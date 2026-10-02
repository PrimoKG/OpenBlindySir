"""``view_for``: the ONLY projection of the state to clients (spec §2 principle 5, §6.8).

Every field is built explicitly. Track data (catalogue entries, tags, reveal) is read only
by ``_reveal_track``, ``_mc_panel`` and ``_mc_track_info``.
"""

import posixpath

from openblindysir_protocol.enums import (
    AnswerStatus,
    AssetState,
    BridgeState,
    ConnectionState,
    GamePhase,
    HostMode,
    HostWarning,
    Role,
    RoundState,
    ScoreKind,
)
from openblindysir_protocol.settings import GameSettings, ServerLimits, SourceView
from openblindysir_protocol.version import PROTOCOL_VERSION
from openblindysir_protocol.views import (
    AdjustmentEntry,
    AudioRef,
    AudioSlots,
    BridgeStatus,
    FinalAdjustmentShown,
    FinalResults,
    FinalReviewRow,
    GameInfo,
    HistoryEntry,
    HostMcView,
    HostPanel,
    HostPlayerModeView,
    McOpenRow,
    McPanel,
    McTrackInfo,
    Me,
    MyAnswer,
    PlayerOps,
    PlayerView,
    PlayInfo,
    Progress,
    ReadyCheck,
    RevealRow,
    RevealTrack,
    ReviewRow,
    RoundCountdown,
    RoundHostReview,
    RoundMcOpen,
    RoundOpen,
    RoundPending,
    RoundPlayerReview,
    RoundRevealed,
    SessionInfo,
    StandingRow,
    ViewPlayer,
)
from openblindysir_server import __version__
from openblindysir_server.game import assets, permissions, selection
from openblindysir_server.game.readiness import expected_ready, ready_ids
from openblindysir_server.game.standings import standings
from openblindysir_server.game.state import (
    IN_FLIGHT_ASSET_STATES,
    Answer,
    Player,
    Round,
    SessionState,
    Slot,
    active_play,
    active_players,
    current_round,
    is_participant,
    late_start_ms,
    undo_target,
)

PROGRESS_MIN_EXPECTED = 3  # below 3, "1/2" would reveal who answered and when (patch 2)
PENDING_STATES = frozenset({RoundState.QUEUED, RoundState.PREPARING, RoundState.LOADING})
CURRENT_AUDIO_STATES = frozenset(
    {
        RoundState.LOADING,
        RoundState.COUNTDOWN,
        RoundState.OPEN,
        RoundState.REVIEW,
        RoundState.REVEALED,
    }
)
NEXT_AUDIO_STATES = frozenset({RoundState.REVIEW, RoundState.REVEALED})

AnyView = PlayerView | HostPlayerModeView | HostMcView


def view_for(s: SessionState, player_id: str) -> AnyView:
    p = s.players[player_id]
    if p.connection is ConnectionState.REMOVED:
        raise ValueError("removed players have no view")
    session = _session(s)
    me = _me(p)
    phase = s.game.phase
    players = _players(s, player_id)
    ranking = standings(s)
    game = _game_info(s)
    audio = audio_slots(s)
    play = _play(s)
    final_results = _final_results(s, ranking)
    if p.role is Role.PLAYER:
        return PlayerView(
            kind="player",
            session=session,
            me=me,
            phase=phase,
            players=players,
            standings=ranking,
            game=game,
            audio=audio,
            play=play,
            final_results=final_results,
            round=_round_player(s, p),
        )
    host = _host_panel(s, p, ranking)
    if p.host_mode is HostMode.PLAYER:
        return HostPlayerModeView(
            kind="host_player",
            session=session,
            me=me,
            phase=phase,
            players=players,
            standings=ranking,
            game=game,
            audio=audio,
            play=play,
            final_results=final_results,
            round=_round_host_pm(s, p),
            host=host,
        )
    return HostMcView(
        kind="host_mc",
        session=session,
        me=me,
        phase=phase,
        players=players,
        standings=ranking,
        game=game,
        audio=audio,
        play=play,
        final_results=final_results,
        round=_round_mc(s),
        host=host,
        mc=_mc_panel(s),
    )


