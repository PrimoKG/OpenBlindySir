"""Game phases (spec §7.1), final review (§6.6), adjustments (§6.5) and Bridge events.

There is no path from IN_GAME to FINAL_RESULTS: every end goes through FINAL_SCORE_REVIEW.
"""

from openblindysir_protocol.enums import (
    AssetState,
    BridgeState,
    CancelReason,
    CloseReason,
    ConnectionState,
    EndGameMode,
    GamePhase,
    RoundState,
    ScoreKind,
)
from openblindysir_protocol.errors import CloseCode, ErrorCode
from openblindysir_protocol.host_commands import (
    EmptyArgs,
    HostAdjust,
    HostConfigure,
    HostEndGame,
    HostEndSession,
    HostFinaleReveal,
    HostFinaleStop,
    HostFinalReset,
    HostFinalSet,
    HostFinalValidate,
    HostJoinLock,
    HostNewGame,
    HostStartGame,
    HostToFinalReview,
)
from openblindysir_server.game import assets, auto_scoring, rounds, selection
from openblindysir_server.game import commands as c
from openblindysir_server.game.clock import Instant
from openblindysir_server.game.effects import (
    CancelJob,
    CloseConnection,
    EffectSink,
    Play,
    ResetSession,
    RevokeTokens,
    SendPlay,
)
from openblindysir_server.game.permissions import rule_ok, start_blockers
from openblindysir_server.game.rejections import require
from openblindysir_server.game.scoring import ScoreJournal
from openblindysir_server.game.standings import standings_player_ids
from openblindysir_server.game.state import (
    IN_FLIGHT_ASSET_STATES,
    BridgeInfo,
    Catalog,
    GameState,
    Player,
    SessionState,
    Settings,
    active_players,
    current_round,
)

IN_GAME_CONFIGURABLE = frozenset({"allow_repeats", "auto_start", "auto_advance", "intermission_s"})
EARLY_STATES = frozenset(
    {RoundState.QUEUED, RoundState.PREPARING, RoundState.LOADING, RoundState.COUNTDOWN}
)
BLOCKER_CODES = {
    "no_sources": ErrorCode.NO_SOURCES,
    "bridge_offline": ErrorCode.BRIDGE_OFFLINE,
    "no_competitors": ErrorCode.NO_COMPETITORS,
    "pool_exhausted": ErrorCode.POOL_EXHAUSTED,
}


def require_phase(s: SessionState, expected: GamePhase) -> None:
    require(s.game.phase == expected, ErrorCode.STALE_COMMAND)


def require_rule(cmd: str, s: SessionState, issuer: Player) -> None:
    require(rule_ok(cmd, s, issuer), ErrorCode.INVALID_STATE)


# --- start and configuration ---------------------------------------------------------------


def h_start_game(
    s: SessionState, issuer: Player, msg: HostStartGame, at: Instant, fx: EffectSink
) -> None:
    del issuer
    require_phase(s, msg.expected_phase)
    blockers = start_blockers(s)
    require(not blockers, BLOCKER_CODES[blockers[0].value] if blockers else ErrorCode.INVALID_STATE)
    g = s.game
    g.phase = GamePhase.IN_GAME
    g.started_wall_ms = at.wall_ms
    g.queue = selection.build_queue(s, include_played=g.settings.allow_repeats)
    s.touched = True
    fx.log("game_started", rounds=g.settings.rounds, pool=len(selection.pool(s)))
    rounds.start_round(s, at, fx)


def _maximum_points(settings: Settings) -> int:
    return sum(getattr(settings, f"{key}_points") for key in auto_scoring.criteria(settings))


