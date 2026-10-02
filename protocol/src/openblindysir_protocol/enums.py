"""Enumerations of the wire protocol (states upper case as in the spec, kinds lower case)."""

from enum import StrEnum


class GamePhase(StrEnum):
    LOBBY = "LOBBY"
    IN_GAME = "IN_GAME"
    FINAL_SCORE_REVIEW = "FINAL_SCORE_REVIEW"
    FINAL_RESULTS = "FINAL_RESULTS"


class RoundState(StrEnum):
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    LOADING = "LOADING"
    COUNTDOWN = "COUNTDOWN"
    OPEN = "OPEN"
    REVIEW = "REVIEW"
    REVEALED = "REVEALED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AssetState(StrEnum):
    REQUESTED = "REQUESTED"
    ENCODING = "ENCODING"
    UPLOADING = "UPLOADING"
    STORED = "STORED"
    EVICTED = "EVICTED"
    FAILED = "FAILED"


class AssetFailureCode(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    DECODE_ERROR = "DECODE_ERROR"
    TOO_SHORT = "TOO_SHORT"
    TIMEOUT = "TIMEOUT"
    BRIDGE_OFFLINE = "BRIDGE_OFFLINE"
    INVALID_UPLOAD = "INVALID_UPLOAD"
    CANCELLED = "CANCELLED"


class JobFailureCode(StrEnum):
    """Failure codes a Bridge may report; never a path (spec §8.3)."""

    NOT_FOUND = "NOT_FOUND"
    DECODE_ERROR = "DECODE_ERROR"
    TOO_SHORT = "TOO_SHORT"
    TIMEOUT = "TIMEOUT"
    INVALID_UPLOAD = "INVALID_UPLOAD"
    CANCELLED = "CANCELLED"
    QUEUE_FULL = "QUEUE_FULL"


class JobStage(StrEnum):
    PROBING = "probing"
    ENCODING = "encoding"
    UPLOADING = "uploading"


class ConnectionState(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    REMOVED = "REMOVED"


class AudioState(StrEnum):
    LOCKED = "LOCKED"
    IDLE = "IDLE"
    LOADING = "LOADING"
    READY = "READY"
    PLAYING = "PLAYING"
    ERROR = "ERROR"


class AudioErrorCode(StrEnum):
    FETCH_FAILED = "FETCH_FAILED"
    DECODE_FAILED = "DECODE_FAILED"
    CONTEXT_FAILED = "CONTEXT_FAILED"


class AnswerStatus(StrEnum):
    NONE = "NONE"
    DRAFT = "DRAFT"
    LOCKED = "LOCKED"
    CAPTURED = "CAPTURED"


class Role(StrEnum):
    PLAYER = "player"
    HOST = "host"


class HostMode(StrEnum):
    PLAYER = "player"
    MC = "mc"


class ScoreKind(StrEnum):
    ROUND = "round"
    ADJUSTMENT = "adjustment"
    FINAL_ADJUSTMENT = "final_adjustment"
    REVOKE = "revoke"


class EndGameMode(StrEnum):
    SCORE = "score"
    ABANDON = "abandon"


class CloseReason(StrEnum):
    """Why the answers of a round were closed."""

    DEADLINE = "deadline"
    ALL_LOCKED = "all_locked"
    HOST = "host"
    END_GAME = "end_game"


class CancelReason(StrEnum):
    SKIPPED = "skipped"
    END_GAME = "end_game"
    UNDO_DISCARDED = "undo_discarded"


class BridgeState(StrEnum):
    OFFLINE = "OFFLINE"
    CONNECTED = "CONNECTED"
    SYNCING = "SYNCING"
    ONLINE = "ONLINE"
    REJECTED = "REJECTED"


class ClipFormat(StrEnum):
    AAC = "aac"
    OPUS = "opus"


class AssetRole(StrEnum):
    PREVIOUS = "previous"
    CURRENT = "current"
    NEXT = "next"
    NEXT2 = "next2"


class HostWarning(StrEnum):
    BRIDGE_OFFLINE = "bridge_offline"
    POOL_EXHAUSTED = "pool_exhausted"
    CACHE_FULL = "cache_full"
    TRACK_REPLACED = "track_replaced"
    ROUND_FAILED = "round_failed"


class AnswerAckStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class BrowserFamily(StrEnum):
    """Coarse browser family for diagnostics only (spec §21); never a version."""

    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    SAFARI = "safari"
    IOS_WEBKIT = "ios_webkit"
    OTHER = "other"
