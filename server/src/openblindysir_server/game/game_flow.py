"""Game phases (spec §7.1), final review (§6.6), adjustments (§6.5) and Bridge events.

There is no path from IN_GAME to FINAL_RESULTS: every end goes through FINAL_SCORE_REVIEW.
"""

from openblindysir_protocol.enums import (
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
    HostFinalReset,
    HostFinalSet,
    HostFinalValidate,
    HostNewGame,
    HostStartGame,
    HostToFinalReview,
)
from openblindysir_server.game import assets, rounds, selection
from openblindysir_server.game import commands as c
from openblindysir_server.game.clock import Instant
from openblindysir_server.game.effects import (
    CancelJob,
    CloseConnection,
    EffectSink,
    ResetSession,
    RevokeTokens,
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
    active_players,
    current_round,
)

IN_GAME_CONFIGURABLE = frozenset({"allow_repeats", "auto_start"})
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
    g.queue = selection.build_queue(s, include_played=g.settings.allow_repeats)
    s.touched = True
    fx.log("game_started", rounds=g.settings.rounds, pool=len(selection.pool(s)))
    rounds.start_round(s, at, fx)


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
    if patch.rounds is not None:
        settings.rounds = patch.rounds
    if patch.clip_seconds is not None:
        settings.clip_seconds = patch.clip_seconds
    if patch.answer_grace_s is not None:
        settings.answer_grace_s = patch.answer_grace_s
    if patch.sources is not None:
        settings.sources = sorted({(src.bridge_id, src.folder_prefix) for src in patch.sources})
    if patch.auto_start is not None:
        settings.auto_start = patch.auto_start
    if patch.prefetch_depth is not None:
        settings.prefetch_depth = patch.prefetch_depth
    if patch.allow_repeats is not None:
        settings.allow_repeats = patch.allow_repeats
    for name in (
        "answer_mode",
        "title_points",
        "artist_points",
        "instructions",
        "captured_policy",
        "normalize_audio",
        "avoid_silence",
    ):
        value = getattr(patch, name)
        if value is not None:
            setattr(settings, name, value)
    g.settings = settings
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


def enter_final_review(s: SessionState, fx: EffectSink) -> None:
    g = s.game
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
    r = rounds.current_by_key(s, msg.round_id)
    require_rule("end_game", s, issuer)
    mode = msg.args.current_round
    if r.state is RoundState.REVEALED:
        enter_final_review(s, fx)
    elif mode is EndGameMode.ABANDON or r.state in EARLY_STATES:
        rounds.cancel_round(s, r, CancelReason.END_GAME, fx)
        enter_final_review(s, fx)
    elif r.state is RoundState.OPEN:
        rounds.close_round(s, r, at, CloseReason.END_GAME, fx)
        s.game.ending = EndGameMode.SCORE
    else:  # REVIEW: publish then final review
        s.game.ending = EndGameMode.SCORE
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
    present = set(standings_player_ids(s))
    corrections = 0
    for player_id, delta in g.final_draft.items():
        if delta and player_id in present:
            s.journal.append(
                game_id=g.game_id,
                player_id=player_id,
                delta=delta,
                kind=ScoreKind.FINAL_ADJUSTMENT,
                by=issuer.id,
                at_wall_ms=at.wall_ms,
            )
            corrections += 1
    s.journal.freeze(g.game_id)
    g.final_draft = {}
    g.finalized_at = at.mono_ms
    g.finalized_wall_ms = at.wall_ms
    g.phase = GamePhase.FINAL_RESULTS
    from openblindysir_server.game import views  # noqa: PLC0415 - build the final snapshot

    s.archives.append(views.game_record(s, at.wall_ms).model_dump(mode="json"))
    s.archives = s.archives[-50:]
    s.touched = True
    fx.log("final_validated", corrections=corrections)


def h_new_game(
    s: SessionState, issuer: Player, msg: HostNewGame, at: Instant, fx: EffectSink
) -> None:
    del issuer, at
    require_phase(s, msg.expected_phase)
    s.game = GameState(game_id=s.ids.game_id(), settings=s.game.settings.copy())
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
    s.game = GameState(game_id=s.ids.game_id(), settings=s.game.settings.copy())
    s.journal = ScoreJournal()
    s.played = set()
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
    )
    if catalog is not None:
        catalog.bridge_name = cmd.name
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
    s.catalogs[cmd.bridge_id] = Catalog(
        bridge_id=cmd.bridge_id,
        bridge_name=cmd.bridge_name,
        catalog_hash=cmd.catalog_hash,
        entries=dict(cmd.entries),
    )
    info = s.bridges.get(cmd.bridge_id)
    if info is not None and info.state is not BridgeState.OFFLINE:
        info.state = BridgeState.ONLINE
        info.catalog_hash = cmd.catalog_hash
        info.track_count = len(cmd.entries)
    if s.game.phase is GamePhase.IN_GAME:
        s.game.queue = selection.build_queue(s, include_played=s.game.settings.allow_repeats)
    assets.wake_waiting_slots(s, cmd.bridge_id)
    s.touched = True
    fx.log("catalog_received", bridge_id=cmd.bridge_id, tracks=len(cmd.entries))
