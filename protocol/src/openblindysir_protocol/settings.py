"""Game settings, server limits and shared size constants."""

import unicodedata
from typing import Annotated, Final, Literal

from pydantic import Field, StringConstraints, field_validator

from openblindysir_protocol.base import BridgeId, InboundModel, OutboundModel
from openblindysir_protocol.enums import ClipFormat

WS_PLAYER_MAX_BYTES: Final = 16_384
WS_BRIDGE_MAX_BYTES: Final = 65_536
HTTP_JSON_MAX_BYTES: Final = 4_096
CLIENT_PING_INTERVAL_S: Final = 5
HEARTBEAT_OFFLINE_S: Final = 20


def check_relative_path(value: str, *, allow_empty: bool) -> str:
    """Validate a POSIX relative path: NFC, no leading/trailing "/", no ".", ".." or empty
    segment, no backslash nor NUL. Raises ValueError otherwise."""
    if value != unicodedata.normalize("NFC", value):
        raise ValueError("path must be NFC")
    if value == "":
        if allow_empty:
            return value
        raise ValueError("path must not be empty")
    if "\\" in value or ":" in value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("path must use '/' and contain no NUL")
    if value.startswith("/") or value.endswith("/"):
        raise ValueError("path must be relative without trailing '/'")
    if any(segment in {"", ".", ".."} for segment in value.split("/")):
        raise ValueError("path has an empty, '.' or '..' segment")
    return value


class SourceSelection(InboundModel):
    """A folder checked by the host; "" is the Bridge root, i.e. the whole library (§6.9)."""

    bridge_id: BridgeId
    folder_prefix: Annotated[str, StringConstraints(max_length=1024)]

    @field_validator("folder_prefix")
    @classmethod
    def _valid_prefix(cls, value: str) -> str:
        return check_relative_path(value, allow_empty=True)


class SourceView(OutboundModel):
    bridge_id: BridgeId
    folder_prefix: str


class GameSettings(OutboundModel):
    rounds: int
    clip_seconds: int
    answer_grace_s: int
    sources: list[SourceView]
    auto_start: bool
    prefetch_depth: int
    allow_repeats: bool
    answer_mode: str = "both"
    title_points: int = 1
    artist_points: int = 1
    instructions: str = ""
    captured_policy: str = "manual"
    normalize_audio: bool = True
    avoid_silence: bool = True
    balance_folders: bool = False


class SettingsPatch(InboundModel):
    """Arguments of ``HOST configure``: each given field is set (value semantics)."""

    rounds: Annotated[int, Field(ge=1, le=200)] | None = None
    # Narrowed to CLIP_MIN_S..CLIP_MAX_S by the core.
    clip_seconds: Annotated[int, Field(ge=5, le=60)] | None = None
    answer_grace_s: Annotated[int, Field(ge=0, le=120)] | None = None
    sources: Annotated[list[SourceSelection], Field(max_length=64)] | None = None
    auto_start: bool | None = None
    prefetch_depth: Annotated[int, Field(ge=1, le=2)] | None = None
    allow_repeats: bool | None = None
    answer_mode: Literal["title", "artist", "both", "custom"] | None = None
    title_points: Annotated[int, Field(ge=0, le=1000)] | None = None
    artist_points: Annotated[int, Field(ge=0, le=1000)] | None = None
    instructions: Annotated[str, StringConstraints(max_length=500)] | None = None
    captured_policy: Literal["manual", "zero"] | None = None
    normalize_audio: bool | None = None
    avoid_silence: bool | None = None
    balance_folders: bool | None = None


class ServerLimits(OutboundModel):
    max_players: int
    clip_min_s: int
    clip_max_s: int
    answer_max_chars: int
    near_tie_ms: int
    ready_timeout_s: int
    clip_format: ClipFormat