# --- common parts ---------------------------------------------------------------------------


def _session(s: SessionState) -> SessionInfo:
    return SessionInfo(epoch=s.epoch, protocol=PROTOCOL_VERSION, server_version=__version__)


def _me(p: Player) -> Me:
    return Me(
        player_id=p.id,
        nickname=p.nickname,
        role=p.role,
        host_mode=p.host_mode if p.role is Role.HOST else None,
        participant=is_participant(p),
    )


def _players(s: SessionState, viewer_id: str) -> list[ViewPlayer]:
    return [
        ViewPlayer(
            id=p.id,
            nickname=p.nickname,
            online=p.connection is ConnectionState.ONLINE,
            is_host=p.role is Role.HOST,
            is_me=p.id == viewer_id,
        )
        for p in active_players(s)
    ]


def _game_info(s: SessionState) -> GameInfo | None:
    g = s.game
    if g.phase is GamePhase.LOBBY:
        return None
    r = current_round(g)
    return GameInfo(
        game_id=g.game_id,
        rounds_total=g.settings.rounds,
        round_number=r.number if r is not None else None,
        clip_seconds=g.settings.clip_seconds,
    )


def _audio_ref(s: SessionState, asset_id: str | None) -> AudioRef | None:
    asset = assets.stored(s, asset_id)
    if asset is None:
        return None
    return AudioRef(
        asset_id=asset.asset_id,
        url=f"/api/audio/{asset.asset_id}",
        duration_ms=asset.clip_duration_ms or 0,
    )


def audio_slots(s: SessionState) -> AudioSlots:
    """Downloadable clips; ``next`` only while the current round is REVIEW/REVEALED (§7.3)."""
    r = current_round(s.game)
    if r is None:
        return AudioSlots(current=None, next=None)
    current = _audio_ref(s, r.slot.asset_id) if r.state in CURRENT_AUDIO_STATES else None
    upcoming = None
    if r.state in NEXT_AUDIO_STATES and s.game.pipeline:
        upcoming = _audio_ref(s, s.game.pipeline[0].asset_id)
    return AudioSlots(current=current, next=upcoming)


def _play(s: SessionState) -> PlayInfo | None:
    r = current_round(s.game)
    play = active_play(r) if r is not None else None
    if play is None:
        return None
    return PlayInfo(
        play_id=play.play_id,
        asset_id=play.asset_id,
        start_at=play.start_at,
        clip_offset=play.clip_offset_s,
    )


def _final_results(s: SessionState, ranking: list[StandingRow]) -> FinalResults | None:
    g = s.game
    if g.phase is not GamePhase.FINAL_RESULTS:
        return None
    shown = [
        FinalAdjustmentShown(player_id=event.player_id, delta=event.delta)
        for event in s.journal.active(g.game_id)
        if event.kind is ScoreKind.FINAL_ADJUSTMENT
    ]
    return FinalResults(
        standings=ranking,
        podium=[row for row in ranking if row.rank <= 3],
        rounds_played=sum(1 for r in g.rounds if r.state is RoundState.REVEALED),
        final_adjustments=shown,
    )


# --- rounds ---------------------------------------------------------------------------------


def _my_answer(r: Round, player_id: str) -> MyAnswer:
    answer = r.answers.get(player_id)
    if answer is None:
        return MyAnswer(status=AnswerStatus.NONE, text=None, draft_text=None)
    restorable = answer.status in (AnswerStatus.NONE, AnswerStatus.DRAFT)
    return MyAnswer(
        status=answer.status,
        text=answer.text if answer.status in (AnswerStatus.LOCKED, AnswerStatus.CAPTURED) else None,
        draft_text=answer.draft_text if restorable and answer.draft_text else None,
    )


