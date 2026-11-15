"""Structured logging configuration for Corbel with correlation ID support."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Global context variable for tracking correlation ID per request / task execution
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    """Retrieve the current correlation ID from context."""
    return correlation_id_ctx.get()


def set_correlation_id(correlation_id: str | None) -> None:
    """Set the correlation ID in the current execution context."""
    correlation_id_ctx.set(correlation_id)


class JSONLogFormatter(logging.Formatter):
    """Custom JSON formatter producing structured log entries."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        correlation_id = get_correlation_id()
        if correlation_id:
            log_obj["correlation_id"] = correlation_id

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Include custom extra fields if present
        extra_keys = set(record.__dict__.keys()) - {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelname", "levelno", "lineno", "module", "msecs",
            "msg", "name", "pathname", "process", "processName", "relativeCreated",
            "stack_info", "thread", "threadName",
        }
        for key in extra_keys:
            val = getattr(record, key)
            if key not in log_obj:
                try:
                    # ensure serializable
                    json.dumps(val)
                    log_obj[key] = val
                except (TypeError, OverflowError):
                    log_obj[key] = str(val)

        return json.dumps(log_obj)


class ConsoleLogFormatter(logging.Formatter):
    """Clean readable console formatter for development mode."""

    def format(self, record: logging.LogRecord) -> str:
        time_str = datetime.fromtimestamp(record.created, tz=UTC).strftime("%H:%M:%S")
        correlation_id = get_correlation_id()
        cid_str = f" [{correlation_id[:8]}]" if correlation_id else ""
        base = f"{time_str} | {record.levelname:<7} | {record.name}{cid_str} - {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def setup_logging(log_level: str = "INFO", log_format: str = "console") -> None:
    """Configure root logger with structured formatting."""
    root_logger = logging.getLogger()
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)

    if log_format.lower() == "json":
        handler.setFormatter(JSONLogFormatter())
    else:
        handler.setFormatter(ConsoleLogFormatter())

    root_logger.addHandler(handler)

    # Silence overly verbose external loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
