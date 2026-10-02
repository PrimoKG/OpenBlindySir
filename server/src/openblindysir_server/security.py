"""HTTP security: headers set by the application on every response (spec §5.5, §12),
Origin checks, bounded JSON bodies, client IP helpers and coarse browser family."""

import ipaddress
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from openblindysir_protocol.enums import BrowserFamily
from openblindysir_protocol.errors import ErrorCode
from openblindysir_protocol.settings import HTTP_JSON_MAX_BYTES
from openblindysir_server.config import Settings

Scope = MutableMapping[str, Any]
ASGIApp = Callable[
    [Scope, Callable[[], Awaitable[Any]], Callable[[Any], Awaitable[None]]], Awaitable[None]
]

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "media-src 'self' blob:; connect-src 'self'; font-src 'self'; object-src 'none'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
BASE_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"content-security-policy", CSP.encode()),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
)
HSTS = (b"strict-transport-security", b"max-age=31536000")


class SecurityHeadersMiddleware:
    """Pure ASGI middleware adding the security headers to every HTTP response."""

    def __init__(self, app: Any, *, hsts: bool) -> None:
        self.app = app
        self.headers = (*BASE_HEADERS, HSTS) if hsts else BASE_HEADERS

    async def __call__(self, scope: Scope, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                names = {name.lower() for name, _ in message.get("headers", [])}
                extra = [(n, v) for n, v in self.headers if n not in names]
                message["headers"] = [*message.get("headers", []), *extra]
            await send(message)

        await self.app(scope, receive, send_with_headers)


def allowed_origins(settings: Settings) -> frozenset[str]:
    origins: set[str] = set()
    if settings.domain and not settings.dev_mode:
        origins.add(f"https://{settings.domain}")
    if settings.dev_mode:
        for host in ("localhost", "127.0.0.1"):
            for port in (settings.port, 5173):
                origins.add(f"http://{host}:{port}")
    return frozenset(origins)


def check_origin(origin: str | None, settings: Settings) -> bool:
    """Exact match only; a missing Origin is refused (CSRF and cross-site WS, spec §12)."""
    return origin is not None and origin in allowed_origins(settings)


def error(status: int, code: ErrorCode) -> JSONResponse:
    return JSONResponse({"error": code.value}, status_code=status)


async def read_json_body(
    request: Request, limit: int = HTTP_JSON_MAX_BYTES
) -> bytes | JSONResponse:
    """Bounded raw body of a JSON request, or an error response (415/413)."""
    content_type = request.headers.get("content-type", "")
    if content_type.split(";")[0].strip().lower() != "application/json":
        return error(415, ErrorCode.JSON_REQUIRED)
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        return error(413, ErrorCode.PAYLOAD_TOO_LARGE)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            return error(413, ErrorCode.PAYLOAD_TOO_LARGE)
    return bytes(body)


def truncate_ip(ip: str | None) -> str:
    """IPv4 /24, IPv6 /48, for logs."""
    if not ip:
        return "-"
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return "-"
    prefix = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))


def browser_family(user_agent: str | None) -> BrowserFamily:
    """Coarse family for audio triage (spec §21); never a version, never stored raw."""
    ua = user_agent or ""
    if any(token in ua for token in ("iPhone", "iPad", "iPod")):
        return BrowserFamily.IOS_WEBKIT
    if "Firefox/" in ua:
        return BrowserFamily.FIREFOX
    if any(token in ua for token in ("Chrome/", "Chromium/", "Edg/")):
        return BrowserFamily.CHROMIUM
    if "Safari/" in ua:
        return BrowserFamily.SAFARI
    return BrowserFamily.OTHER
