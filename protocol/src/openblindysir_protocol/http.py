"""HTTP request and response bodies (spec §8.1)."""

from typing import Annotated, Literal

from pydantic import StringConstraints

from openblindysir_protocol.base import BridgeId, InboundModel, OutboundModel, PlayerId
from openblindysir_protocol.enums import BridgeState, HostMode, Role
from openblindysir_protocol.errors import ErrorCode

_Secret = Annotated[str, StringConstraints(min_length=1, max_length=256)]


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


class LibraryBridge(OutboundModel):
    bridge_id: BridgeId
    name: str
    online: bool
    track_count: int
    root: FolderNode


class LibraryResponse(OutboundModel):
    bridges: list[LibraryBridge]


class HealthResponse(OutboundModel):
    status: Literal["ok"]
    bridge: BridgeState | None  # filled only in DEV_MODE
