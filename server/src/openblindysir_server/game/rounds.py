"""Round machine (spec §7.2), ready check (§9.4), scoring of a round (§6.4–6.5)."""

from openblindysir_protocol.enums import (
    AnswerStatus,
    AssetFailureCode,
    AssetState,
    CancelReason,
    CloseReason,
    ConnectionState,
    RoundState,
    ScoreKind,
)
from openblindysir_protocol.errors import ErrorCode
from openblindysir_protocol.host_commands import (
    HostAddTime,
    HostClose,
    HostForceStart,
    HostNext,
    HostPublish,
    HostReplay,
    HostScoreDraft,
    HostSkip,
    HostStop,
    HostUndoPublish,
)
from openblindysir_server.game import assets, library, selection
from openblindysir_server.game.answers import capture_drafts
from openblindysir_server.game.clock import Instant
from openblindysir_server.game.effects import EffectSink, Play, SendPlay, SendStop
from openblindysir_server.game.permissions import rule_ok
from openblindysir_server.game.readiness import expected_ready, ready_ids
from openblindysir_server.game.rejections import require
from openblindysir_server.game.state import (
    Listen,
    Player,
    RevealInfo,
    Round,
    SessionState,
    Slot,
    active_play,
    active_players,
    clip_ms,
    current_round,
    is_participant,
    late_start_ms,
    revealed_count,
    undo_target,
)

# --- creation, failure, cancellation ------------------------------------------------------


def start_round(s: SessionState, at: Instant, fx: EffectSink) -> Round:
    """R0: a new current round. A FAILED or skipped round does not consume a number."""
    g = s.game
    if g.pipeline:
        slot = g.pipeline.popleft()
    else:
        ref = selection.take(s)
        slot = Slot(track_ref=ref, attempts=1 if ref is not None else 0)
    r = Round(
        id=s.ids.round_id(),
        number=1 + revealed_count(g),
        slot=slot,
        state=RoundState.QUEUED,
        created_at=at.mono_ms,
    )
    g.rounds.append(r)
    g.current_index = len(g.rounds) - 1
    s.touched = True
    return r


def fail_current_round(s: SessionState, r: Round, at: Instant, fx: EffectSink) -> None:
    """R4: no usable track after the maximum attempts; the next round takes its place."""
    r.state = RoundState.FAILED
    s.touched = True
    fx.log("round_failed", round_id=r.id, attempts=r.slot.attempts)
    start_round(s, at, fx)


def stop_play(r: Round, fx: EffectSink) -> None:
    """Stop the active or scheduled play of the round, if any."""
    play = active_play(r)
    if play is not None:
        r.stopped_play_ids.add(play.play_id)
        fx.add(SendStop(play.play_id))


def cancel_round(s: SessionState, r: Round, reason: CancelReason, fx: EffectSink) -> None:
    stop_play(r, fx)
    r.state = RoundState.CANCELLED
    r.cancel_reason = reason
    s.touched = True
    fx.log("round_cancelled", round_id=r.id, reason=reason.value)


# --- derived transitions (settle) ---------------------------------------------------------


def promote(s: SessionState, at: Instant, fx: EffectSink) -> bool:
    r = current_round(s.game)
    if r is None:
        return False
    if r.state is RoundState.QUEUED and r.slot.track_ref is not None:
        r.state = RoundState.PREPARING
        s.touched = True
        return True
    if r.state is RoundState.PREPARING and assets.stored(s, r.slot.asset_id) is not None:
        r.state = RoundState.LOADING
        r.loading_since = at.mono_ms
        r.ready_deadline = at.mono_ms + s.config.ready_timeout_ms
        s.touched = True
        fx.log("round_loading", round_id=r.id)
        return True
    return False


