"""Timed transitions, derived from the state and applied at their exact due instant."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum

from openblindysir_protocol.enums import CloseReason, RoundState
from openblindysir_server.game import assets, rounds, selection
from openblindysir_server.game.clock import Instant
from openblindysir_server.game.effects import EffectSink
from openblindysir_server.game.state import (
    IN_FLIGHT_ASSET_STATES,
    SessionState,
    active_play,
    current_round,
)


class DueKind(IntEnum):
    """Order of application when several transitions are due at the same instant."""

    COUNTDOWN_END = 0
    READY_TIMEOUT = 1
    ANSWER_DEADLINE = 2
    PLAY_END = 3
    JOB_TIMEOUT = 4
    RESUME_END = 5
    PAUSE_START = 6
    BRIDGE_WAIT = 7
    NEXT_ROUND = 8


@dataclass(frozen=True, slots=True, order=True)
class Due:
    at: int
    kind: DueKind
    ref: str


def pending(s: SessionState) -> list[Due]:
    dues: list[Due] = []
    r = current_round(s.game)
    if r is not None:
        if r.state is RoundState.REVIEW and r.auto_advance_at is not None and r.paused_at is None:
            dues.append(Due(r.auto_advance_at, DueKind.NEXT_ROUND, r.id))
        if r.state is RoundState.COUNTDOWN and r.official_start_at is not None:
            dues.append(Due(r.official_start_at, DueKind.COUNTDOWN_END, r.id))
        if r.state is RoundState.LOADING and r.ready_deadline is not None:
            dues.append(Due(r.ready_deadline, DueKind.READY_TIMEOUT, r.id))
        if r.state is RoundState.OPEN and r.deadline is not None and r.paused_at is None:
            dues.append(Due(r.deadline, DueKind.ANSWER_DEADLINE, r.id))
        if r.resume_at is not None:
            dues.append(Due(r.resume_at, DueKind.RESUME_END, r.id))
        if r.paused_at is not None and not r.pause_ready:
            dues.append(Due(r.paused_at, DueKind.PAUSE_START, r.id))
        play = active_play(r)
        if play is not None:
            dues.append(Due(play.ends_at, DueKind.PLAY_END, play.play_id))
    for asset in s.assets.values():
        if asset.state in IN_FLIGHT_ASSET_STATES:
            dues.append(Due(asset.job_deadline, DueKind.JOB_TIMEOUT, asset.asset_id))
    for slot in selection.live_slots(s):
        if slot.waiting_bridge and slot.bridge_wait_since is not None:
            dues.append(
                Due(slot.bridge_wait_since + assets.BRIDGE_WAIT_MS, DueKind.BRIDGE_WAIT, "")
            )
    return dues


def next_wakeup(s: SessionState) -> int | None:
    dues = pending(s)
    return min(due.at for due in dues) if dues else None


def apply(s: SessionState, due: Due, at: Instant, fx: EffectSink) -> None:
    r = current_round(s.game)
    if due.kind is DueKind.NEXT_ROUND and r is not None and r.id == due.ref:
        rounds.advance_round(s, r, at, fx)
        return
    if due.kind is DueKind.COUNTDOWN_END and r is not None:
        rounds.open_round(s, r)
    elif due.kind is DueKind.READY_TIMEOUT and r is not None:
        # spec §9.4: "au-delà, on démarre quand même", whatever auto_start says.
        rounds.begin_countdown(s, r, at, fx)
    elif due.kind is DueKind.ANSWER_DEADLINE and r is not None:
        rounds.close_round(s, r, at, CloseReason.DEADLINE, fx)
    elif due.kind is DueKind.PLAY_END and r is not None:
        r.ended_play_ids.add(due.ref)
        s.touched = True
    elif due.kind is DueKind.RESUME_END and r is not None:
        r.paused_at = None
        r.resume_at = None
        r.pause_offset_s = None
        s.touched = True
    elif due.kind is DueKind.PAUSE_START and r is not None:
        r.pause_ready = True
        s.touched = True
    elif due.kind is DueKind.JOB_TIMEOUT:
        asset = s.assets.get(due.ref)
        if asset is not None:
            assets.expire_job(s, asset, fx)
    elif due.kind is DueKind.BRIDGE_WAIT:
        assets.settle_slots(s, at, fx)


def advance_to(
    s: SessionState,
    at: Instant,
    fx: EffectSink,
    settle: Callable[[SessionState, Instant, EffectSink], None],
) -> None:
    """Apply every transition due at or before ``at``, each at its own due instant."""
    for _ in range(10_000):
        dues = pending(s)
        if not dues:
            return
        due = min(dues)
        if due.at > at.mono_ms:
            return
        due_instant = Instant(due.at, at.wall_ms - (at.mono_ms - due.at))
        apply(s, due, due_instant, fx)
        settle(s, due_instant, fx)
    raise AssertionError("timer loop did not converge")
