"""HTTP request and response bodies (spec §8.1)."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from openblindysir_protocol.base import BridgeId, InboundModel, OutboundModel, PlayerId, TrackId
from openblindysir_protocol.enums import BridgeState, HostMode, Role
from openblindysir_protocol.errors import ErrorCode
from openblindysir_protocol.metadata import MusicalMetadata
from openblindysir_protocol.settings import SourceSelection
from openblindysir_protocol.themes import ThemeFilter

_Secret = Annotated[str, StringConstraints(min_length=1, max_length=256)]


class ConfirmRequest(InboundModel):
    confirm: Annotated[bool, Field(strict=True)]


class JoinRequest(InboundModel):
    password: _Secret
    nickname: Annotated[str, StringConstraints(min_length=1, max_length=64)]  # raw


class JoinResponse(OutboundModel):
    player_id: PlayerId
    nickname: str
    role: Role


class SessionResponse(OutboundModel):
    player_id: PlayerId
    nickname: str
    role: Role
    host_mode: HostMode | None
    protocol: int
    server_version: str
    epoch: str


class RecoveryRequest(InboundModel):
    password: _Secret
    code: Annotated[str, StringConstraints(pattern=r"^[A-Z2-9]{6}$")]


class RecoveryCode(OutboundModel):
    code: str


class HostElevateRequest(InboundModel):
    host_password: _Secret


class HostElevateResponse(OutboundModel):
    role: Literal["host"]
    host_mode: HostMode


class OkResponse(OutboundModel):
    ok: Literal[True]


class ErrorResponse(OutboundModel):
    error: ErrorCode


class FolderNode(OutboundModel):
    """Folder tree node; folders only, NEVER a file name."""

    name: str
    prefix: str  # value for SourceSelection.folder_prefix ("" = root)
    track_count: int  # recursive, from the catalogue only
    children: list["FolderNode"]
    fresh_count: int | None = None
    available_count: int | None = None


class LibraryIssue(OutboundModel):
    bridge_id: BridgeId
    filename: str
    folder: str
    code: str


class LibraryBridge(OutboundModel):
    bridge_id: BridgeId
    name: str
    online: bool
    track_count: int
    root: FolderNode
    scanned_folders: list[str] = Field(default_factory=lambda: [""])
    source_error: str | None = None


class LibraryTrack(OutboundModel):
    genres: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    metadata_revision: int = 0
    cleared_fields: list[str] = Field(default_factory=list)
    missing_references: list[str] = Field(default_factory=list)
    aliases: dict[str, list[str]] | None = None
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    linked_to: list[str] = Field(default_factory=list)
    consumption: str = "available"
    bridge_name: str = ""
    duration_ms: int | None = None
    played: bool = False
    reserved: bool = False
    in_pool: bool = True
    bridge_id: BridgeId
    track_id: TrackId
    filename: str
    folder: str
    ext: str
    available: bool
    title: str | None = None
    artist: str | None = None
    featuring: str | None = None
    album: str | None = None
    year: int | None = None


class LibrarySearch(OutboundModel):
    total: int
    tracks: list[LibraryTrack]
    tags: list[str] = Field(default_factory=list)
    linked_to: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)


class SelectionPreviewRequest(InboundModel):
    sources: Annotated[list[SourceSelection], Field(max_length=64)]
    selection_filter: ThemeFilter = Field(default_factory=ThemeFilter)
    scoring_criteria: Annotated[
        list[Literal["title", "artist", "album", "year", "featuring"]], Field(max_length=5)
    ] = Field(default_factory=list)
    allow_repeats: bool = False


class SelectionPreview(OutboundModel):
    matching: int
    available: int
    fresh: int
    unclassified: int
    genres: list[str]
    languages: list[str]
    tags: list[str]
    linked_to: list[str]
    years: list[int]
    examples: list[LibraryTrack]
    reference_eligible: int = 0
    reference_ready: int = 0
    missing_by_criterion: dict[str, int] = Field(default_factory=dict)
    reference_issues: list[LibraryTrack] = Field(default_factory=list)


class SourceUpdate(InboundModel):
    bridge_id: BridgeId
    folders: Annotated[list[str], Field(max_length=64)] | None = None


class MetadataEdit(InboundModel):
    expected_revision: Annotated[int, Field(ge=0)] | None = None
    bridge_id: BridgeId
    track_id: TrackId
    metadata: MusicalMetadata


class LibraryResponse(OutboundModel):
    bridges: list[LibraryBridge]
    issues: list[LibraryIssue] = Field(default_factory=list)


class HealthResponse(OutboundModel):
    status: Literal["ok"]
    bridge: BridgeState | None  # filled only in DEV_MODE