def h_configure(
    s: SessionState, issuer: Player, msg: HostConfigure, at: Instant, fx: EffectSink
) -> None:
    require_phase(s, msg.expected_phase)
    require_rule("configure", s, issuer)
    patch = msg.args
    given = {name for name in type(patch).model_fields if getattr(patch, name) is not None}
    g = s.game
    require(not msg.start_game or g.phase is GamePhase.LOBBY, ErrorCode.INVALID_STATE)
    if g.phase is GamePhase.IN_GAME:
        require(given <= IN_GAME_CONFIGURABLE, ErrorCode.INVALID_STATE)
    if patch.clip_seconds is not None:
        require(
            s.config.clip_min_s <= patch.clip_seconds <= s.config.clip_max_s,
            ErrorCode.INVALID_ARGS,
        )
    if patch.sources is not None:
        known = set(s.catalogs) | set(s.bridges)
        require(all(src.bridge_id in known for src in patch.sources), ErrorCode.INVALID_ARGS)
    previous = g.settings
    settings = g.settings.copy()
    for name in given - {"sources"}:
        setattr(settings, name, getattr(patch, name))
    if patch.sources is not None:
        settings.sources = sorted({(src.bridge_id, src.folder_prefix) for src in patch.sources})
    require(_maximum_points(settings) <= 1000, ErrorCode.INVALID_ARGS)
    require(
        settings.scoring_mode != "auto" or settings.answer_mode != "custom", ErrorCode.INVALID_ARGS
    )
    g.settings = settings
    r = current_round(g)
    if (
        r is not None
        and r.state is RoundState.REVIEW
        and ({"auto_advance", "intermission_s"} & given)
    ):
        r.auto_advance_at = (
            at.mono_ms + settings.intermission_s * 1000 if settings.auto_advance else None
        )
        if r.paused_at is not None:
            r.paused_at = at.mono_ms
    if msg.start_game:
        blockers = start_blockers(s)
        if blockers:
            g.settings = previous
            require(False, BLOCKER_CODES[blockers[0].value])
    if patch.allow_repeats is not None:
        changed = previous.allow_repeats != settings.allow_repeats
        if changed and g.phase is GamePhase.IN_GAME:
            g.queue = selection.build_queue(s, include_played=patch.allow_repeats)
            if not patch.allow_repeats:
                selection.drop_played_from_idle_slots(s)
    if g.phase is GamePhase.LOBBY:
        selection.prune_manual_plans(s)
    s.touched = True
    fx.log("game_configured", fields=",".join(sorted(given)))
    if msg.start_game:
        h_start_game(
            s,
            issuer,
            HostStartGame(
                t="HOST", cmd="start_game", expected_phase=GamePhase.LOBBY, args=EmptyArgs()
            ),
            at,
            fx,
        )


# --- end of game ----------------------------------------------------------------------------


def h_finale_reveal(
    s: SessionState, issuer: Player, msg: HostFinaleReveal, at: Instant, fx: EffectSink
) -> None:
    del issuer, fx
    require_phase(s, msg.expected_phase)
    r = next((r for r in s.game.rounds if r.id == msg.args.round_id), None)
    require(r is not None and r.official_start_at is not None, ErrorCode.INVALID_ARGS)
    assert r is not None
    if msg.args.fast_forward:
        require(s.game.finale_round_id == msg.args.round_id, ErrorCode.STALE_COMMAND)
        r.finale_awarded = set(rounds.review_player_ids(s, r))
        r.finale_wave_at = None
        s.touched = True
        return
    if s.game.finale_round_id == msg.args.round_id:
        return
    # Finish a previous wave before changing stage; revisiting never repeats awards.
    for previous in s.game.rounds:
        if previous.finale_wave_at is not None:
            previous.finale_awarded = set(rounds.review_player_ids(s, previous))
            previous.finale_wave_at = None
    if r.auto_evidence and msg.args.round_id not in s.game.finale_revealed:
        r.finale_awarded = set()
        r.finale_wave_at = at.mono_ms + 1500
    s.game.finale_round_id = msg.args.round_id
    if msg.args.round_id not in s.game.finale_revealed:
        s.game.finale_revealed.append(msg.args.round_id)
    s.game.finale_play = None
    s.game.finale_audio_revision += 1
    s.touched = True


def advance_finale_awards(s: SessionState, r: object, at: Instant) -> None:
    from openblindysir_server.game.state import Round  # noqa: PLC0415

    assert isinstance(r, Round)
    awarded = r.finale_awarded
    if awarded is None:
        r.finale_wave_at = None
        return
    remaining = [pid for pid in rounds.review_player_ids(s, r) if pid not in awarded]
    awarded.update(remaining[:3])
    r.finale_wave_at = at.mono_ms + 1000 if len(remaining) > 3 else None
    s.touched = True


def h_finale_stop(
    s: SessionState, issuer: Player, msg: HostFinaleStop, at: Instant, fx: EffectSink
) -> None:
    del issuer, at, fx
    require_phase(s, msg.expected_phase)
    s.game.finale_play = None
    s.game.finale_audio_revision += 1
    s.touched = True


