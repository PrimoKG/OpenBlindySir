"""Bridge ↔ server messages (spec §8.3) and the catalogue upload body.

Server → Bridge messages also inherit ``InboundModel``: the Bridge receives them from a peer
it does not trust (spec §2 principle 6). The Bridge parses ONLY ``ServerToBridge``, the
exhaustive list WELCOME / PREPARE / CANCEL / PING (spec §11).
"""

import posixpath
from typing import Annotated, Final, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from openblindysir_protocol.base import (
    BridgeId,
    InboundModel,
    JobId,
    Sha256Hex,
    TrackId,
    UploadToken,
)
from openblindysir_protocol.enums import ClipFormat, JobFailureCode, JobStage
from openblindysir_protocol.settings import check_relative_path

UPLOAD_SHA256_HEADER: Final = "X-Content-SHA256"
CATALOG_TOKEN_HEADER: Final = "X-Catalog-Token"  # noqa: S105 - header name, not a token
CATALOG_MAX_GZIP_BYTES: Final = 8 * 1024 * 1024
CATALOG_MAX_RAW_BYTES: Final = 32 * 1024 * 1024
CATALOG_MAX_TRACKS: Final = 200_000
UPLOAD_TOKEN_TTL_S: Final = 120
BRIDGE_HEARTBEAT_S: Final = 15
BRIDGE_DEAD_S: Final = 45

_Version = Annotated[str, StringConstraints(pattern=r"^[0-9A-Za-z.+-]{1,32}$")]
_Count = Annotated[int, Field(ge=0, le=CATALOG_MAX_TRACKS)]
_Echo = Annotated[float, Field(ge=0, le=1e13)]


class BridgeHello(InboundModel):
    t: Literal["HELLO"]
    bridge_id: BridgeId
    name: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    version: _Version
    protocol: Annotated[int, Field(ge=0, le=10_000)]
    catalog_hash: Sha256Hex
    track_count: _Count
    formats: Annotated[list[ClipFormat], Field(min_length=1, max_length=4)]


class BridgeLimits(InboundModel):
    clip_min_s: Annotated[float, Field(ge=1, le=600)]
    clip_max_s: Annotated[float, Field(ge=1, le=600)]
    max_clip_bytes: Annotated[int, Field(ge=1, le=64 * 1024 * 1024)]


class Welcome(InboundModel):
    """Format and limits requested by the server; the Bridge caps them to its own maxima."""

    t: Literal["WELCOME"]
    clip_format: ClipFormat
    bitrate: Annotated[int, Field(ge=32, le=512)]  # kbps
    limits: BridgeLimits
    catalog_needed: bool
    catalog_upload_token: UploadToken | None = None

    @model_validator(mode="after")
    def _token_iff_needed(self) -> "Welcome":
        if self.catalog_needed != (self.catalog_upload_token is not None):
            raise ValueError("catalog_upload_token is present iff catalog_needed")
        return self


class CatalogChanged(InboundModel):
    t: Literal["CATALOG_CHANGED"]
    catalog_hash: Sha256Hex


class Prepare(InboundModel):
    """The only business command: no path, no FFmpeg argument (spec §8.3)."""

    t: Literal["PREPARE"]
    job_id: JobId
    track_id: TrackId
    start_fraction: Annotated[float, Field(ge=0, lt=1)]
    duration: Annotated[float, Field(gt=0, le=600)]  # seconds; capped by the Bridge
    # A path only: the Bridge joins it to its OWN configured server URL.
    upload_url: Annotated[
        str, StringConstraints(pattern=r"^/api/bridge/assets/a_[A-Za-z0-9_-]{22}$")
    ]
    upload_token: UploadToken


class Cancel(InboundModel):
    t: Literal["CANCEL"]
    job_id: JobId


class JobProgress(InboundModel):
    t: Literal["JOB_PROGRESS"]
    job_id: JobId
    stage: JobStage


class Tags(InboundModel):
    title: Annotated[str, StringConstraints(max_length=200)] | None = None
    artist: Annotated[str, StringConstraints(max_length=200)] | None = None


class JobDone(InboundModel):
    t: Literal["JOB_DONE"]
    job_id: JobId
    actual_start: Annotated[float, Field(ge=0, le=86_400)]
    clip_duration: Annotated[float, Field(gt=0, le=600)]
    track_duration: Annotated[float, Field(gt=0, le=86_400)]
    bytes: Annotated[int, Field(gt=0, le=64 * 1024 * 1024)]
    sha256: Sha256Hex
    tags: Tags | None = None  # used for the reveal only


class JobFailed(InboundModel):
    t: Literal["JOB_FAILED"]
    job_id: JobId
    code: JobFailureCode  # never a path


class BridgePing(InboundModel):
    t: Literal["PING"]
    c: _Echo


class BridgePong(InboundModel):
    t: Literal["PONG"]
    c: _Echo


BridgeToServer = Annotated[
    BridgeHello | CatalogChanged | JobProgress | JobDone | JobFailed | BridgePong,
    Field(discriminator="t"),
]
ServerToBridge = Annotated[Welcome | Prepare | Cancel | BridgePing, Field(discriminator="t")]


class CatalogEntry(InboundModel):
    track_id: TrackId
    relpath: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    folder: Annotated[str, StringConstraints(max_length=1024)]
    ext: Annotated[str, StringConstraints(pattern=r"^\.[a-z0-9]{1,6}$")]
    size: Annotated[int, Field(ge=0)]

    @field_validator("relpath")
    @classmethod
    def _valid_relpath(cls, value: str) -> str:
        return check_relative_path(value, allow_empty=False)

    @model_validator(mode="after")
    def _folder_is_parent(self) -> "CatalogEntry":
        if self.folder != posixpath.dirname(self.relpath):
            raise ValueError("folder must be the parent of relpath")
        return self


class CatalogUpload(InboundModel):
    """Body (gzip JSON) of ``PUT /api/bridge/catalog``."""

    bridge_id: BridgeId
    catalog_hash: Sha256Hex
    entries: Annotated[list[CatalogEntry], Field(max_length=CATALOG_MAX_TRACKS)]