def begin_countdown(s: SessionState, r: Round, at: Instant, fx: EffectSink) -> None:
    """First PLAY of the round: ``official_start_at`` is fixed here, once and for all."""
    assert r.official_start_at is None
    asset = assets.stored(s, r.slot.asset_id)
    assert asset is not None
    assert r.slot.track_ref is not None
    duration = clip_ms(s, r)
    start_at = at.mono_ms + s.config.lead_ms
    play = Play(s.ids.play_id(), asset.asset_id, start_at, 0.0, start_at + duration)
    r.official_start_at = start_at
    r.plays.append(play)
    r.deadline = start_at + duration + s.game.settings.answer_grace_s * 1000
    r.state = RoundState.COUNTDOWN
    s.played.add(r.slot.track_ref)
    ready = s.asset_ready.get(asset.asset_id, {})
    for p in active_players(s):
        if not is_participant(p):
            continue
        listen = Listen(ready_at=ready.get(p.id))
        if listen.ready_at is not None and p.connection is ConnectionState.OFFLINE:
            listen.offline_since = start_at
        r.listen[p.id] = listen
    s.touched = True
    fx.add(SendPlay(play))
    fx.log(
        "round_started",
        round_id=r.id,
        ready=len(ready_ids(s, r)),
        expected=len(expected_ready(s)),
    )


def ready_check(s: SessionState, at: Instant, fx: EffectSink) -> bool:
    """R6: automatic start once every expected player is ready (never with nobody expected)."""
    r = current_round(s.game)
    if r is None or r.state is not RoundState.LOADING or not s.game.settings.auto_start:
        return False
    expected = {p.id for p in expected_ready(s)}
    if not expected or not expected <= ready_ids(s, r):
        return False
    begin_countdown(s, r, at, fx)
    return True


def open_round(s: SessionState, r: Round) -> None:
    """R10: end of the countdown, answers open with the first note."""
    r.state = RoundState.OPEN
    s.touched = True


def _overlap(start: int, end: int, window_start: int, window_end: int) -> int:
    return max(0, min(end, window_end) - max(start, window_start))


def close_round(
    s: SessionState, r: Round, at: Instant, reason: CloseReason, fx: EffectSink
) -> None:
    """OPEN → REVIEW: drafts captured, outages accounted, late_start_ms computed."""
    locked, captured = capture_drafts(r)
    start = r.official_start_at
    assert start is not None
    window_end = start + clip_ms(s, r)
    for listen in r.listen.values():
        if listen.offline_since is not None:
            listen.missed_ms += _overlap(listen.offline_since, at.mono_ms, start, window_end)
            listen.offline_since = None
    for answer in r.answers.values():
        if answer.status in (AnswerStatus.LOCKED, AnswerStatus.CAPTURED):
            answer.late_start_ms = late_start_ms(r, answer.player_id)
    r.closed_at = at.mono_ms
    r.close_reason = reason
    r.state = RoundState.REVIEW
    s.touched = True
    fx.log("round_closed", round_id=r.id, locked=locked, captured=captured, reason=reason.value)


def auto_close(s: SessionState, at: Instant, fx: EffectSink) -> bool:
    """R12: close as soon as every online participant has validated."""
    r = current_round(s.game)
    if r is None or r.state is not RoundState.OPEN:
        return False
    locked = {pid for pid, a in r.answers.items() if a.status is AnswerStatus.LOCKED}
    online = {
        p.id
        for p in s.players.values()
        if is_participant(p) and p.connection is ConnectionState.ONLINE
    }
    if not locked or not online <= locked:
        return False
    close_round(s, r, at, CloseReason.ALL_LOCKED, fx)
    return True


def decode_failure(s: SessionState, r: Round, fx: EffectSink) -> None:
    """R9: a strict majority of the expected clients cannot decode the clip."""
    expected = {p.id for p in expected_ready(s)}
    if not expected:
        return
    failing = r.decode_errors & expected
    if len(failing) <= s.config.decode_failure_majority * len(expected):
        return
    asset = s.assets.get(r.slot.asset_id or "")
    if asset is not None and asset.state is AssetState.STORED:
        asset.state = AssetState.FAILED
        asset.error = AssetFailureCode.DECODE_ERROR
    r.state = RoundState.PREPARING
    r.loading_since = None
    r.ready_deadline = None
    r.decode_errors.clear()
    s.touched = True
    fx.log("asset_decode_failed", round_id=r.id, failing=len(failing), expected=len(expected))


