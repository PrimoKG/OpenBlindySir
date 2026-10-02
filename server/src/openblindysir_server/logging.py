"""Event logging (spec §21): one ``event=... key=value`` line (or JSON) per event.

Never logged: secrets, tokens, cookies, Authorization headers, paths or track names (only
track ids), answer text (only its length).
"""

import json
import logging
import sys
import time
from collections.abc import Iterable
from typing import Any

ROOT = "openblindysir"
REDACTED = "***"
FORBIDDEN_KEYS = frozenset(
    {
        "password",
        "host_password",
        "token",
        "secret",
        "authorization",
        "cookie",
        "upload_token",
        "text",
        "relpath",
        "path",
        "nickname_raw",
    }
)


def _format_value(value: object) -> str:
    text = (
        "null" if value is None else str(value).lower() if isinstance(value, bool) else str(value)
    )
    if any(ch in text for ch in ' ="') or not text:
        return json.dumps(text, ensure_ascii=False)
    return text


class RedactingFilter(logging.Filter):
    """Masks forbidden keys and any registered secret value appearing in a record."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets: set[str] = {s for s in secrets if s}

    def add_secret(self, value: str) -> None:
        if value:
            self._secrets.add(value)

    def discard_secret(self, value: str) -> None:
        self._secrets.discard(value)

    def _clean(self, text: str) -> str:
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, REDACTED)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        fields: dict[str, Any] | None = getattr(record, "fields", None)
        if fields is not None:
            cleaned = {
                key: REDACTED
                if key.lower() in FORBIDDEN_KEYS
                else self._clean(value)
                if isinstance(value, str)
                else value
                for key, value in fields.items()
            }
            setattr(record, "fields", cleaned)  # noqa: B010 - LogRecord extra attribute
        if isinstance(record.msg, str):
            record.msg = self._clean(record.msg)
        if record.args:
            record.args = tuple(
                self._clean(arg) if isinstance(arg, str) else arg
                for arg in (record.args if isinstance(record.args, tuple) else (record.args,))
            )
        return True


class KeyValueFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields: dict[str, Any] | None = getattr(record, "fields", None)
        if fields is None:
            message = _format_value(record.getMessage())
            return f"level={record.levelname.lower()} logger={record.name} msg={message}"
        parts = [f"event={_format_value(getattr(record, 'event', 'log'))}"]
        parts.extend(f"{key}={_format_value(value)}" for key, value in fields.items())
        if record.levelno >= logging.WARNING:
            parts.insert(0, f"level={record.levelname.lower()}")
        return " ".join(parts)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "logger": record.name,
        }
        fields: dict[str, Any] | None = getattr(record, "fields", None)
        if fields is None:
            data["msg"] = record.getMessage()
        else:
            data["event"] = getattr(record, "event", "log")
            data.update(fields)
        return json.dumps(data, ensure_ascii=False, default=str)


_FILTER = RedactingFilter()


def redaction() -> RedactingFilter:
    """The process-wide redaction filter (secrets and active tokens are registered here)."""
    return _FILTER


def setup_logging(level: str, fmt: str, secrets: Iterable[str]) -> None:
    for secret in secrets:
        _FILTER.add_secret(secret)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else KeyValueFormatter())
    handler.addFilter(_FILTER)
    root = logging.getLogger(ROOT)
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        other = logging.getLogger(name)
        other.handlers[:] = [handler]
        other.propagate = False
    logging.getLogger("uvicorn.access").addFilter(AccessPathFilter())


class AccessPathFilter(logging.Filter):
    """Reduce audio and upload paths in access logs to their prefix (no asset ids)."""

    PREFIXES = ("/api/audio/", "/api/bridge/assets/")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self._reduce(arg) for arg in record.args)
        return True

    def _reduce(self, arg: object) -> object:
        if isinstance(arg, str):
            for prefix in self.PREFIXES:
                if arg.startswith(prefix):
                    return prefix + "…"
        return arg


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """One INFO event line: ``event=<event> key=value ...``."""
    if logger.isEnabledFor(logging.INFO):
        logger.info(event, extra={"event": event, "fields": fields})


def get(name: str) -> logging.Logger:
    return logging.getLogger(f"{ROOT}.{name}")
