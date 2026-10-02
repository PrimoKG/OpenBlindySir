"""Bridge configuration: CLI > environment > ``config.toml`` (spec §11, patch 1)."""

import argparse
import os
import socket
import sys
import tomllib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from openblindysir_bridge.scanner import DEFAULT_EXTENSIONS

ENV_PREFIX = "OPENBLINDYSIR_BRIDGE_"


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    server_url: str | None
    music_dir: Path | None
    secret: str | None
    name: str
    ffmpeg: str | None
    ffprobe: str | None
    extensions: frozenset[str]
    bridge_id: str
    config_path: Path


def default_config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "OpenBlindySir" / "bridge" / "config.toml"
    return Path.home() / ".config" / "openblindysir" / "bridge" / "config.toml"


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_config(path: Path, values: Mapping[str, str]) -> None:
    """Write string keys only (no TOML writer dependency); private permissions on POSIX."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{key} = {_quote(value)}\n" for key, value in values.items())
    path.write_text(body, encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o600)


def read_config(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if isinstance(v, str)}


def _ensure_bridge_id(path: Path, data: dict[str, str]) -> str:
    current = data.get("bridge_id")
    try:
        if current and str(uuid.UUID(current)) == current:
            return current
    except ValueError:
        pass
    data["bridge_id"] = str(uuid.uuid4())
    write_config(path, data)
    return data["bridge_id"]


def load_config(ns: argparse.Namespace, env: Mapping[str, str] | None = None) -> BridgeConfig:
    env = os.environ if env is None else env
    path = Path(ns.config or env.get(f"{ENV_PREFIX}CONFIG") or default_config_path())
    file_values = read_config(path)
    bridge_id = _ensure_bridge_id(path, dict(file_values))

    def pick(cli: str | None, key: str, file_key: str) -> str | None:
        return cli or env.get(f"{ENV_PREFIX}{key}") or file_values.get(file_key)

    extensions_raw = pick(getattr(ns, "extensions", None), "EXTENSIONS", "extensions")
    extensions = (
        frozenset(
            ext if ext.startswith(".") else f".{ext}"
            for ext in extensions_raw.lower().replace(",", " ").split()
        )
        if extensions_raw
        else DEFAULT_EXTENSIONS
    )
    music_dir = pick(getattr(ns, "dir", None), "DIR", "music_dir")
    return BridgeConfig(
        server_url=pick(getattr(ns, "server", None), "SERVER", "server_url"),
        music_dir=Path(music_dir) if music_dir else None,
        secret=pick(getattr(ns, "secret", None), "SECRET", "secret"),
        name=pick(getattr(ns, "name", None), "NAME", "name")
        or socket.gethostname()[:24]
        or "Bridge",
        ffmpeg=pick(getattr(ns, "ffmpeg", None), "FFMPEG", "ffmpeg"),
        ffprobe=pick(getattr(ns, "ffprobe", None), "FFPROBE", "ffprobe"),
        extensions=extensions,
        bridge_id=bridge_id,
        config_path=path,
    )
