"""Optional, non-blocking Arize Phoenix telemetry adapter.

Implements ADR-016:
- Provides optional OpenTelemetry-compliant trace and span export for AI operations.
- Corbel functions 100% independently if Phoenix is disabled, offline, or returns errors.
- Automatic secret and credential redaction.
- Optional payload capture controlled by PHOENIX_CAPTURE_PAYLOADS.
"""

import logging
import re
import time
import uuid
from functools import lru_cache
from typing import Any

import httpx

from corbel.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Regular expressions for identifying and redacting credentials and tokens
DATABASE_URI_PATTERN = re.compile(
    r"(?i)\b((?:postgres(?:ql)?(?:\+[a-z0-9_]+)?|mysql(?:\+[a-z0-9_]+)?|mssql(?:\+[a-z0-9_]+)?|mongodb(?:\+srv)?|redis[s]?):\/\/[^\s\"'<>]+)"
)


def redact_database_uri_in_text(text: str) -> str:
    """Robustly redact userinfo credentials from database connection URIs in text.

    Correctly handles passwords with special characters (e.g. '@', ':', URL-encoded '%40'),
    while preserving the scheme, username, hostname, port, and database name.
    """

    def _replace_uri(match: re.Match[str]) -> str:
        uri_str = match.group(1)
        trailing = ""
        while uri_str and uri_str[-1] in ".,;:)!?'\"":
            trailing = uri_str[-1] + trailing
            uri_str = uri_str[:-1]

        scheme_match = re.match(r"^([a-zA-Z0-9+_-]+:\/\/)(.*)$", uri_str)
        if not scheme_match:
            return uri_str + trailing

        scheme_prefix = scheme_match.group(1)
        body = scheme_match.group(2)

        # In URI syntax: authority ends at the first '/', '?', or '#'
        path_match = re.search(r"[/?#]", body)
        if path_match:
            authority = body[: path_match.start()]
            rest_path = body[path_match.start() :]
        else:
            authority = body
            rest_path = ""

        # If no '@' in authority, there is no userinfo/credentials in the authority component
        if "@" not in authority:
            return uri_str + trailing

        # When password contains '@' (e.g. admin:p@ssw0rd99@db:5432),
        # the hostname/port is ALWAYS after the LAST '@' in the authority component.
        userinfo, host_port = authority.rsplit("@", 1)

        # If userinfo contains ':', split user and password on the first ':' only
        # so passwords containing ':' are fully redacted.
        if ":" in userinfo:
            user, _ = userinfo.split(":", 1)
            redacted_userinfo = f"{user}:[REDACTED]"
        else:
            redacted_userinfo = "[REDACTED]"

        redacted_authority = f"{redacted_userinfo}@{host_port}"
        return f"{scheme_prefix}{redacted_authority}{rest_path}{trailing}"

    return DATABASE_URI_PATTERN.sub(_replace_uri, text)


SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{15,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(r"((?:api[_-]?key|password|secret)\s*[:=]\s*['\"]?)[A-Za-z0-9_\-]{6,}(['\"]?)", re.IGNORECASE),
    re.compile(r"((?:session(?:_?id)?|token|csrf|xsrf)\s*=\s*)[A-Za-z0-9_\-\.]{10,}", re.IGNORECASE),
]


def redact_secrets_from_text(text: str | None) -> str | None:
    """Sanitize strings by redacting API keys, Bearer tokens, and credential patterns."""
    if not text:
        return text
    # 1. Apply URI-aware database credential redaction
    sanitized = redact_database_uri_in_text(text)
    # 2. Apply other secret patterns
    for pattern in SECRET_PATTERNS:
        if pattern.groups == 2:
            sanitized = pattern.sub(r"\g<1>[REDACTED]\g<2>", sanitized)
        elif pattern.groups == 1:
            sanitized = pattern.sub(r"\g<1>[REDACTED]", sanitized)
        else:
            sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