# --- reveal ---------------------------------------------------------------------------------


def build_reveal(s: SessionState, r: Round) -> RevealInfo:
    """Track information for the reveal; called only by ``publish``."""
    ref = r.slot.track_ref
    assert ref is not None
    asset = s.assets.get(r.slot.asset_id or "")
    title = asset.title if asset is not None else None
    artist = asset.artist if asset is not None else None
    catalog = s.catalogs.get(ref.bridge_id)
    entry = catalog.entries.get(ref.track_id) if catalog is not None else None
    bridge_name = catalog.bridge_name if catalog is not None else ""
    if title and artist:
        display = f"{artist} — {title}"
    elif title:
        display = title
    elif entry is not None:
        display = library.file_display_name(entry)
    else:
        display = "?"
    folder = bridge_name
    if entry is not None and entry.folder:
        folder = f"{bridge_name}/{entry.folder}"
    return RevealInfo(display_name=display, folder=folder, title=title, artist=artist)


# --- host commands --------------------------------------------------------------------------


def current_by_key(s: SessionState, round_id: str) -> Round:
    """Step 2 of the HOST checks: the envelope ``round_id`` must be the current round."""
    r = current_round(s.game)
    require(r is not None and r.id == round_id, ErrorCode.STALE_COMMAND)
    assert r is not None
    return r


def require_rule(cmd: str, s: SessionState, issuer: Player) -> None:
    require(rule_ok(cmd, s, issuer), ErrorCode.INVALID_STATE)


def h_next(s: SessionState, issuer: Player, msg: HostNext, at: Instant, fx: EffectSink) -> None:
    current_by_key(s, msg.round_id)
    require_rule("next", s, issuer)
    start_round(s, at, fx)


def h_force_start(
    s: SessionState, issuer: Player, msg: HostForceStart, at: Instant, fx: EffectSink
) -> None:
    r = current_by_key(s, msg.round_id)
    require_rule("force_start", s, issuer)
    begin_countdown(s, r, at, fx)


def h_replay(s: SessionState, issuer: Player, msg: HostReplay, at: Instant, fx: EffectSink) -> None:
    """R15: new play; ``official_start_at`` and the deadline never change."""
    r = current_by_key(s, msg.round_id)
    require(bool(r.plays) and r.plays[-1].play_id == msg.args.play_id, ErrorCode.STALE_COMMAND)
    require_rule("replay", s, issuer)
    stop_play(r, fx)
    duration = clip_ms(s, r)
    start_at = at.mono_ms + s.config.replay_lead_ms
    play = Play(s.ids.play_id(), r.plays[-1].asset_id, start_at, 0.0, start_at + duration)
    r.plays.append(play)
    s.touched = True
    fx.add(SendPlay(play))
    fx.log("round_replayed", round_id=r.id)


def h_stop(s: SessionState, issuer: Player, msg: HostStop, at: Instant, fx: EffectSink) -> None:
    del at
    r = current_by_key(s, msg.round_id)
    play = active_play(r)
    require(play is not None and play.play_id == msg.args.play_id, ErrorCode.STALE_COMMAND)
    require_rule("stop", s, issuer)
    stop_play(r, fx)
    s.touched = True


def h_skip(s: SessionState, issuer: Player, msg: HostSkip, at: Instant, fx: EffectSink) -> None:
    """R18: the round is cancelled; its track is not marked as played unless it was heard."""
    r = current_by_key(s, msg.round_id)
    require_rule("skip", s, issuer)
    cancel_round(s, r, CancelReason.SKIPPED, fx)
    start_round(s, at, fx)