def handle_finale_replay(
    s: SessionState, cmd: c.FinaleReplayReady, at: Instant, fx: EffectSink
) -> None:
    issuer = s.players.get(cmd.player_id)
    require(
        issuer is not None
        and issuer.connection is not ConnectionState.REMOVED
        and issuer.role.value == "host",
        ErrorCode.NOT_HOST,
    )
    require(
        s.game.phase is GamePhase.FINAL_SCORE_REVIEW
        and s.game.game_id == cmd.game_id
        and s.game.finale_round_id == cmd.round_id,
        ErrorCode.STALE_COMMAND,
    )
    require(s.game.finale_audio_revision == cmd.revision, ErrorCode.STALE_COMMAND)
    r = next(r for r in s.game.rounds if r.id == cmd.round_id)
    asset = s.assets.get(r.slot.asset_id or "")
    require(asset is not None and asset.upload is not None, ErrorCode.REVIEW_UNAVAILABLE)
    assert asset is not None
    asset.state = AssetState.STORED
    start = at.mono_ms + s.config.lead_ms
    play = Play(s.ids.play_id(), asset.asset_id, start, 0.0, start + (asset.clip_duration_ms or 0))
    s.game.finale_play = play
    s.game.finale_audio_revision += 1
    s.touched = True
    fx.add(SendPlay(play))


def enter_final_review(s: SessionState, fx: EffectSink) -> None:
    g = s.game
    if g.phase is GamePhase.FINAL_SCORE_REVIEW:
        return
    for r in g.rounds:
        r.finale_wave_at = None
    r = current_round(g)
    if r is not None:
        rounds.stop_play(r, fx)
    g.phase = GamePhase.FINAL_SCORE_REVIEW
    g.ending = None
    g.final_draft = {}
    for slot in g.pipeline:
        if slot.track_ref is not None:
            g.queue.appendleft(slot.track_ref)
    g.pipeline.clear()
    s.touched = True
    fx.log("final_review_started", game_id=g.game_id)


def h_end_game(
    s: SessionState, issuer: Player, msg: HostEndGame, at: Instant, fx: EffectSink
) -> None:
    """Early end (spec §7.1 table): always through FINAL_SCORE_REVIEW."""
    if s.game.phase in {GamePhase.FINAL_SCORE_REVIEW, GamePhase.FINAL_RESULTS}:
        return  # repeated stop leaves all review drafts intact
    if msg.expected_phase is not None:
        require_phase(s, msg.expected_phase)
    elif s.game.phase is GamePhase.IN_GAME:
        rounds.current_by_key(s, msg.round_id or "")
    elif not any(r.id == msg.round_id for r in s.game.rounds):
        require(False, ErrorCode.STALE_COMMAND)
    require_rule("end_game", s, issuer)
    r = current_round(s.game)
    mode = msg.args.current_round
    if r is not None and r.state is RoundState.OPEN:
        rounds.close_round(s, r, at, CloseReason.END_GAME, fx)
    if r is not None and (mode is EndGameMode.ABANDON or r.state in EARLY_STATES):
        rounds.cancel_round(s, r, CancelReason.END_GAME, fx)
    enter_final_review(s, fx)
    s.touched = True
    fx.log("game_end_requested", mode=mode.value)


def h_to_final_review(
    s: SessionState, issuer: Player, msg: HostToFinalReview, at: Instant, fx: EffectSink
) -> None:
    del at
    rounds.current_by_key(s, msg.round_id)
    require_rule("to_final_review", s, issuer)
    enter_final_review(s, fx)


def h_final_set(
    s: SessionState, issuer: Player, msg: HostFinalSet, at: Instant, fx: EffectSink
) -> None:
    """Sets the VALUE of a final adjustment draft (not an increment); never an event."""
    del at, fx
    require_phase(s, msg.expected_phase)
    require_rule("final_set", s, issuer)
    require(msg.args.player_id in standings_player_ids(s), ErrorCode.UNKNOWN_PLAYER)
    require(
        msg.args.expected_delta is None
        or (
            s.game.final_draft.get(msg.args.player_id, 0) == msg.args.expected_delta
            and s.game.final_notes.get(msg.args.player_id) == msg.args.expected_note
        ),
        ErrorCode.STALE_COMMAND,
    )
    if msg.args.delta and msg.args.note:
        s.game.final_notes[msg.args.player_id] = msg.args.note.strip()
    else:
        s.game.final_notes.pop(msg.args.player_id, None)
    if msg.args.delta == 0:
        s.game.final_draft.pop(msg.args.player_id, None)
    else:
        s.game.final_draft[msg.args.player_id] = msg.args.delta
    s.touched = True


def h_final_reset(
    s: SessionState, issuer: Player, msg: HostFinalReset, at: Instant, fx: EffectSink
) -> None:
    del at, fx
    require_phase(s, msg.expected_phase)
    require_rule("final_reset", s, issuer)
    s.game.final_draft = {}
    s.game.final_notes = {}
    s.touched = True


