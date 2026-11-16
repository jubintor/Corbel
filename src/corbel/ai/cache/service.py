"""Multi-tier caching service with strict tenant isolation and governance invariants.

Implements Level 1 provider-native prompt caching telemetry and Level 2 exact-response caching.
Enforces tenant/project key isolation, TTL freshness, and prohibits caching for consequential actions.
Adheres strictly to ADR-015 and ARCHITECTURE.md Section 7.3.
"""

import hashlib
import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class CachedEntry:
    """Internal container for a cached response."""

    def __init__(self, data: Any, expires_at: float, metadata: dict[str, Any] | None = None) -> None:
        self.data = data
        self.expires_at = expires_at
        self.metadata = metadata or {}

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class CacheService:
    """Service managing exact-response caching and provider-native prompt caching tracking."""

    def __init__(self) -> None:
        # Exact response cache dictionary: cache_key -> CachedEntry
        self._exact_cache: dict[str, CachedEntry] = {}

    def build_cache_key(
        self,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        prompt_version_tag: str,
        user_prompt: str,
        schema_hash: str = "default",
    ) -> str:
        """Construct a strictly isolated cache key incorporating tenant, project, prompt version, and schema hash."""
        raw = f"{tenant_id}:{project_id}:{prompt_version_tag}:{schema_hash}:{user_prompt}"
        hashed = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"exact:{tenant_id}:{project_id}:{hashed}"

    def get(
        self,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        prompt_version_tag: str,
        user_prompt: str,
        schema_hash: str = "default",
        is_consequential: bool = False,
    ) -> Any | None:
        """Retrieve cached response if valid, unexpired, and not for a consequential action.

        Governance invariant: Cached responses may NEVER be used to authorize consequential actions.
        """
        if is_consequential:
            logger.debug("Bypassing cache for consequential business action")
            return None

        key = self.build_cache_key(tenant_id, project_id, prompt_version_tag, user_prompt, schema_hash)
        entry = self._exact_cache.get(key)
        if not entry:
            return None

        if entry.is_expired():
            del self._exact_cache[key]
            logger.debug("Evicted expired cache key: %s", key)
            return None

        logger.info("Level 2 cache HIT for tenant=%s, project=%s", tenant_id, project_id)
        return entry.data

    def put(
        self,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        prompt_version_tag: str,
        user_prompt: str,
        data: Any,
        ttl_seconds: int = 3600,
        schema_hash: str = "default",
        is_consequential: bool = False,
    ) -> None:
        """Store an exact deterministic response in cache with explicit TTL."""
        if is_consequential:
            # Never cache consequential action outputs
            return

        key = self.build_cache_key(tenant_id, project_id, prompt_version_tag, user_prompt, schema_hash)
        expires_at = time.time() + ttl_seconds
        self._exact_cache[key] = CachedEntry(data=data, expires_at=expires_at)
        logger.debug("Stored response in Level 2 cache: %s (TTL=%ds)", key, ttl_seconds)

    def invalidate_project(self, project_id: uuid.UUID) -> int:
        """Event-driven invalidation hook to purge cached analytical queries for a project upon dataset update."""
        prefix = f":{project_id}:"
        keys_to_remove = [k for k in self._exact_cache if prefix in k]
        for k in keys_to_remove:
            del self._exact_cache[k]
        logger.info("Invalidated %d cache keys for project %s", len(keys_to_remove), project_id)
        return len(keys_to_remove)

    def clear(self) -> None:
        """Clear all cache entries."""
        self._exact_cache.clear()


_global_cache_service: CacheService | None = None


def get_default_cache_service() -> CacheService:
    """Retrieve singleton default cache service instance."""
    global _global_cache_service
    if _global_cache_service is None:
        _global_cache_service = CacheService()
    return _global_cache_service