def h_add_time(
    s: SessionState, issuer: Player, msg: HostAddTime, at: Instant, fx: EffectSink
) -> None:
    del at, fx
    r = current_by_key(s, msg.round_id)
    require(r.deadline == msg.args.expected_deadline, ErrorCode.STALE_COMMAND)
    require_rule("add_time", s, issuer)
    assert r.deadline is not None
    r.deadline += s.config.add_time_ms
    s.touched = True


def h_close(s: SessionState, issuer: Player, msg: HostClose, at: Instant, fx: EffectSink) -> None:
    r = current_by_key(s, msg.round_id)
    require_rule("close", s, issuer)
    close_round(s, r, at, CloseReason.HOST, fx)


def review_player_ids(s: SessionState, r: Round) -> list[str]:
    """Players listed in REVIEW: participants and anyone with an answer, not removed."""
    ids: list[str] = []
    for p in active_players(s):
        if is_participant(p) or p.id in r.answers:
            ids.append(p.id)
    return ids


def h_score_draft(
    s: SessionState, issuer: Player, msg: HostScoreDraft, at: Instant, fx: EffectSink
) -> None:
    """Server-side draft of the round's points: never an event (spec §6.4)."""
    del at, fx
    r = current_by_key(s, msg.round_id)
    require_rule("score_draft", s, issuer)
    require(msg.args.player_id in review_player_ids(s, r), ErrorCode.UNKNOWN_PLAYER)
    if msg.args.points == 0:
        r.score_draft.pop(msg.args.player_id, None)
    else:
        r.score_draft[msg.args.player_id] = msg.args.points
    s.touched = True


def h_publish(
    s: SessionState, issuer: Player, msg: HostPublish, at: Instant, fx: EffectSink
) -> None:
    """R20: one ``round`` event per non-zero draft, then the reveal."""
    r = current_by_key(s, msg.round_id)
    require_rule("publish", s, issuer)
    events: list[int] = []
    for p in active_players(s):
        points = r.score_draft.get(p.id, 0)
        if points:
            event = s.journal.append(
                game_id=s.game.game_id,
                player_id=p.id,
                delta=points,
                kind=ScoreKind.ROUND,
                by=issuer.id,
                at_wall_ms=at.wall_ms,
                round_id=r.id,
            )
            events.append(event.id)
    r.published_event_ids = tuple(events)
    r.published_at = at.mono_ms
    r.reveal = build_reveal(s, r)
    r.state = RoundState.REVEALED
    s.touched = True
    fx.log("round_published", round_id=r.id, events=len(events))


def h_undo_publish(
    s: SessionState, issuer: Player, msg: HostUndoPublish, at: Instant, fx: EffectSink
) -> None:
    """R21: revoke the round's events, back to REVIEW with the previous draft restored."""
    target = undo_target(s.game)
    require(target is not None and target.id == msg.round_id, ErrorCode.STALE_COMMAND)
    require_rule("undo_publish", s, issuer)
    assert target is not None
    revoked = s.journal.revoked_ids()
    for event_id in target.published_event_ids:
        if event_id in revoked:
            continue
        event = s.journal.events()[event_id - 1]
        s.journal.append(
            game_id=event.game_id,
            player_id=event.player_id,
            delta=0,
            kind=ScoreKind.REVOKE,
            by=issuer.id,
            at_wall_ms=at.wall_ms,
            round_id=event.round_id,
            revokes=(event_id,),
        )
    g = s.game
    live = current_round(g)
    if (
        live is not None
        and live is not target
        and live.state
        not in (
            RoundState.REVEALED,
            RoundState.FAILED,
            RoundState.CANCELLED,
        )
    ):
        live.state = RoundState.CANCELLED
        live.cancel_reason = CancelReason.UNDO_DISCARDED
        g.pipeline.appendleft(live.slot)
        live.slot = Slot(track_ref=None)
    target.reveal = None
    target.published_event_ids = ()
    target.published_at = None
    target.state = RoundState.REVIEW
    g.current_index = g.rounds.index(target)
    s.touched = True
    fx.log("publish_undone", round_id=target.id)