def _locked_count(s: SessionState, r: Round) -> int:
    present = {p.id for p in active_players(s)}
    return sum(
        1 for pid, a in r.answers.items() if a.status is AnswerStatus.LOCKED and pid in present
    )


def _progress_counts(s: SessionState, r: Round) -> tuple[int, int]:
    """``n`` = LOCKED answers; ``m`` = n + online participants not LOCKED (MC excluded)."""
    validated = _locked_count(s, r)
    waiting = 0
    for p in s.players.values():
        if not is_participant(p) or p.connection is not ConnectionState.ONLINE:
            continue
        answer = r.answers.get(p.id)
        if answer is None or answer.status is not AnswerStatus.LOCKED:
            waiting += 1
    return validated, validated + waiting


def _progress(s: SessionState, r: Round) -> Progress | None:
    validated, expected = _progress_counts(s, r)
    if expected < PROGRESS_MIN_EXPECTED:
        return None
    return Progress(validated=validated, expected=expected)


def _pending(r: Round) -> RoundPending:
    state = r.state.value
    assert state in ("QUEUED", "PREPARING", "LOADING")
    return RoundPending(state=state, round_id=r.id, number=r.number)


def _countdown(r: Round) -> RoundCountdown:
    assert r.official_start_at is not None
    return RoundCountdown(
        state="COUNTDOWN", round_id=r.id, number=r.number, official_start_at=r.official_start_at
    )


def _round_open_player(s: SessionState, r: Round, p: Player) -> RoundOpen:
    """OPEN as seen by a player AND a host in Player Mode: identical (patch 2)."""
    assert r.official_start_at is not None
    assert r.deadline is not None
    return RoundOpen(
        state="OPEN",
        round_id=r.id,
        number=r.number,
        official_start_at=r.official_start_at,
        deadline=r.deadline,
        my_answer=_my_answer(r, p.id),
        progress=_progress(s, r),
    )


def _row_order(s: SessionState, r: Round) -> list[str]:
    """LOCKED by order, then CAPTURED by arrival, then the others by arrival."""
    present = [p for p in active_players(s) if is_participant(p) or p.id in r.answers]
    locked = sorted(
        (p for p in present if _status(r, p.id) is AnswerStatus.LOCKED),
        key=lambda p: r.answers[p.id].order or 0,
    )
    captured = [p for p in present if _status(r, p.id) is AnswerStatus.CAPTURED]
    others = [
        p for p in present if _status(r, p.id) not in (AnswerStatus.LOCKED, AnswerStatus.CAPTURED)
    ]
    return [p.id for p in locked + captured + others]


def _status(r: Round, player_id: str) -> AnswerStatus:
    answer = r.answers.get(player_id)
    return answer.status if answer is not None else AnswerStatus.NONE


def _shown_answer(r: Round, player_id: str) -> Answer:
    return r.answers.get(player_id) or Answer(player_id=player_id)


def _review_rows(s: SessionState, r: Round) -> list[ReviewRow]:
    rows: list[ReviewRow] = []
    for pid in _row_order(s, r):
        answer = _shown_answer(r, pid)
        status = answer.status if answer.status is not AnswerStatus.DRAFT else AnswerStatus.NONE
        rows.append(
            ReviewRow(
                player_id=pid,
                text=answer.text if status is not AnswerStatus.NONE else None,
                status=status,
                elapsed_ms=answer.elapsed_ms,
                order=answer.order,
                near_tie=answer.near_tie,
                late_start_ms=late_start_ms(r, pid),
                points_draft=r.score_draft.get(pid, 0),
            )
        )
    return rows


def _host_review(s: SessionState, r: Round) -> RoundHostReview:
    assert r.official_start_at is not None
    return RoundHostReview(
        state="REVIEW",
        round_id=r.id,
        number=r.number,
        official_start_at=r.official_start_at,
        answers=_review_rows(s, r),
        ending=s.game.ending is not None,
    )


