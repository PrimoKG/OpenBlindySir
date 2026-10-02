"""Server URL rules: HTTPS only, except plain HTTP towards localhost (spec §11)."""

from dataclasses import dataclass
from urllib.parse import urlsplit

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class InvalidServerUrlError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ServerUrl:
    scheme: str
    host: str
    port: int | None

    @property
    def is_local(self) -> bool:
        return self.host in LOCAL_HOSTS

    def _netloc(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{host}:{self.port}" if self.port else host

    def base(self) -> str:
        return f"{self.scheme}://{self._netloc()}"

    def ws_url(self) -> str:
        ws_scheme = "wss" if self.scheme == "https" else "ws"
        return f"{ws_scheme}://{self._netloc()}/api/bridge/ws"

    def join_path(self, path: str) -> str:
        """Join a server-provided PATH to OUR configured server: never another host."""
        if not path.startswith("/") or path.startswith("//") or "://" in path:
            raise InvalidServerUrlError("not a path")
        return self.base() + path


def validate_server_url(url: str) -> ServerUrl:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not host:
        raise InvalidServerUrlError("missing host")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise InvalidServerUrlError("credentials, query and fragment are not allowed")
    if parts.path not in ("", "/"):
        raise InvalidServerUrlError("the server URL must not contain a path")
    if scheme == "https" or (scheme == "http" and host in LOCAL_HOSTS):
        return ServerUrl(scheme=scheme, host=host, port=parts.port)
    raise InvalidServerUrlError("https is required (http only towards localhost)")
