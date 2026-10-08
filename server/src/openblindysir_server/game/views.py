"""``view_for``: the ONLY projection of the state to clients (spec §2 principle 5, §6.8).

Every field is built explicitly. Track data (catalogue entries, tags, reveal) is read only
by ``_reveal_track``, ``_mc_panel`` and ``_mc_track_info``.
"""

import posixpath
from dataclasses import asdict

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
from openblindysir_protocol.metadata import MusicalMetadata
from openblindysir_protocol.settings import GameSettings, ServerLimits, SourceView
from openblindysir_protocol.themes import ThemeFilter
from openblindysir_protocol.version import PROTOCOL_VERSION
from openblindysir_protocol.views import (
    AdjustmentEntry,
    ArchiveSource,
    AudioRef,
    AudioSlots,
    AutoMatchInfo,
    BridgeDetail,
    BridgeStatus,
    FinalAdjustmentShown,
    Finale,
    FinaleAnswer,
    FinaleRound,
    FinalResults,
    FinalReviewRow,
    GameInfo,
    GameRecord,
    GameRules,
    HistoryEntry,
    HostMcView,
    HostPanel,
    HostPlayerModeView,
    McOpenRow,
    McPanel,
    McTrackInfo,
    Me,
    MyAnswer,
    PauseInfo,
    PlayerOps,
    PlayerView,
    PlayInfo,
    Progress,
    ReadyCheck,
    RevealRow,
    RevealTrack,
    ReviewRound,
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
    TeamStanding,
    ViewPlayer,
)
from openblindysir_server import __version__
from openblindysir_server.game import assets, auto_scoring, manual, permissions, rounds, selection
from openblindysir_server.game.metadata import musical_metadata
from openblindysir_server.game.readiness import expected_ready, ready_ids
from openblindysir_server.game.standings import standings, standings_player_ids
from openblindysir_server.game.state import (
    IN_FLIGHT_ASSET_STATES,
    Answer,
    Player,
    RevealInfo,
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
    ranking = standings(s) if phase is GamePhase.FINAL_RESULTS else []
    game = _game_info(s)
    audio = audio_slots(s)
    play = _play(s)
    final_results = _final_results(s, ranking)
    finale = _finale(s)
    rules, paused, teams = _rules(s), _paused(s), team_standings(s, ranking)
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
            finale=finale,
            round=_round_player(s, p),
            rules=rules,
            paused=paused,
            team_standings=teams,
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
            finale=finale,
            round=_round_host_pm(s, p),
            host=host,
            rules=rules,
            paused=paused,
            team_standings=teams,
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
        finale=finale,
        round=_round_mc(s),
        host=host,
        mc=_mc_panel(s),
        rules=rules,
        paused=paused,
        team_standings=teams,
    )


# --- common parts ---------------------------------------------------------------------------


def _session(s: SessionState) -> SessionInfo:
    return SessionInfo(
        epoch=s.epoch,
        protocol=PROTOCOL_VERSION,
        server_version=__version__,
        recovered=s.recovered,
        persistence_status=s.persistence_status,
    )


def _rules(s: SessionState) -> GameRules:
    cfg = s.game.settings
    return GameRules(
        answer_max_chars=s.config.answer_max_chars,
        scoring_mode=cfg.scoring_mode,
        acceptance_threshold=cfg.acceptance_threshold,
        answer_fields=cfg.answer_fields,
        album_points=cfg.album_points,
        year_points=cfg.year_points,
        featuring_points=cfg.featuring_points,
        answer_mode=cfg.answer_mode,
        title_points=cfg.title_points,
        artist_points=cfg.artist_points,
        custom_points=cfg.custom_points,
        instructions=cfg.instructions,
        captured_policy=cfg.captured_policy,
    )


def _paused(s: SessionState) -> PauseInfo | None:
    r = current_round(s.game)
    if r is None or r.paused_at is None or r.state not in {RoundState.OPEN, RoundState.REVIEW}:
        return None
    assert r.deadline is not None
    return PauseInfo(
        paused_at=r.paused_at,
        remaining_ms=max(
            0,
            ((r.auto_advance_at if r.state is RoundState.REVIEW else r.deadline) or 0)
            - (r.resume_at or r.paused_at),
        ),
        clip_offset_s=r.pause_offset_s,
        resume_at=r.resume_at,
    )