def _reveal_track(r: Round) -> RevealTrack:
    info = r.reveal
    assert info is not None
    return RevealTrack(
        display_name=info.display_name, folder=info.folder, title=info.title, artist=info.artist
    )


def _reveal_rows(s: SessionState, r: Round) -> list[RevealRow]:
    game_id = s.game.game_id
    rows: list[RevealRow] = []
    for pid in _row_order(s, r):
        answer = _shown_answer(r, pid)
        status = answer.status if answer.status is not AnswerStatus.DRAFT else AnswerStatus.NONE
        rows.append(
            RevealRow(
                player_id=pid,
                text=answer.text if status is not AnswerStatus.NONE else None,
                status=status,
                elapsed_ms=answer.elapsed_ms,
                order=answer.order,
                near_tie=answer.near_tie,
                points=s.journal.round_points(game_id, r.id, pid),
            )
        )
    return rows


def _revealed(s: SessionState, r: Round) -> RoundRevealed:
    return RoundRevealed(
        state="REVEALED",
        round_id=r.id,
        number=r.number,
        track=_reveal_track(r),
        rows=_reveal_rows(s, r),
    )


def _round_player(
    s: SessionState, p: Player
) -> RoundPending | RoundCountdown | RoundOpen | RoundPlayerReview | RoundRevealed | None:
    r = current_round(s.game)
    if r is None:
        return None
    if r.state in PENDING_STATES:
        return _pending(r)
    if r.state is RoundState.COUNTDOWN:
        return _countdown(r)
    if r.state is RoundState.OPEN:
        return _round_open_player(s, r, p)
    if r.state is RoundState.REVIEW:
        return RoundPlayerReview(
            state="REVIEW", round_id=r.id, number=r.number, my_answer=_my_answer(r, p.id)
        )
    if r.state is RoundState.REVEALED:
        return _revealed(s, r)
    return None


def _round_host_pm(
    s: SessionState, p: Player
) -> RoundPending | RoundCountdown | RoundOpen | RoundHostReview | RoundRevealed | None:
    r = current_round(s.game)
    if r is None:
        return None
    if r.state in PENDING_STATES:
        return _pending(r)
    if r.state is RoundState.COUNTDOWN:
        return _countdown(r)
    if r.state is RoundState.OPEN:
        return _round_open_player(s, r, p)
    if r.state is RoundState.REVIEW:
        return _host_review(s, r)
    if r.state is RoundState.REVEALED:
        return _revealed(s, r)
    return None


def _round_mc(
    s: SessionState,
) -> RoundPending | RoundCountdown | RoundMcOpen | RoundHostReview | RoundRevealed | None:
    r = current_round(s.game)
    if r is None:
        return None
    if r.state in PENDING_STATES:
        return _pending(r)
    if r.state is RoundState.COUNTDOWN:
        return _countdown(r)
    if r.state is RoundState.OPEN:
        assert r.official_start_at is not None
        assert r.deadline is not None
        validated, expected = _progress_counts(s, r)
        per_player = [
            McOpenRow(player_id=p.id, validated=_status(r, p.id) is AnswerStatus.LOCKED)
            for p in active_players(s)
            if is_participant(p)
        ]
        return RoundMcOpen(
            state="OPEN",
            round_id=r.id,
            number=r.number,
            official_start_at=r.official_start_at,
            deadline=r.deadline,
            validated=validated,
            expected=expected,
            per_player=per_player,
        )
    if r.state is RoundState.REVIEW:
        return _host_review(s, r)
    if r.state is RoundState.REVEALED:
        return _revealed(s, r)
    return None


# --- host panel -----------------------------------------------------------------------------


def _settings(s: SessionState) -> GameSettings:
    settings = s.game.settings
    return GameSettings(
        rounds=settings.rounds,
        clip_seconds=settings.clip_seconds,
        answer_grace_s=settings.answer_grace_s,
        sources=[SourceView(bridge_id=b, folder_prefix=f) for b, f in settings.sources],
        auto_start=settings.auto_start,
        prefetch_depth=settings.prefetch_depth,
        allow_repeats=settings.allow_repeats,
    )


