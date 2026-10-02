"""Base models and constrained aliases shared by every protocol message."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints


class InboundModel(BaseModel):
    """Everything that ENTERS a component from an untrusted peer.

    ``extra="forbid"`` rejects any undeclared field (e.g. a client timestamp in
    ANSWER_SUBMIT, spec §6.3) and ``strict=True`` refuses type coercion.
    """

    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, allow_inf_nan=False, str_max_length=4096
    )


class OutboundModel(BaseModel):
    """Everything a component EMITS.

    ``extra="forbid"`` too: an undeclared field cannot be added at construction (anti-leak
    guard). Fields have no defaults, so every builder passes every field, None included.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        json_schema_serialization_defaults_required=True,
    )


def _reject_zero(value: int) -> int:
    if value == 0:
        raise ValueError("must not be zero")
    return value


PlayerId = Annotated[str, StringConstraints(pattern=r"^p_[A-Za-z0-9_-]{4,32}$")]
RoundId = Annotated[str, StringConstraints(pattern=r"^r_[A-Za-z0-9_-]{4,32}$")]
PlayId = Annotated[str, StringConstraints(pattern=r"^pl_[A-Za-z0-9_-]{4,32}$")]
# 128 random bits, unrelated to track_id (spec §12 anti-spoiler).
AssetId = Annotated[str, StringConstraints(pattern=r"^a_[A-Za-z0-9_-]{22}$")]
JobId = Annotated[str, StringConstraints(pattern=r"^j_[A-Za-z0-9_-]{4,32}$")]
GameId = Annotated[str, StringConstraints(pattern=r"^g_[A-Za-z0-9_-]{4,32}$")]
TrackId = Annotated[str, StringConstraints(pattern=r"^t_[0-9a-f]{16}$")]
BridgeId = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]
OpId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{8,64}$")]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
# 256 random bits, URL-safe base64 without padding.
UploadToken = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{43}$")]

POINTS_BOUND = 1000
Points = Annotated[int, Field(ge=-POINTS_BOUND, le=POINTS_BOUND)]
NonZeroPoints = Annotated[
    int, Field(ge=-POINTS_BOUND, le=POINTS_BOUND), AfterValidator(_reject_zero)
]
# Server monotonic clock, in milliseconds.
ServerMs = Annotated[int, Field(ge=0, le=2**53 - 1)]
AnswerText = Annotated[str, StringConstraints(max_length=200)]
NoteText = Annotated[str, StringConstraints(max_length=120)]
