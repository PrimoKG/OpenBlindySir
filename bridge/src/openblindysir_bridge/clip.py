"""Pure clip rules: the Bridge's own bounds always win (the server is untrusted, §11)."""

from dataclasses import dataclass

from openblindysir_protocol.bridge import Prepare, Welcome
from openblindysir_protocol.enums import ClipFormat

BRIDGE_CLIP_MIN_S = 5.0
BRIDGE_CLIP_MAX_S = 60.0
BRIDGE_MAX_CLIP_BYTES = 4 * 1024 * 1024
ALLOWED_BITRATES = (96, 128, 160, 192)
MIN_TRACK_S = 8.0
MAX_FRACTION = 0.999


class TooShortError(Exception):
    """The track is shorter than MIN_TRACK_S."""


@dataclass(frozen=True, slots=True)
class ClipRequest:
    duration_s: float
    fraction: float
    bitrate_kbps: int
    max_bytes: int
    clip_format: ClipFormat


def clamp_request(prepare: Prepare, welcome: Welcome) -> ClipRequest:
    """Bound everything the server asks, even against an inverted or absurd WELCOME."""
    lo = min(max(welcome.limits.clip_min_s, BRIDGE_CLIP_MIN_S), BRIDGE_CLIP_MAX_S)
    hi = min(max(welcome.limits.clip_max_s, lo), BRIDGE_CLIP_MAX_S)
    duration = min(max(prepare.duration, lo), hi)
    fraction = min(max(prepare.start_fraction, 0.0), MAX_FRACTION)
    eligible = [b for b in ALLOWED_BITRATES if b <= welcome.bitrate]
    bitrate = max(eligible) if eligible else ALLOWED_BITRATES[0]
    max_bytes = min(BRIDGE_MAX_CLIP_BYTES, welcome.limits.max_clip_bytes)
    return ClipRequest(duration, fraction, bitrate, max_bytes, welcome.clip_format)


def compute_start(track_s: float, clip_s: float, fraction: float) -> tuple[float, float]:
    """Start point (spec §10): ``(start, duration)``, ``0 <= start``, ``start + duration <= track``.

    The valid window goes from ``max(10 s, 8 %)`` to ``track − clip − max(20 s, 10 %)``; an
    empty window starts at a third of the track; a track shorter than the clip is played
    whole; a track under 8 s is refused.
    """
    if track_s < MIN_TRACK_S:
        raise TooShortError
    if track_s <= clip_s:
        return 0.0, track_s
    lo = max(10.0, 0.08 * track_s)
    hi = track_s - clip_s - max(20.0, 0.10 * track_s)
    start = min(track_s / 3, track_s - clip_s) if hi < lo else lo + fraction * (hi - lo)
    return max(0.0, start), clip_s