def h_final_validate(
    s: SessionState, issuer: Player, msg: HostFinalValidate, at: Instant, fx: EffectSink
) -> None:
    """One ``final_adjustment`` per non-zero draft delta, then FINAL_RESULTS (scores frozen).

    Idempotent through ``expected_phase``: a second click finds FINAL_RESULTS and is stale.
    """
    require_phase(s, msg.expected_phase)
    require_rule("final_validate", s, issuer)
    g = s.game
    eligible = [r for r in g.rounds if r.included and r.official_start_at is not None]
    require(
        all(set(rounds.review_player_ids(s, r)) <= r.score_reviewed for r in eligible)
        or msg.args.confirm_unreviewed,
        ErrorCode.UNREVIEWED_SCORES,
    )
    for r in eligible:
        r.finale_wave_at = None
        events = []
        for pid in rounds.review_player_ids(s, r):
            points = r.score_draft.get(pid, 0)
            if points:
                event = s.journal.append(
                    game_id=g.game_id,
                    player_id=pid,
                    delta=points,
                    kind=ScoreKind.ROUND,
                    by=issuer.id,
                    at_wall_ms=at.wall_ms,
                    round_id=r.id,
                )
                events.append(event.id)
        r.published_event_ids = tuple(events)
        r.published_at = at.mono_ms
        r.reveal = rounds.build_reveal(s, r)
        r.state = RoundState.REVEALED
    present = set(standings_player_ids(s))
    corrections = 0
    for player_id, delta in g.final_draft.items():
        if delta and player_id in present:
            s.journal.append(
                game_id=g.game_id,
                player_id=player_id,
                delta=delta,
                kind=ScoreKind.FINAL_ADJUSTMENT,
                note=g.final_notes.get(player_id),
                by=issuer.id,
                at_wall_ms=at.wall_ms,
            )
            corrections += 1
    s.journal.freeze(g.game_id)
    g.final_draft = {}
    g.final_notes = {}
    g.finalized_at = at.mono_ms
    g.finalized_wall_ms = at.wall_ms
    g.phase = GamePhase.FINAL_RESULTS
    g.finale_play = None
    from openblindysir_server.game import views  # noqa: PLC0415 - build the final snapshot

    s.archives.append(views.game_record(s, at.wall_ms).model_dump(mode="json"))
    from openblindysir_server.game.history import retained  # noqa: PLC0415

    s.archives = retained(s.archives, at.wall_ms)
    s.touched = True
    fx.log("final_validated", corrections=corrections)


def h_join_lock(
    s: SessionState, issuer: Player, msg: HostJoinLock, at: Instant, fx: EffectSink
) -> None:
    del issuer, at, fx
    require_phase(s, msg.expected_phase)
    s.joins_locked = msg.args.locked
    s.touched = True


def h_new_game(
    s: SessionState, issuer: Player, msg: HostNewGame, at: Instant, fx: EffectSink
) -> None:
    del issuer, at
    require_phase(s, msg.expected_phase)
    s.game = GameState(game_id=s.ids.game_id(), settings=s.game.settings.copy())
    if msg.args.reset_library:
        s.played.clear()
        s.consumed_cancelled.clear()
    # Completed results are self-contained in the bounded archive, not a growing journal.
    s.journal = ScoreJournal()
    s.players = {p.id: p for p in active_players(s)}
    s.assets = {}
    s.jobs = {}
    s.asset_ready = {}
    s.touched = True
    fx.log("game_created", game_id=s.game.game_id)


def h_end_session(
    s: SessionState, issuer: Player, msg: HostEndSession, at: Instant, fx: EffectSink
) -> None:
    """Every token revoked, everyone disconnected, empty LOBBY; catalogues are kept."""
    del issuer, at
    require_phase(s, msg.expected_phase)
    for asset in s.assets.values():
        if asset.state in IN_FLIGHT_ASSET_STATES:
            fx.add(CancelJob(asset.track_ref.bridge_id, asset.job_id))
    for p in active_players(s):
        fx.add(CloseConnection(p.id, CloseCode.SESSION_ENDED))
    fx.add(RevokeTokens("ALL"))
    fx.add(ResetSession())
    s.epoch = s.ids.epoch()
    s.players = {}
    s.joins_locked = False
    s.game = GameState(game_id=s.ids.game_id(), settings=s.game.settings.copy())
    s.journal = ScoreJournal()
    s.played = set()
    s.consumed_cancelled.clear()
    s.assets = {}
    s.jobs = {}
    s.asset_ready = {}
    s.join_seq = 0
    s.touched = True
    fx.log("session_ended")