def _limits(s: SessionState) -> ServerLimits:
    cfg = s.config
    return ServerLimits(
        max_players=cfg.max_players,
        clip_min_s=cfg.clip_min_s,
        clip_max_s=cfg.clip_max_s,
        answer_max_chars=cfg.answer_max_chars,
        near_tie_ms=cfg.near_tie_ms,
        ready_timeout_s=cfg.ready_timeout_ms // 1000,
        clip_format=cfg.clip_format,
    )


def bridge_status(s: SessionState) -> BridgeStatus:
    if not s.bridges:
        return BridgeStatus(state=BridgeState.OFFLINE, name=None, track_count=0, jobs_in_flight=0)
    online = [b for b in s.bridges.values() if b.state is not BridgeState.OFFLINE]
    info = online[-1] if online else list(s.bridges.values())[-1]
    in_flight = sum(
        1
        for a in s.assets.values()
        if a.track_ref.bridge_id == info.bridge_id and a.state in IN_FLIGHT_ASSET_STATES
    )
    return BridgeStatus(
        state=info.state, name=info.name, track_count=info.track_count, jobs_in_flight=in_flight
    )


def _late_ms(s: SessionState, p: Player) -> int | None:
    r = current_round(s.game)
    if r is None or r.state not in (RoundState.COUNTDOWN, RoundState.OPEN):
        return None
    return late_start_ms(r, p.id)


def _players_ops(s: SessionState) -> list[PlayerOps]:
    r = current_round(s.game)
    ready: set[str] = ready_ids(s, r) if r is not None else set()
    return [
        PlayerOps(
            player_id=p.id,
            connection=p.connection,
            audio_state=p.audio_state,
            audio_error=p.audio_error,
            ready=p.id in ready,
            late_ms=_late_ms(s, p),
            rtt_min_ms=None if p.rtt_min_ms is None else round(p.rtt_min_ms),
            offset_ms=None if p.clock_offset_ms is None else round(p.clock_offset_ms),
        )
        for p in active_players(s)
    ]


def _ready_check(s: SessionState) -> ReadyCheck | None:
    r = current_round(s.game)
    if r is None or r.state is not RoundState.LOADING or r.ready_deadline is None:
        return None
    expected = {p.id for p in expected_ready(s)}
    ready = ready_ids(s, r)
    return ReadyCheck(
        ready=len(expected & ready),
        expected=len(expected),
        timeout_at=r.ready_deadline,
        can_force=len(ready) >= 1,
    )


def _history(s: SessionState, player_id: str) -> list[HistoryEntry]:
    game_id = s.game.game_id
    entries: list[HistoryEntry] = []
    for r in s.game.rounds:
        if r.state is not RoundState.REVEALED:
            continue
        answer = _shown_answer(r, player_id)
        status = answer.status if answer.status is not AnswerStatus.DRAFT else AnswerStatus.NONE
        entries.append(
            HistoryEntry(
                round_id=r.id,
                number=r.number,
                text=answer.text if status is not AnswerStatus.NONE else None,
                status=status,
                elapsed_ms=answer.elapsed_ms,
                order=answer.order,
                near_tie=answer.near_tie,
                points=s.journal.round_points(game_id, r.id, player_id),
            )
        )
    return entries


def _adjustments(s: SessionState, player_id: str) -> list[AdjustmentEntry]:
    numbers = {r.id: r.number for r in s.game.rounds}
    return [
        AdjustmentEntry(
            delta=event.delta,
            round_number=numbers.get(event.round_id) if event.round_id else None,
            note=event.note,
        )
        for event in s.journal.active(s.game.game_id)
        if event.kind is ScoreKind.ADJUSTMENT and event.player_id == player_id
    ]