def team_standings(s: SessionState, ranking: list[StandingRow]) -> list[TeamStanding]:
    groups: dict[str, list[StandingRow]] = {}
    for row in ranking:
        team = s.players[row.player_id].team
        if team:
            groups.setdefault(team, []).append(row)
    ordered = sorted(
        groups, key=lambda team: (-sum(row.score for row in groups[team]), team.casefold())
    )
    result: list[TeamStanding] = []
    previous: int | None = None
    rank = 0
    for index, team in enumerate(ordered, 1):
        score = sum(row.score for row in groups[team])
        if score != previous:
            rank, previous = index, score
        result.append(
            TeamStanding(
                team=team, score=score, rank=rank, members=[row.player_id for row in groups[team]]
            )
        )
    return result


def _me(p: Player) -> Me:
    return Me(
        player_id=p.id,
        nickname=p.nickname,
        role=p.role,
        host_mode=p.host_mode if p.role is Role.HOST else None,
        participant=is_participant(p),
    )


def _players(s: SessionState, viewer_id: str) -> list[ViewPlayer]:
    present = {p.id for p in active_players(s)}
    historical = s.game.phase is GamePhase.FINAL_RESULTS or (
        s.game.phase is GamePhase.FINAL_SCORE_REVIEW and s.players[viewer_id].role is Role.HOST
    )
    return [
        ViewPlayer(
            id=p.id,
            nickname=p.nickname,
            online=p.connection is ConnectionState.ONLINE,
            is_host=p.role is Role.HOST,
            is_me=p.id == viewer_id,
            spectator=p.spectator,
            team=p.team,
        )
        for p in s.players.values()
        if p.id in present
        or (
            historical
            and any(p.id in r.participant_ids or p.id in r.answers for r in s.game.rounds)
        )
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
    if s.game.phase is GamePhase.FINAL_SCORE_REVIEW:
        play = s.game.finale_play
        return AudioSlots(current=_audio_ref(s, play.asset_id) if play else None, next=None)
    if s.game.phase is GamePhase.FINAL_RESULTS:
        return AudioSlots(current=None, next=None)
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
    play = (
        s.game.finale_play
        if s.game.phase is GamePhase.FINAL_SCORE_REVIEW
        else active_play(r)
        if r is not None
        else None
    )
    if (
        s.game.phase is GamePhase.FINAL_SCORE_REVIEW
        and play is not None
        and s.last_at >= play.ends_at
    ):
        return None
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
        FinalAdjustmentShown(player_id=event.player_id, delta=event.delta, note=event.note)
        for event in s.journal.active(g.game_id)
        if event.kind is ScoreKind.FINAL_ADJUSTMENT
    ]
    return FinalResults(
        standings=ranking,
        podium=[row for row in ranking if row.rank <= 3],
        rounds_played=sum(1 for r in g.rounds if r.state is RoundState.REVEALED),
        final_adjustments=shown,
        recap=_final_rows(s, ranking),
        finished_at=g.finalized_wall_ms,
        podium_started_at=g.finalized_at + 800
        if g.finalized_at is not None and not g.podium_skipped
        else None,
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
    return RoundPending(
        state=state,
        round_id=r.id,
        number=r.number,
        wait_reason="pool_exhausted"
        if r.slot.track_ref is None
        else "bridge_offline"
        if r.slot.waiting_bridge
        else None,
    )


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
    ids = rounds.review_player_ids(s, r)
    present = [s.players[pid] for pid in ids]
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
                auto_evidence=[
                    AutoMatchInfo(**asdict(row)) for row in r.auto_evidence.get(pid, [])
                ],
                auto_overridden=pid in r.auto_overrides,
                player_id=pid,
                text=answer.text if status is not AnswerStatus.NONE else None,
                status=status,
                elapsed_ms=answer.elapsed_ms,
                order=answer.order,
                near_tie=answer.near_tie,
                late_start_ms=late_start_ms(r, pid),
                points_draft=r.score_draft.get(pid, 0),
                reviewed=pid in r.score_reviewed,
                score_before=_draft_score(s, pid)
                - (r.score_draft.get(pid, 0) if r.included else 0)
                + s.game.final_draft.get(pid, 0),
                received_at_wall_ms=answer.received_at_wall_ms,
                judgement="criteria" if pid in r.judgements else "manual",
                score_revision=r.score_revisions.get(pid, 0),
                **r.judgements.get(pid, {}),
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
        track=_track_info(rounds.build_reveal(s, r)),
        recovery_interrupted=r.recovery_interrupted,
    )


def _reveal_track(r: Round) -> RevealTrack:
    info = r.reveal
    assert info is not None
    return _track_info(info)