class PhoenixTelemetryAdapter:
    """Asynchronous exporter sending LLM spans to Arize Phoenix OpenTelemetry OTLP collector."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.enabled = self.settings.PHOENIX_ENABLED
        self.endpoint = self.settings.PHOENIX_COLLECTOR_ENDPOINT
        self.project_name = self.settings.PHOENIX_PROJECT_NAME
        self.capture_payloads = self.settings.PHOENIX_CAPTURE_PAYLOADS
        self.timeout_seconds = self.settings.PHOENIX_TIMEOUT_SECONDS
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._client

    async def close(self) -> None:
        """Close underlying HTTP client resources cleanly."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def check_health(self) -> bool:
        """Ping Phoenix endpoint or root to determine server reachability.

        Never raises an exception; returns False if unreachable or disabled.
        """
        if not self.enabled:
            return False
        try:
            client = await self._get_client()
            # Try root URL or endpoint
            base_url = self.endpoint.split("/v1/traces")[0]
            resp = await client.get(base_url, timeout=1.5)
            return resp.status_code < 500
        except Exception as exc:
            logger.debug("Phoenix health check unreachable: %s", exc)
            return False

    async def export_span(
        self,
        span_name: str,
        model_name: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        organization_id: str | uuid.UUID | None = None,
        project_id: str | uuid.UUID | None = None,
        correlation_id: str | None = None,
        prompt: str | None = None,
        response_text: str | None = None,
        error_message: str | None = None,
        status: str = "SUCCESS",
    ) -> None:
        """Export an LLM operation span to Arize Phoenix.

        If Phoenix is disabled or encounters any network or HTTP failure,
        the error is silently caught and logged; caller workflow continues unaffected.
        """
        if not self.enabled:
            return

        # Fire and forget safely in background or await cleanly
        try:
            await self._send_span(
                span_name=span_name,
                model_name=model_name,
                provider=provider,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                organization_id=str(organization_id) if organization_id else None,
                project_id=str(project_id) if project_id else None,
                correlation_id=correlation_id,
                prompt=prompt,
                response_text=response_text,
                error_message=error_message,
                status=status,
            )
        except Exception as exc:
            # Fault tolerance invariant (ADR-016): Phoenix failure never breaks Corbel
            logger.debug("Arize Phoenix telemetry export suppressed error: %s", exc)

    async def _send_span(
        self,
        span_name: str,
        model_name: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        organization_id: str | None,
        project_id: str | None,
        correlation_id: str | None,
        prompt: str | None,
        response_text: str | None,
        error_message: str | None,
        status: str,
    ) -> None:
        trace_id = uuid.uuid4().hex
        span_id = uuid.uuid4().hex[:16]

        now_ns = int(time.time() * 1_000_000_000)
        start_ns = now_ns - int(latency_ms * 1_000_000)

        # Standard OpenTelemetry Attributes for AI Spans (OpenInference spec)
        attributes: list[dict[str, Any]] = [
            {"key": "openinference.span.kind", "value": {"stringValue": "LLM"}},
            {"key": "llm.model_name", "value": {"stringValue": model_name}},
            {"key": "llm.provider", "value": {"stringValue": provider}},
            {"key": "llm.token_count.prompt", "value": {"intValue": input_tokens}},
            {"key": "llm.token_count.completion", "value": {"intValue": output_tokens}},
            {"key": "llm.token_count.total", "value": {"intValue": input_tokens + output_tokens}},
            {"key": "llm.invocation_latency_ms", "value": {"doubleValue": latency_ms}},
        ]

        if organization_id:
            attributes.append({"key": "corbel.tenant_id", "value": {"stringValue": organization_id}})
        if project_id:
            attributes.append({"key": "corbel.project_id", "value": {"stringValue": project_id}})
        if correlation_id:
            attributes.append({"key": "corbel.correlation_id", "value": {"stringValue": correlation_id}})

        # Optional payload capture (with strict credential redaction)
        if self.capture_payloads:
            if prompt:
                safe_prompt = redact_secrets_from_text(prompt) or ""
                attributes.append({
                    "key": "llm.input_messages.0.message.content",
                    "value": {"stringValue": safe_prompt[:2000]},
                })
            if response_text:
                safe_resp = redact_secrets_from_text(response_text) or ""
                attributes.append({
                    "key": "llm.output_messages.0.message.content",
                    "value": {"stringValue": safe_resp[:2000]},
                })

        if error_message:
            attributes.append({
                "key": "exception.message",
                "value": {"stringValue": redact_secrets_from_text(error_message) or ""},
            })

        status_code = 1 if status == "SUCCESS" else 2  # 1 = Ok, 2 = Error

        otlp_payload = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "corbel"}},
                            {"key": "project.name", "value": {"stringValue": self.project_name}},
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "corbel.ai.telemetry", "version": "0.1.0"},
                            "spans": [
                                {
                                    "traceId": trace_id,
                                    "spanId": span_id,
                                    "name": span_name,
                                    "kind": 1,  # SpanKind.INTERNAL
                                    "startTimeUnixNano": start_ns,
                                    "endTimeUnixNano": now_ns,
                                    "attributes": attributes,
                                    "status": {"code": status_code},
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        client = await self._get_client()
        resp = await client.post(
            self.endpoint,
            json=otlp_payload,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code >= 400:
            logger.debug("Phoenix collector responded with status %d", resp.status_code)


@lru_cache
def get_phoenix_adapter() -> PhoenixTelemetryAdapter:
    """Return cached singleton instance of PhoenixTelemetryAdapter."""
    return PhoenixTelemetryAdapter()