def _final_rows(s: SessionState, ranking: list[StandingRow]) -> list[FinalReviewRow]:
    draft = s.game.final_draft
    return [
        FinalReviewRow(
            player_id=row.player_id,
            score_before=row.score,
            draft_delta=draft.get(row.player_id, 0),
            score_after=row.score + draft.get(row.player_id, 0),
            history=_history(s, row.player_id),
            adjustments=_adjustments(s, row.player_id),
        )
        for row in ranking
    ]


def _warnings(s: SessionState) -> list[HostWarning]:
    g = s.game
    r = current_round(g)
    warnings: list[HostWarning] = []
    in_play = g.phase in (GamePhase.LOBBY, GamePhase.IN_GAME)
    if in_play and not any(b.state is BridgeState.ONLINE for b in s.bridges.values()):
        warnings.append(HostWarning.BRIDGE_OFFLINE)
    if r is not None and r.state is RoundState.QUEUED and r.slot.track_ref is None:
        warnings.append(HostWarning.POOL_EXHAUSTED)
    if r is not None and g.cache_full_round == r.id:
        warnings.append(HostWarning.CACHE_FULL)
    if r is not None and r.slot.attempts > 1:
        warnings.append(HostWarning.TRACK_REPLACED)
    if r is not None and r.state in PENDING_STATES | {RoundState.COUNTDOWN}:
        index = g.current_index
        if index is not None and index > 0 and g.rounds[index - 1].state is RoundState.FAILED:
            warnings.append(HostWarning.ROUND_FAILED)
    return warnings


def _host_panel(s: SessionState, p: Player, ranking: list[StandingRow]) -> HostPanel:
    g = s.game
    r = current_round(g)
    target = undo_target(g)
    return HostPanel(
        settings=_settings(s),
        limits=_limits(s),
        commands=permissions.allowed(s, p),
        start_blockers=permissions.start_blockers(s) if g.phase is GamePhase.LOBBY else [],
        bridge=bridge_status(s),
        pool=selection.pool_status(s) if g.phase in (GamePhase.LOBBY, GamePhase.IN_GAME) else None,
        players_ops=_players_ops(s),
        ready_check=_ready_check(s),
        undo_round_id=target.id if target is not None else None,
        last_play_id=r.plays[-1].play_id if r is not None and r.plays else None,
        final_review=_final_rows(s, ranking) if g.phase is GamePhase.FINAL_SCORE_REVIEW else None,
        warnings=_warnings(s),
    )


# --- MC panel (the only place, with the reveal, that reads track data) -----------------------


def _mc_track_info(s: SessionState, slot: Slot) -> McTrackInfo | None:
    ref = slot.track_ref
    if ref is None:
        return None
    catalog = s.catalogs.get(ref.bridge_id)
    entry = catalog.entries.get(ref.track_id) if catalog is not None else None
    if catalog is None or entry is None:
        return None
    asset = s.assets.get(slot.asset_id) if slot.asset_id else None
    display = None
    if asset is not None and asset.state is AssetState.STORED and (asset.title or asset.artist):
        display = " — ".join(part for part in (asset.artist, asset.title) if part)
    return McTrackInfo(
        bridge_name=catalog.bridge_name,
        folder=entry.folder,
        filename=posixpath.basename(entry.relpath),
        display_name=display,
        asset_state=asset.state if asset is not None else None,
    )


def _mc_panel(s: SessionState) -> McPanel:
    g = s.game
    r = current_round(g)
    current = _mc_track_info(s, r.slot) if r is not None else None
    upcoming = [info for slot in g.pipeline if (info := _mc_track_info(s, slot)) is not None]
    heads = list(g.queue)[: s.config.mc_upcoming_queue_heads]
    upcoming.extend(
        info for ref in heads if (info := _mc_track_info(s, Slot(track_ref=ref))) is not None
    )
    return McPanel(current_track=current, upcoming=upcoming)