def _track_info(info: RevealInfo) -> RevealTrack:
    return RevealTrack(
        cleared_fields=info.cleared_fields or [],
        aliases=info.aliases,
        display_name=info.display_name,
        folder=info.folder,
        title=info.title,
        artist=info.artist,
        featuring=info.featuring,
        album=info.album,
        year=info.year,
    )


def game_record(s: SessionState, finished_at: int) -> GameRecord:
    ranking = standings(s)
    results = _final_results(s, ranking)
    assert results is not None
    return GameRecord(
        game_id=s.game.game_id,
        finished_at=finished_at,
        players=[
            ViewPlayer(
                id=p.id,
                nickname=p.nickname,
                online=False,
                is_host=p.role is Role.HOST,
                is_me=False,
                spectator=p.spectator,
                team=p.team,
            )
            for p in s.players.values()
            if p.id in standings_player_ids(s)
        ],
        results=results,
        teams=team_standings(s, ranking),
        started_at=s.game.started_wall_ms,
        settings=_settings(s),
        sources=[
            ArchiveSource(bridge_id=identity, name=name)
            for identity, name in sorted(
                {
                    (r.slot.track_ref.bridge_id, r.bridge_name)
                    for r in s.game.rounds
                    if r.official_start_at is not None and r.slot.track_ref is not None
                }
            )
        ],
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
            state="REVIEW",
            round_id=r.id,
            number=r.number,
            my_answer=_my_answer(r, p.id),
            auto_advance_at=r.auto_advance_at,
        )
    if r.state is RoundState.REVEALED:
        return _revealed(s, r)
    return None


def _round_host_pm(
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
            state="REVIEW",
            round_id=r.id,
            number=r.number,
            my_answer=_my_answer(r, p.id),
            auto_advance_at=r.auto_advance_at,
        )
    if r.state is RoundState.REVEALED:
        return _revealed(s, r)
    return None


def _round_mc(
    s: SessionState,
) -> RoundPending | RoundCountdown | RoundMcOpen | RoundPlayerReview | RoundRevealed | None:
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
            McOpenRow(
                player_id=p.id,
                validated=_status(r, p.id) is AnswerStatus.LOCKED,
                status=_status(r, p.id),
                text=(_shown_answer(r, p.id).text or _shown_answer(r, p.id).draft_text or None),
            )
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
        return RoundPlayerReview(
            state="REVIEW",
            round_id=r.id,
            number=r.number,
            my_answer=MyAnswer(status=AnswerStatus.NONE, text=None, draft_text=None),
            auto_advance_at=r.auto_advance_at,
        )
    if r.state is RoundState.REVEALED:
        return _revealed(s, r)
    return None


# --- host panel -----------------------------------------------------------------------------