def h_adjust(s: SessionState, issuer: Player, msg: HostAdjust, at: Instant, fx: EffectSink) -> None:
    """Immediate correction during IN_GAME: an ``adjustment`` event (spec §6.5)."""
    require_phase(s, msg.expected_phase)
    args = msg.args
    g = s.game
    require(args.op_id not in g.applied_op_ids, ErrorCode.STALE_COMMAND)
    require_rule("adjust", s, issuer)
    target = s.players.get(args.player_id)
    require(
        target is not None and target.connection is not ConnectionState.REMOVED,
        ErrorCode.UNKNOWN_PLAYER,
    )
    if args.round_id is not None:
        require(any(r.id == args.round_id for r in g.rounds), ErrorCode.INVALID_ARGS)
    require(not s.journal.is_frozen(g.game_id), ErrorCode.SCORES_FROZEN)
    s.journal.append(
        game_id=g.game_id,
        player_id=args.player_id,
        delta=args.delta,
        kind=ScoreKind.ADJUSTMENT,
        by=issuer.id,
        at_wall_ms=at.wall_ms,
        round_id=args.round_id,
        note=args.note,
    )
    g.applied_op_ids.add(args.op_id)
    s.touched = True
    fx.log("score_adjusted", player_id=args.player_id, delta=args.delta)


# --- Bridge events ---------------------------------------------------------------------------


def handle_bridge_connected(
    s: SessionState, cmd: c.BridgeConnected, at: Instant, fx: EffectSink
) -> None:
    del at
    catalog = s.catalogs.get(cmd.bridge_id)
    synced = catalog is not None and catalog.catalog_hash == cmd.catalog_hash
    s.bridges[cmd.bridge_id] = BridgeInfo(
        bridge_id=cmd.bridge_id,
        name=cmd.name,
        version=cmd.version,
        state=BridgeState.ONLINE if synced else BridgeState.SYNCING,
        catalog_hash=cmd.catalog_hash,
        track_count=cmd.track_count,
        protocol=cmd.protocol,
        formats=cmd.formats,
        allow_full_review=cmd.allow_full_review,
        source_error=catalog.source_error if catalog else None,
    )
    if catalog is not None:
        catalog.bridge_name = cmd.name
    if synced and s.game.phase is GamePhase.IN_GAME:
        s.game.queue = selection.build_queue(s, include_played=s.game.settings.allow_repeats)
    assets.wake_waiting_slots(s, cmd.bridge_id)
    s.touched = True
    fx.log("bridge_connected", bridge_id=cmd.bridge_id, synced=synced)


def handle_bridge_disconnected(
    s: SessionState, cmd: c.BridgeDisconnected, at: Instant, fx: EffectSink
) -> None:
    del at
    info = s.bridges.get(cmd.bridge_id)
    if info is None or info.state is BridgeState.OFFLINE:
        return
    info.state = BridgeState.OFFLINE
    assets.fail_in_flight_of_bridge(s, cmd.bridge_id, fx)
    s.touched = True
    fx.log("bridge_lost", bridge_id=cmd.bridge_id)


def handle_catalog_loaded(
    s: SessionState, cmd: c.CatalogLoaded, at: Instant, fx: EffectSink
) -> None:
    del at
    previous = s.catalogs.get(cmd.bridge_id)
    s.catalogs[cmd.bridge_id] = Catalog(
        bridge_id=cmd.bridge_id,
        bridge_name=cmd.bridge_name,
        catalog_hash=cmd.catalog_hash,
        entries=dict(cmd.entries),
        scanned_folders=list(cmd.scanned_folders),
        source_error=cmd.source_error,
        ambiguous_paths=cmd.ambiguous_paths,
        scan_revision=(previous.scan_revision if previous else 0) + 1,
    )
    info = s.bridges.get(cmd.bridge_id)
    if info is not None and info.state is not BridgeState.OFFLINE:
        info.state = BridgeState.ONLINE
        info.catalog_hash = cmd.catalog_hash
        info.track_count = len(cmd.entries)
        info.source_error = cmd.source_error
    if s.game.phase is GamePhase.IN_GAME:
        s.game.queue = selection.build_queue(s, include_played=s.game.settings.allow_repeats)
    assets.wake_waiting_slots(s, cmd.bridge_id)
    s.touched = True
    fx.log("catalog_received", bridge_id=cmd.bridge_id, tracks=len(cmd.entries))
