"""Answers (spec §6.2) and server-side timing (spec §6.3, ADR 0003).

``elapsed = received_at − official_start_at`` with the instant read by the shell right after
receiving the frame; no client timestamp, no RTT compensation. Speed is measured and shown,
never converted into points.
"""

from openblindysir_protocol.enums import AnswerAckStatus, AnswerStatus, RoundState
from openblindysir_protocol.errors import AnswerRejectReason
from openblindysir_protocol.text import normalize_answer
from openblindysir_server.game import commands as c
from openblindysir_server.game.clock import Instant
from openblindysir_server.game.effects import EffectSink, SendAck
from openblindysir_server.game.state import (
    Answer,
    Round,
    SessionState,
    current_round,
    is_participant,
)

NOT_OPEN_STATES = frozenset(
    {RoundState.QUEUED, RoundState.PREPARING, RoundState.LOADING, RoundState.COUNTDOWN}
)


def handle_draft(s: SessionState, cmd: c.DraftIn, at: Instant, fx: EffectSink) -> None:
    """Invisible draft; refused silently. Never bumps the version (only its author sees it)."""
    del fx
    p = s.players.get(cmd.player_id)
    r = current_round(s.game)
    if p is None or not is_participant(p) or r is None:
        return
    if (
        r.id != cmd.msg.round_id
        or r.state is not RoundState.OPEN
        or (r.paused_at is not None and at.mono_ms >= r.paused_at)
    ):
        return
    answer = r.answers.get(p.id)
    if answer is not None and answer.status in (AnswerStatus.LOCKED, AnswerStatus.CAPTURED):
        return
    try:
        text = normalize_answer(cmd.msg.text, s.config.answer_max_chars)
    except ValueError:
        return
    if answer is None:
        answer = r.answers[p.id] = Answer(player_id=p.id)
    answer.draft_text = text
    answer.draft_last_changed_at = at.mono_ms
    answer.status = AnswerStatus.DRAFT if text else AnswerStatus.NONE


def _reject_reason(s: SessionState, cmd: c.SubmitIn, at: Instant) -> AnswerRejectReason | None:
    p = s.players.get(cmd.player_id)
    if p is None or not is_participant(p):
        return AnswerRejectReason.NOT_PARTICIPANT
    r = current_round(s.game)
    known = {round_.id for round_ in s.game.rounds}
    if cmd.msg.round_id not in known:
        return AnswerRejectReason.WRONG_ROUND
    if r is None or cmd.msg.round_id != r.id:
        return AnswerRejectReason.CLOSED
    if r.state in NOT_OPEN_STATES:
        return AnswerRejectReason.NOT_OPEN
    if r.paused_at is not None and at.mono_ms >= r.paused_at:
        return AnswerRejectReason.NOT_OPEN
    if r.state is not RoundState.OPEN:
        return AnswerRejectReason.CLOSED
    answer = r.answers.get(p.id)
    if answer is not None and answer.status is AnswerStatus.LOCKED:
        return AnswerRejectReason.ALREADY_LOCKED
    try:
        text = normalize_answer(cmd.msg.text, s.config.answer_max_chars)
    except ValueError:
        return AnswerRejectReason.TOO_LONG
    if not text:
        return AnswerRejectReason.EMPTY
    return None


def handle_submit(s: SessionState, cmd: c.SubmitIn, at: Instant, fx: EffectSink) -> None:
    """Definitive validation, always acknowledged; the ack carries no timing data."""
    reason = _reject_reason(s, cmd, at)
    if reason is not None:
        fx.add(SendAck(cmd.player_id, cmd.msg.round_id, AnswerAckStatus.REJECTED, reason))
        return
    r = current_round(s.game)
    assert r is not None
    assert r.official_start_at is not None
    lock_answer(s, r, cmd.player_id, normalize_answer(cmd.msg.text), at)
    answer = r.answers[cmd.player_id]
    fx.add(SendAck(cmd.player_id, r.id, AnswerAckStatus.ACCEPTED, None))
    fx.log(
        "answer_locked",
        player_id=cmd.player_id,
        order=answer.order,
        elapsed_ms=answer.elapsed_ms,
        len=len(answer.text or ""),
    )


def lock_answer(s: SessionState, r: Round, player_id: str, text: str, at: Instant) -> None:
    assert r.official_start_at is not None
    answer = r.answers.get(player_id)
    if answer is None:
        answer = r.answers[player_id] = Answer(player_id=player_id)
    locked = [a for a in r.answers.values() if a.status is AnswerStatus.LOCKED]
    order = len(locked) + 1
    previous = next((a for a in locked if a.order == order - 1), None)
    answer.status = AnswerStatus.LOCKED
    answer.text = text
    answer.received_at = at.mono_ms
    answer.received_at_wall_ms = at.wall_ms
    answer.elapsed_ms = at.mono_ms - r.official_start_at - r.paused_total_ms
    answer.order = order
    answer.near_tie = (
        previous is not None
        and previous.elapsed_ms is not None
        and answer.elapsed_ms - previous.elapsed_ms < s.config.near_tie_ms
    )
    s.touched = True


def capture_drafts(r: Round) -> tuple[int, int]:
    """At close, a non-empty unvalidated draft becomes CAPTURED (no rank, no time)."""
    locked = captured = 0
    for answer in r.answers.values():
        if answer.status is AnswerStatus.LOCKED:
            locked += 1
        elif answer.status is AnswerStatus.DRAFT and answer.draft_text:
            answer.status = AnswerStatus.CAPTURED
            answer.text = answer.draft_text
            captured += 1
        elif answer.status is AnswerStatus.DRAFT:
            answer.status = AnswerStatus.NONE
    return locked, captured
