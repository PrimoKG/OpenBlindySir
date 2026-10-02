"""Server configuration from the environment (spec §15), with start-up refusal rules (§12).

A local ``.env`` file, if present in the working directory, only fills variables missing
from the environment (development convenience; never committed).
"""

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from openblindysir_protocol.enums import ClipFormat
from openblindysir_server.game.config import CoreConfig

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
MIN_PASSWORD = 12
MIN_BRIDGE_SECRET = 32
WEAK_VALUES = frozenset({"changeme", "change-me", "password"})
LOCAL_DOMAINS = frozenset({"localhost", "127.0.0.1"})
OPEN_NETWORKS = frozenset({"0.0.0.0/0", "::/0", "*"})
DOTENV = Path(".env")


class ConfigError(Exception):
    """Every configuration problem at once, as ``(variable, reason)`` pairs; never values."""

    def __init__(self, problems: list[tuple[str, str]]) -> None:
        super().__init__(", ".join(f"{var}:{reason}" for var, reason in problems))
        self.problems = problems


@dataclass(frozen=True, slots=True)
class Settings:
    blind_password: str = field(repr=False)
    host_password: str = field(repr=False)
    bridge_secret: str = field(repr=False)
    domain: str | None = None
    trusted_proxies: tuple[str, ...] = ("172.16.0.0/12",)
    log_level: LogLevel = "INFO"
    log_format: Literal["text", "json"] = "text"
    log_track_names: bool = False
    max_players: int = 20
    clip_min_s: int = 5
    clip_max_s: int = 60
    clip_format: ClipFormat = ClipFormat.AAC
    clip_bitrate: int = 128
    audio_cache_mb: int = 32
    max_clip_mb: int = 2
    ready_timeout_s: int = 10
    answer_max_chars: int = 200
    near_tie_ms: int = 300
    session_idle_ttl_h: int = 24
    dev_mode: bool = False
    static_dir: Path | None = None
    host: str = "0.0.0.0"  # noqa: S104 - listens inside the container, behind the proxy
    port: int = 8000
    warnings: tuple[tuple[str, str], ...] = ()
    state_dir: Path | None = None

    @property
    def secrets(self) -> tuple[str, ...]:
        return (self.blind_password, self.host_password, self.bridge_secret)


