"""Bounded, redacted diagnostics; no source extraction or arbitrary endpoint."""

import asyncio
import json
import platform
import ssl
import unicodedata
from dataclasses import dataclass

import httpx
import websockets
from pydantic import ValidationError

from openblindysir_bridge import __version__, ffmpeg
from openblindysir_bridge.catalog import LocalCatalog
from openblindysir_bridge.config import BridgeConfig
from openblindysir_bridge.sandbox import Sandbox
from openblindysir_bridge.urls import validate_server_url
from openblindysir_protocol.bridge import (
    BRIDGE_ID_HEADER,
    CATALOG_TOKEN_HEADER,
    BridgeHello,
    Welcome,
)
from openblindysir_protocol.compatibility import required_range
from openblindysir_protocol.version import PROTOCOL_VERSION

GUIDE = "https://github.com/PrimoKG/OpenBlindySir/blob/main/docs/troubleshooting.md"
CONNECT_TIMEOUT_S = 20
CONNECTION_ACTIONS = {
    "network": "réseau indisponible ; vérifiez adresse, DNS, VPN, pare-feu et proxy",
    "certificate": "certificat refusé ; vérifiez adresse et autorité SSL_CERT_FILE",
    "authentication": (
        "secret ou identité refusé/révoqué ; demandez un fichier de credentials "
        "propre à ce Bridge puis relancez configure"
    ),
    "protocol": "protocole incompatible ; mettez à jour serveur, Bridge et page web ensemble",
    "catalogue": "catalogue refusé ; vérifiez limites du proxy et identité du Bridge",
}


def validate_config(cfg: BridgeConfig, *, root: bool = True, connection: bool = True) -> None:
    if connection:
        validate_server_url(cfg.server_url or "")
        if not cfg.secret or not 32 <= len(cfg.secret) <= 4096:
            raise ValueError("Le secret du Bridge doit contenir au moins 32 caractères.")
        if any(unicodedata.category(ch) in {"Cc", "Cf"} for ch in cfg.secret):
            raise ValueError("Le secret contient des caractères de contrôle.")
    if not 1 <= len(cfg.name) <= 24 or any(
        unicodedata.category(ch) in {"Cc", "Cf"} for ch in cfg.name
    ):
        raise ValueError("Choisissez un nom lisible de 1 à 24 caractères.")
    if root:
        if cfg.music_dir is None or not cfg.music_dir.is_dir():
            raise ValueError("Dossier introuvable : vérifiez son accès puis relancez init.")
        Sandbox(str(cfg.music_dir))


@dataclass(frozen=True)
class ConnectionResult:
    ok: bool
    code: str
    protocol_range: tuple[int, int] | None = None


async def check_connection(
    cfg: BridgeConfig, info: ffmpeg.FfmpegInfo, catalog: LocalCatalog
) -> ConnectionResult:
    """One authenticated registration + optional catalogue, then disconnect.

    The caller announces the scan and possible replacement of this UUID's connection.
    Server replies and exception text are never copied into diagnostics.
    """
    server = validate_server_url(cfg.server_url or "")
    hello = BridgeHello(
        t="HELLO",
        protocol=PROTOCOL_VERSION,
        bridge_id=cfg.bridge_id,
        name=cfg.name,
        version=__version__,
        formats=info.formats(),
        catalog_hash=catalog.catalog_hash,
        track_count=len(catalog.entries),
        allow_full_review=cfg.allow_full_review,
    )
    try:
        async with asyncio.timeout(CONNECT_TIMEOUT_S):
            async with websockets.connect(
                server.ws_url(),
                additional_headers={"Authorization": f"Bearer {cfg.secret}"},
                ssl=ssl.create_default_context() if server.scheme == "https" else None,
                max_size=65536,
                open_timeout=10,
                close_timeout=2,
            ) as ws:
                await ws.send(hello.model_dump_json())
                raw = await ws.recv()
                response = json.loads(raw)
                if not isinstance(response, dict):
                    return ConnectionResult(False, "protocol")
                if response.get("t") == "ERROR":
                    code = response.get("code")
                    return ConnectionResult(
                        False, "protocol" if code == "protocol_mismatch" else "authentication"
                    )
                welcome = Welcome.model_validate_json(raw)
                if welcome.catalog_needed:
                    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as http:
                        result = await http.put(
                            server.join_path("/api/bridge/catalog"),
                            content=catalog.to_upload(cfg.bridge_id),
                            headers={
                                "Authorization": f"Bearer {cfg.secret}",
                                CATALOG_TOKEN_HEADER: welcome.catalog_upload_token or "",
                                BRIDGE_ID_HEADER: cfg.bridge_id,
                                "Content-Encoding": "gzip",
                                "Content-Type": "application/json",
                            },
                        )
                        if result.status_code != 204:
                            return ConnectionResult(False, "catalogue")
                return ConnectionResult(True, "registered")
    except ssl.SSLError:
        return ConnectionResult(False, "certificate")
    except websockets.exceptions.InvalidStatus as exc:
        return ConnectionResult(
            False, "authentication" if exc.response.status_code in {401, 403} else "network"
        )
    except websockets.exceptions.ConnectionClosed as exc:
        return ConnectionResult(
            False,
            "authentication"
            if exc.rcvd and exc.rcvd.reason == "authentication"
            else "protocol"
            if exc.rcvd and exc.rcvd.code == 1008
            else "network",
            required_range(exc.rcvd.reason) if exc.rcvd else None,
        )
    except (OSError, TimeoutError, httpx.HTTPError, websockets.exceptions.WebSocketException):
        return ConnectionResult(False, "network")
    except (ValueError, ValidationError):
        return ConnectionResult(False, "protocol")


def diagnostic_report(
    cfg: BridgeConfig,
    *,
    config_ok: bool,
    info: ffmpeg.FfmpegInfo | None,
    tracks: int | None = None,
    connection: ConnectionResult | None = None,
) -> dict[str, object]:
    """Explicit allowlist: no URL, UUID, hostname, root, secret, headers or exception."""
    return {
        "bridge_version": __version__,
        "protocol": PROTOCOL_VERSION,
        "system": platform.system(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "configuration_valid": config_ok,
        "secret_configured": bool(cfg.secret),
        "full_review_enabled": cfg.allow_full_review,
        "extensions": sorted(cfg.extensions),
        "ffmpeg": info.version if info else None,
        "formats": [f.value for f in info.formats()] if info else [],
        "tracks": tracks,
        "connection": connection.code if connection else "not_checked",
        "required_protocol": connection.protocol_range if connection else None,
    }
