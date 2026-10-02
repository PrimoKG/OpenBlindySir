"""Time values for the game core.

The core never reads a clock: every command is dispatched with an ``Instant`` read by the
shell at handler entry (spec §6.3). ``MonotonicClock`` is the production source.
"""

import time
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True, order=True)
class Instant:
    """A point in time: server monotonic milliseconds plus wall-clock milliseconds."""

    mono_ms: int
    wall_ms: int  # UTC epoch ms, for display, export and ScoreEvent.at only


class Clock(Protocol):
    def now(self) -> Instant: ...

    def mono_ms_precise(self) -> float: ...


class MonotonicClock:
    """Production clock based on ``time.monotonic_ns`` (same base as asyncio's loop.time())."""

    def now(self) -> Instant:
        return Instant(time.monotonic_ns() // 1_000_000, time.time_ns() // 1_000_000)

    def mono_ms_precise(self) -> float:
        return time.monotonic_ns() / 1_000_000


class FakeClock:
    """Manually driven clock for tests; never goes backwards."""

    def __init__(self, mono_ms: int = 1_000_000, wall_ms: int = 1_790_000_000_000) -> None:
        self._mono = mono_ms
        self._wall = wall_ms

    def now(self) -> Instant:
        return Instant(self._mono, self._wall)

    def mono_ms_precise(self) -> float:
        return float(self._mono)

    def advance(self, ms: int) -> Instant:
        if ms < 0:
            raise AssertionError("FakeClock cannot go backwards")
        self._mono += ms
        self._wall += ms
        return self.now()

    def set(self, mono_ms: int) -> Instant:
        return self.advance(mono_ms - self._mono)
