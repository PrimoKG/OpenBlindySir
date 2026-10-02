"""Session cookie: ``__Host-openblindysir``, HttpOnly, Secure, SameSite=Strict (spec §8.1, §12).

In DEV_MODE the cookie cannot be Secure on http://localhost, hence a distinct name.
"""

from starlette.requests import HTTPConnection
from starlette.responses import Response

from openblindysir_server.config import Settings

PROD_COOKIE = "__Host-openblindysir"
DEV_COOKIE = "openblindysir_dev"


def cookie_name(settings: Settings) -> str:
    return DEV_COOKIE if settings.dev_mode else PROD_COOKIE


def read_token(conn: HTTPConnection, settings: Settings) -> str | None:
    return conn.cookies.get(cookie_name(settings))


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        cookie_name(settings),
        token,
        max_age=settings.session_idle_ttl_h * 3600,
        path="/",
        secure=not settings.dev_mode,
        httponly=True,
        samesite="strict",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.set_cookie(
        cookie_name(settings),
        "",
        max_age=0,
        path="/",
        secure=not settings.dev_mode,
        httponly=True,
        samesite="strict",
    )