def _settings(s: SessionState) -> GameSettings:
    settings = s.game.settings
    return GameSettings(
        selection_filter=ThemeFilter(**asdict(settings.selection_filter)),
        scoring_mode=settings.scoring_mode,
        acceptance_threshold=settings.acceptance_threshold,
        answer_fields=settings.answer_fields,
        album_points=settings.album_points,
        year_points=settings.year_points,
        featuring_points=settings.featuring_points,
        rounds=settings.rounds,
        clip_seconds=settings.clip_seconds,
        answer_grace_s=settings.answer_grace_s,
        sources=[SourceView(bridge_id=b, folder_prefix=f) for b, f in settings.sources],
        auto_start=settings.auto_start,
        prefetch_depth=settings.prefetch_depth,
        allow_repeats=settings.allow_repeats,
        answer_mode=settings.answer_mode,
        title_points=settings.title_points,
        artist_points=settings.artist_points,
        custom_points=settings.custom_points,
        auto_advance=settings.auto_advance,
        intermission_s=settings.intermission_s,
        instructions=settings.instructions,
        captured_policy=settings.captured_policy,
        normalize_audio=settings.normalize_audio,
        avoid_silence=settings.avoid_silence,
        balance_folders=settings.balance_folders,
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


def bridge_details(s: SessionState) -> list[BridgeDetail]:
    return [
        BridgeDetail(
            bridge_id=info.bridge_id,
            name=info.name,
            version=info.version,
            protocol=info.protocol,
            state=info.state,
            track_count=info.track_count,
            jobs_in_flight=sum(
                a.track_ref.bridge_id == info.bridge_id and a.state in IN_FLIGHT_ASSET_STATES
                for a in s.assets.values()
            ),
            formats=list(info.formats),
            allow_full_review=info.allow_full_review,
            source_error=info.source_error,
        )
        for info in sorted(s.bridges.values(), key=lambda b: (b.name.casefold(), b.bridge_id))
    ]


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
        if r.official_start_at is None:
            continue
        answer = _shown_answer(r, player_id)
        status = answer.status if answer.status is not AnswerStatus.DRAFT else AnswerStatus.NONE
        entries.append(
            HistoryEntry(
                judgement="criteria" if player_id in r.judgements else "manual",
                **r.judgements.get(player_id, {}),
                round_id=r.id,
                number=r.number,
                text=answer.text if status is not AnswerStatus.NONE else None,
                status=status,
                elapsed_ms=answer.elapsed_ms,
                order=answer.order,
                near_tie=answer.near_tie,
                points=(
                    s.journal.round_points(game_id, r.id, player_id)
                    if s.game.phase is GamePhase.FINAL_RESULTS
                    else r.score_draft.get(player_id, 0)
                )
                if r.included
                else 0,
                track=_reveal_track(r),
                received_at_wall_ms=answer.received_at_wall_ms,
                included=r.included,
            )
        )
    return entries


def _adjustments(s: SessionState, player_id: str) -> list[AdjustmentEntry]:
    numbers = {r.id: r.number for r in s.game.rounds}
    return [
        AdjustmentEntry(
            kind=event.kind.value,
            delta=event.delta,
            round_number=numbers.get(event.round_id) if event.round_id else None,
            note=event.note,
        )
        for event in s.journal.active(s.game.game_id)
        if event.kind in {ScoreKind.ADJUSTMENT, ScoreKind.FINAL_ADJUSTMENT}
        and event.player_id == player_id
    ]


def _final_rows(s: SessionState, ranking: list[StandingRow]) -> list[FinalReviewRow]:
    draft = s.game.final_draft
    return [
        FinalReviewRow(
            player_id=row.player_id,
            score_before=_draft_score(s, row.player_id)
            if s.game.phase is GamePhase.FINAL_SCORE_REVIEW
            else row.score,
            draft_delta=draft.get(row.player_id, 0),
            draft_note=s.game.final_notes.get(row.player_id),
            score_after=(
                _draft_score(s, row.player_id)
                if s.game.phase is GamePhase.FINAL_SCORE_REVIEW
                else row.score
            )
            + draft.get(row.player_id, 0),
            history=_history(s, row.player_id),
            adjustments=_adjustments(s, row.player_id),
        )
        for row in ranking
    ]


def _draft_score(s: SessionState, pid: str) -> int:
    return s.journal.score(s.game.game_id, pid) + sum(
        r.score_draft.get(pid, 0) for r in s.game.rounds if r.included
    )


def _finale(s: SessionState) -> Finale | None:
    if s.game.phase is not GamePhase.FINAL_SCORE_REVIEW:
        return None
    revealed = set(s.game.finale_revealed)
    played = [r for r in s.game.rounds if r.official_start_at is not None]
    scores = s.journal.scores(s.game.game_id)
    ids = standings_player_ids(s)
    totals = {
        pid: scores.get(pid, 0)
        + s.game.final_draft.get(pid, 0)
        + sum(
            r.score_draft.get(pid, 0)
            for r in played
            if r.included
            and r.id in revealed
            and (r.finale_awarded is None or pid in r.finale_awarded)
        )
        for pid in ids
    }
    ordered = sorted(ids, key=lambda pid: (-totals[pid], s.players[pid].join_seq))
    ranking = []
    previous, rank = None, 0
    for position, pid in enumerate(ordered, 1):
        if totals[pid] != previous:
            previous, rank = totals[pid], position
        ranking.append(StandingRow(player_id=pid, score=totals[pid], rank=rank))
    active = (
        next(iter(_review_rounds(s, only_id=s.game.finale_round_id)), None)
        if s.game.finale_round_id is not None
        else None
    )
    public = None
    if active is not None and active.round_id in revealed:
        source = next(r for r in played if r.id == active.round_id)
        public = FinaleRound(
            awards_pending=source.finale_wave_at is not None,
            round_id=active.round_id,
            number=active.number,
            track=active.track,
            included=active.included,
            answers=[
                FinaleAnswer(
                    player_id=a.player_id,
                    text=a.text,
                    points=a.points_draft
                    if active.included
                    and (source.finale_awarded is None or a.player_id in source.finale_awarded)
                    else 0,
                    reviewed=a.reviewed
                    and (source.finale_awarded is None or a.player_id in source.finale_awarded),
                    revision=a.score_revision
                    if source.finale_awarded is None or a.player_id in source.finale_awarded
                    else 0,
                    **{
                        f"{key}_correct": getattr(a, f"{key}_correct")
                        if source.finale_awarded is None or a.player_id in source.finale_awarded
                        else None
                        for key in ("title", "artist", "custom", "album", "year", "featuring")
                    },
                )
                for a in active.answers
            ],
        )
    visible = [r for r in played if r.included and r.id in revealed]
    return Finale(
        round=public,
        revealed_round_ids=s.game.finale_revealed,
        rounds_total=len(played),
        reviewed=sum(
            len(
                r.score_reviewed
                & set(rounds.review_player_ids(s, r))
                & (r.finale_awarded if r.finale_awarded is not None else r.score_reviewed)
            )
            for r in visible
        ),
        expected=sum(len(rounds.review_player_ids(s, r)) for r in played if r.included),
        standings=ranking,
        teams=team_standings(s, ranking),
    )


def _review_rounds(s: SessionState, *, only_id: str | None = None) -> list[ReviewRound]:
    result = []
    for r in s.game.rounds:
        if only_id is not None and r.id != only_id:
            continue
        if r.official_start_at is None and r.state is not RoundState.CANCELLED:
            continue
        bridge = s.bridges.get(r.slot.track_ref.bridge_id) if r.slot.track_ref else None
        asset = s.assets.get(r.slot.asset_id or "")
        reason = r.cancel_reason or r.close_reason
        result.append(
            ReviewRound(
                scoring_reference=MusicalMetadata.model_validate(asdict(r.auto_reference))
                if r.auto_reference
                else None,
                reference_changed=bool(
                    r.auto_reference
                    and r.slot.track_ref
                    and r.auto_reference != rounds.build_auto_reference(s, r)
                ),
                played=r.official_start_at is not None,
                round_id=r.id,
                number=r.number,
                track=_track_info(rounds.build_reveal(s, r)) if r.slot.track_ref else None,
                answers=_review_rows(s, r),
                included=r.included,
                state=r.state.value,
                close_reason=reason.value if reason else None,
                recovery_interrupted=r.recovery_interrupted,
                excerpt_duration_ms=asset.clip_duration_ms if asset else None,
                track_duration_ms=asset.track_duration_ms if asset else None,
                metadata_revision=r.metadata_revision,
                full_review_allowed=bool(bridge and bridge.allow_full_review),
                bridge_online=bool(bridge and bridge.state is BridgeState.ONLINE),
            )
        )
    return result


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
    private_sources = g.phase is not GamePhase.IN_GAME or p.host_mode is HostMode.MC
    missing = 0
    if g.phase is GamePhase.LOBBY:
        tagged = {asset.track_ref: asset for asset in s.assets.values()}
        for ref in selection.pool(s):
            meta = musical_metadata(s, ref)
            asset = tagged.get(ref)
            if any(
                not (
                    key not in (meta.cleared_fields or [])
                    and (
                        getattr(meta, key, None)
                        or getattr(asset, key, None)
                        or (meta.aliases or {}).get(key)
                    )
                )
                for key in auto_scoring.criteria(g.settings)
                if key != "custom"
            ):
                missing += 1
    return HostPanel(
        auto_missing_references=missing,
        settings=_settings(s)
        if private_sources
        else _settings(s).model_copy(update={"sources": []}),
        limits=_limits(s),
        commands=permissions.allowed(s, p),
        start_blockers=permissions.start_blockers(s) if g.phase is GamePhase.LOBBY else [],
        bridge=bridge_status(s)
        if private_sources
        else bridge_status(s).model_copy(update={"name": None}),
        pool=selection.pool_status(s) if g.phase in (GamePhase.LOBBY, GamePhase.IN_GAME) else None,
        players_ops=_players_ops(s),
        ready_check=_ready_check(s),
        undo_round_id=target.id if target is not None else None,
        last_play_id=r.plays[-1].play_id if r is not None and r.plays else None,
        final_review=_final_rows(s, standings(s))
        if g.phase is GamePhase.FINAL_SCORE_REVIEW
        else None,
        warnings=_warnings(s),
        history=[],
        history_count=len(s.archives),
        bridges=bridge_details(s) if private_sources else [],
        review_rounds=_review_rounds(s) if g.phase is GamePhase.FINAL_SCORE_REVIEW else [],
        joins_locked=s.joins_locked,
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
    return McPanel(
        current_track=current,
        upcoming=upcoming,
        manual_choices=manual.choices(s) if g.phase in {GamePhase.LOBBY, GamePhase.IN_GAME} else [],
        selection_revision=g.selection_revision,
    )
