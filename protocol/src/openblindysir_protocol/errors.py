"""Error codes, WebSocket close codes and rejection reasons (closed lists)."""

from enum import IntEnum, StrEnum


class ErrorCode(StrEnum):
    """Codes of ``ERROR{code}`` (WebSocket) and of HTTP error bodies ``{error}``."""

    INVALID_MESSAGE = "invalid_message"
    HELLO_REQUIRED = "hello_required"
    PROTOCOL_MISMATCH = "protocol_mismatch"
    NOT_HOST = "not_host"
    INVALID_STATE = "invalid_state"
    STALE_COMMAND = "stale_command"
    UNKNOWN_PLAYER = "unknown_player"
    INVALID_ARGS = "invalid_args"
    NO_SOURCES = "no_sources"
    BRIDGE_OFFLINE = "bridge_offline"
    NO_COMPETITORS = "no_competitors"
    POOL_EXHAUSTED = "pool_exhausted"
    UNREVIEWED_SCORES = "unreviewed_scores"
    SCORES_FROZEN = "scores_frozen"
    RATE_LIMITED = "rate_limited"
    MESSAGE_TOO_LARGE = "message_too_large"
    BAD_PASSWORD = "bad_password"  # noqa: S105 - error code, not a password
    NICKNAME_INVALID = "nickname_invalid"
    NICKNAME_TAKEN = "nickname_taken"
    GAME_FULL = "game_full"
    ALREADY_JOINED = "already_joined"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN_ORIGIN = "forbidden_origin"
    JSON_REQUIRED = "json_required"
    NOT_FOUND = "not_found"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    UPLOAD_REJECTED = "upload_rejected"
    JOIN_LOCKED = "join_locked"
    RECOVERY_INVALID = "recovery_invalid"
    REVIEW_UNAVAILABLE = "review_unavailable"


class CloseCode(IntEnum):
    """Application WebSocket close codes (exactly spec §8.2)."""

    SUPERSEDED = 4001
    KICKED = 4003
    SESSION_ENDED = 4004


class AnswerRejectReason(StrEnum):
    CLOSED = "closed"
    NOT_OPEN = "not_open"
    WRONG_ROUND = "wrong_round"
    ALREADY_LOCKED = "already_locked"
    NOT_PARTICIPANT = "not_participant"
    EMPTY = "empty"
    TOO_LONG = "too_long"


class StartBlocker(StrEnum):
    """Reasons why ``start_game`` is currently impossible (shown in LOBBY)."""

    NO_SOURCES = "no_sources"
    BRIDGE_OFFLINE = "bridge_offline"
    NO_COMPETITORS = "no_competitors"
    POOL_EXHAUSTED = "pool_exhausted"
