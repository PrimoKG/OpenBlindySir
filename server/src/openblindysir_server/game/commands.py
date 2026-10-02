"""Commands: the only input of the game core (dispatched with the Instant of reception)."""

from collections.abc import Mapping
from dataclasses import dataclass

from openblindysir_protocol.bridge import JobDone
from openblindysir_protocol.client import AnswerDraft, AnswerSubmit, AudioStatus, PlaybackReport
from openblindysir_protocol.enums import JobFailureCode, JobStage
from openblindysir_protocol.host_commands import HostCommandVariant
from openblindysir_server.game.state import CatalogEntryData

# --- players and connections ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Join:
    nickname: str  # raw; Outcome.value is the new player id


@dataclass(frozen=True, slots=True)
class Leave:
    player_id: str


@dataclass(frozen=True, slots=True)
class Connected:
    player_id: str
    client_version: str


@dataclass(frozen=True, slots=True)
class Disconnected:
    player_id: str


@dataclass(frozen=True, slots=True)
class ElevateHost:
    player_id: str  # the host password is checked by the shell


@dataclass(frozen=True, slots=True)
class AudioStatusIn:
    player_id: str
    msg: AudioStatus


@dataclass(frozen=True, slots=True)
class PlaybackReportIn:
    player_id: str
    msg: PlaybackReport


@dataclass(frozen=True, slots=True)
class DraftIn:
    player_id: str
    msg: AnswerDraft


@dataclass(frozen=True, slots=True)
class SubmitIn:
    """Dispatched with the instant read right after receiving the frame (spec §6.3)."""

    player_id: str
    msg: AnswerSubmit


@dataclass(frozen=True, slots=True)
class HostIn:
    player_id: str
    msg: HostCommandVariant


# --- Bridge ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BridgeConnected:
    bridge_id: str
    name: str
    version: str
    catalog_hash: str
    track_count: int


@dataclass(frozen=True, slots=True)
class BridgeDisconnected:
    bridge_id: str


@dataclass(frozen=True, slots=True)
class CatalogLoaded:
    bridge_id: str
    bridge_name: str
    catalog_hash: str
    entries: Mapping[str, CatalogEntryData]


@dataclass(frozen=True, slots=True)
class JobProgressIn:
    job_id: str
    stage: JobStage


@dataclass(frozen=True, slots=True)
class UploadVerified:
    asset_id: str
    size: int
    sha256: str
    mime: str


@dataclass(frozen=True, slots=True)
class UploadRejected:
    asset_id: str


@dataclass(frozen=True, slots=True)
class JobDoneIn:
    msg: JobDone


@dataclass(frozen=True, slots=True)
class JobFailedIn:
    job_id: str
    code: JobFailureCode


@dataclass(frozen=True, slots=True)
class CacheRefused:
    asset_id: str


@dataclass(frozen=True, slots=True)
class AssetEvicted:
    """The shell dropped the bytes of a retained asset because the cache was full."""

    asset_id: str


# --- time --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Tick:
    pass


Command = (
    Join
    | Leave
    | Connected
    | Disconnected
    | ElevateHost
    | AudioStatusIn
    | PlaybackReportIn
    | DraftIn
    | SubmitIn
    | HostIn
    | BridgeConnected
    | BridgeDisconnected
    | CatalogLoaded
    | JobProgressIn
    | UploadVerified
    | UploadRejected
    | JobDoneIn
    | JobFailedIn
    | CacheRefused
    | AssetEvicted
    | Tick
)