def read_dotenv(path: Path) -> dict[str, str]:
    """Minimal ``KEY=VALUE`` parser: no interpolation, ``#`` comments, optional quotes."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


class _Reader:
    def __init__(self, env: Mapping[str, str]) -> None:
        self.env = env
        self.problems: list[tuple[str, str]] = []
        self.warnings: list[tuple[str, str]] = []

    def text(self, name: str) -> str | None:
        value = self.env.get(name)
        return value.strip() if value is not None and value.strip() else None

    def boolean(self, name: str, default: bool) -> bool:
        raw = self.text(name)
        if raw is None:
            return default
        lowered = raw.lower()
        if lowered in {"1", "true", "yes"}:
            return True
        if lowered in {"0", "false", "no"}:
            return False
        self.problems.append((name, "invalid_boolean"))
        return default

    def integer(self, name: str, default: int, low: int, high: int) -> int:
        raw = self.text(name)
        if raw is None:
            return default
        try:
            value = int(raw)
        except ValueError:
            self.problems.append((name, "invalid_integer"))
            return default
        if not low <= value <= high:
            self.problems.append((name, "out_of_range"))
            return default
        return value

    def choice(self, name: str, default: str, allowed: tuple[str, ...]) -> str:
        raw = self.text(name)
        if raw is None:
            return default
        if raw not in allowed:
            self.problems.append((name, "invalid_value"))
            return default
        return raw


def _check_secret(r: _Reader, name: str, value: str | None, minimum: int, *, dev: bool) -> str:
    if value is None:
        r.problems.append((name, "missing"))
        return ""
    weak = value.strip().lower() in WEAK_VALUES
    short = len(value) < minimum
    if weak or short:
        reason = "weak_value" if weak else "too_short"
        (r.warnings if dev else r.problems).append((name, reason))
    return value


def _proxies(r: _Reader) -> tuple[str, ...]:
    raw = r.text("TRUSTED_PROXIES")
    if raw is None:
        return ("172.16.0.0/12",)
    items = tuple(item.strip() for item in raw.split(",") if item.strip())
    for item in items:
        if item in OPEN_NETWORKS:
            r.problems.append(("TRUSTED_PROXIES", "too_broad"))
            continue
        try:
            network = ipaddress.ip_network(item, strict=False)
        except ValueError:
            r.problems.append(("TRUSTED_PROXIES", "invalid_network"))
            continue
        if network.prefixlen == 0:
            r.problems.append(("TRUSTED_PROXIES", "too_broad"))
    return items


def load_settings(
    env: Mapping[str, str] | None = None, *, dotenv: Path | None = DOTENV
) -> Settings:
    """Read and validate the configuration; raise ConfigError listing every problem."""
    merged: dict[str, str] = read_dotenv(dotenv) if dotenv is not None else {}
    merged.update(os.environ if env is None else env)
    r = _Reader(merged)
    dev = r.boolean("DEV_MODE", default=False)
    blind = _check_secret(r, "BLIND_PASSWORD", r.text("BLIND_PASSWORD"), MIN_PASSWORD, dev=dev)
    host_pw = _check_secret(r, "HOST_PASSWORD", r.text("HOST_PASSWORD"), MIN_PASSWORD, dev=dev)
    bridge = _check_secret(r, "BRIDGE_SECRET", r.text("BRIDGE_SECRET"), MIN_BRIDGE_SECRET, dev=dev)
    if blind and host_pw and blind == host_pw:
        r.problems.append(("HOST_PASSWORD", "equals_blind_password"))
    domain = r.text("DOMAIN")
    if domain is None and not dev:
        r.problems.append(("DOMAIN", "missing"))
    if dev and domain is not None and domain not in LOCAL_DOMAINS:
        r.problems.append(("DEV_MODE", "forbidden_with_public_domain"))
    clip_min = r.integer("CLIP_MIN_S", 5, 5, 60)
    clip_max = r.integer("CLIP_MAX_S", 60, 5, 60)
    if clip_min > clip_max:
        r.problems.append(("CLIP_MIN_S", "greater_than_clip_max"))
    cache_mb = r.integer("AUDIO_CACHE_MB", 32, 8, 256)
    clip_mb = r.integer("MAX_CLIP_MB", 2, 1, 8)
    if clip_mb * 4 > cache_mb:
        r.problems.append(("MAX_CLIP_MB", "too_large_for_cache"))
    static = r.text("STATIC_DIR")
    settings = Settings(
        blind_password=blind,
        host_password=host_pw,
        bridge_secret=bridge,
        domain=domain,
        trusted_proxies=_proxies(r),
        log_level=r.choice(  # type: ignore[arg-type]
            "LOG_LEVEL", "DEBUG" if dev else "INFO", ("DEBUG", "INFO", "WARNING", "ERROR")
        ),
        log_format=r.choice("LOG_FORMAT", "text", ("text", "json")),  # type: ignore[arg-type]
        log_track_names=r.boolean("LOG_TRACK_NAMES", default=False),
        max_players=r.integer("MAX_PLAYERS", 20, 2, 100),
        clip_min_s=clip_min,
        clip_max_s=clip_max,
        clip_format=ClipFormat(r.choice("CLIP_FORMAT", "aac", ("aac", "opus"))),
        clip_bitrate=int(r.choice("CLIP_BITRATE", "128", ("96", "128", "160", "192"))),
        audio_cache_mb=cache_mb,
        max_clip_mb=clip_mb,
        ready_timeout_s=r.integer("READY_TIMEOUT_S", 10, 3, 60),
        answer_max_chars=r.integer("ANSWER_MAX_CHARS", 200, 20, 200),
        near_tie_ms=r.integer("NEAR_TIE_MS", 300, 0, 5000),
        session_idle_ttl_h=r.integer("SESSION_IDLE_TTL_H", 24, 1, 168),
        dev_mode=dev,
        static_dir=Path(static) if static else None,
        host=r.text("BIND_HOST") or "0.0.0.0",  # noqa: S104
        port=r.integer("PORT", 8000, 1, 65535),
        warnings=tuple(r.warnings),
        state_dir=Path(r.text("STATE_DIR") or ".local/state"),
    )
    if r.problems:
        raise ConfigError(r.problems)
    return settings


def to_core_config(settings: Settings) -> CoreConfig:
    return CoreConfig(
        max_players=settings.max_players,
        clip_min_s=settings.clip_min_s,
        clip_max_s=settings.clip_max_s,
        clip_format=settings.clip_format,
        bitrate_kbps=settings.clip_bitrate,
        max_clip_bytes=settings.max_clip_mb * 1024 * 1024,
        answer_max_chars=settings.answer_max_chars,
        near_tie_ms=settings.near_tie_ms,
        ready_timeout_ms=settings.ready_timeout_s * 1000,
    )
