"""Bridge configuration: CLI > environment > ``config.toml`` (spec §11, patch 1)."""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tomllib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from openblindysir_bridge.scanner import DEFAULT_EXTENSIONS, require_unlinked_path
from openblindysir_protocol.bridge import ScanSources

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
    allow_full_review: bool = False
    scanned_folders: tuple[str, ...] = ("",)


def default_config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "OpenBlindySir" / "bridge" / "config.toml"
    legacy = Path.home() / ".config" / "openblindysir" / "bridge" / "config.toml"
    if sys.platform == "darwin":
        if legacy.is_file():
            return legacy
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "OpenBlindySir"
            / "bridge"
            / "config.toml"
        )
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    if not base.is_absolute():
        base = Path.home() / ".config"
    return base / "openblindysir" / "bridge" / "config.toml"


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def protect_file(path: Path) -> None:
    """Restrict secrets before writing them, including Windows inherited ACLs."""
    if os.name == "posix":
        path.chmod(0o600)
    elif os.name == "nt":
        system = Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32"
        result = subprocess.run(  # noqa: S603 - fixed system executable and arguments
            [str(system / "whoami.exe"), "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
            creationflags=0x08000000,
        )
        sid = next(iter(csv.reader(result.stdout.splitlines())))[-1]
        if not re.fullmatch(r"S-1-(?:\d+-)+\d+", sid):
            raise OSError("private permissions unavailable")
        subprocess.run(  # noqa: S603 - SID validated, path is an argv item
            [str(system / "icacls.exe"), str(path), "/inheritance:r", "/grant:r", f"*{sid}:F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=10,
            creationflags=0x08000000,
        )


def _private_write(path: Path, body: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        protect_file(path)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            descriptor = -1
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        path.unlink(missing_ok=True)
        raise


def write_config(path: Path, values: Mapping[str, str], *, backup: bool = False) -> None:
    """Atomic private TOML; explicit configuration edits retain a private backup."""
    require_unlinked_path(path)
    if any(not re.fullmatch(r"[a-z_]+", key) for key in values):
        raise ValueError("invalid configuration key")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if backup and path.is_file():
        previous = path.with_name(f"{path.name}.bak-{uuid.uuid4().hex}")
        _private_write(previous, path.read_text(encoding="utf-8"))
    body = "".join(f"{key} = {_quote(value)}\n" for key, value in sorted(values.items()))
    temporary = path.parent / f".config-{uuid.uuid4().hex}.tmp"
    _private_write(temporary, body)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_config(path: Path) -> dict[str, str]:
    require_unlinked_path(path)
    if not path.is_file():
        return {}
    if path.stat().st_size > 65536:
        raise ValueError("configuration too large")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if isinstance(v, str)}


def _ensure_bridge_id(path: Path, data: dict[str, str], *, persist: bool = True) -> str:
    current = data.get("bridge_id")
    try:
        if current and str(uuid.UUID(current)) == current:
            return current
    except ValueError:
        raise ValueError(
            "invalid Bridge identity; preserve configuration and repair its UUID"
        ) from None
    if current:
        raise ValueError("invalid Bridge identity; preserve configuration and repair its UUID")
    data["bridge_id"] = str(uuid.uuid4())
    if persist:
        write_config(path, data)
    return data["bridge_id"]


def persist_bridge_id(cfg: BridgeConfig) -> None:
    """Explicit registration uses the same identity as the next run."""
    values = read_config(cfg.config_path)
    if values.get("bridge_id") != cfg.bridge_id:
        values["bridge_id"] = cfg.bridge_id
        write_config(cfg.config_path, values)


def load_config(
    ns: argparse.Namespace, env: Mapping[str, str] | None = None, *, persist_identity: bool = True
) -> BridgeConfig:
    env = os.environ if env is None else env
    path = Path(ns.config or env.get(f"{ENV_PREFIX}CONFIG") or default_config_path())
    file_values = read_config(path)
    credential_path = getattr(ns, "credentials", None) or env.get(f"{ENV_PREFIX}CREDENTIALS_FILE")
    credential_values: dict[str, str] = {}
    if credential_path:
        source = Path(credential_path)
        require_unlinked_path(source)
        if source.stat().st_size > 8192:
            raise ValueError("credential file too large")
        credential_values = tomllib.loads(source.read_text(encoding="utf-8"))
        if set(credential_values) != {"bridge_id", "name", "secret"} or any(
            not isinstance(value, str) for value in credential_values.values()
        ):
            raise ValueError("invalid credential file")
        file_values = {**file_values, **credential_values}
    bridge_id = _ensure_bridge_id(path, dict(file_values), persist=persist_identity)

    def pick(cli: str | None, key: str, file_key: str) -> str | None:
        if file_key in credential_values:
            return credential_values[file_key]
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
    if not extensions <= DEFAULT_EXTENSIONS:
        raise ValueError("unsupported extensions")
    folders = json.loads(file_values.get("scanned_folders_json", '[""]'))
    scanned = ScanSources(t="SCAN_SOURCES", folders=folders).folders
    return BridgeConfig(
        server_url=pick(getattr(ns, "server", None), "SERVER", "server_url"),
        music_dir=Path(music_dir) if music_dir else None,
        secret=pick(getattr(ns, "secret", None), "SECRET", "secret"),
        name=pick(getattr(ns, "name", None), "NAME", "name") or "Bridge",
        ffmpeg=pick(getattr(ns, "ffmpeg", None), "FFMPEG", "ffmpeg"),
        ffprobe=pick(getattr(ns, "ffprobe", None), "FFPROBE", "ffprobe"),
        extensions=extensions,
        bridge_id=bridge_id,
        config_path=path,
        allow_full_review=getattr(ns, "allow_full_review", False)
        or pick(None, "ALLOW_FULL_REVIEW", "allow_full_review") == "true",
        scanned_folders=tuple(scanned if scanned is not None else [""]),
    )
