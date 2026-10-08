"""Explicit compatibility information for the current development protocol."""

import re

from openblindysir_protocol.base import OutboundModel
from openblindysir_protocol.version import PROTOCOL_MAX, PROTOCOL_MIN, PROTOCOL_VERSION


class Compatibility(OutboundModel):
    server_version: str
    protocol: int = PROTOCOL_VERSION
    protocol_min: int = PROTOCOL_MIN
    protocol_max: int = PROTOCOL_MAX
    snapshot_format: int = 9
    history_format: int = 2


def mismatch_reason() -> str:
    return f"protocol_mismatch;required={PROTOCOL_MIN}..{PROTOCOL_MAX}"


def required_range(reason: str) -> tuple[int, int] | None:
    """Extract only bounded integers; never echo untrusted close text in the terminal."""
    match = re.fullmatch(r"protocol_mismatch;required=(\d{1,5})\.\.(\d{1,5})", reason)
    if match is None:
        return None
    low, high = map(int, match.groups())
    return (low, high) if 0 <= low <= high else None
