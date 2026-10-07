"""GameEngine: the single entry point of the pure core (``dispatch(command, at)``).

Each dispatch first applies the timed transitions due at or before ``at``, then validates
the command (a rejection leaves the state unchanged), mutates synchronously, settles the
derived rules and returns the effects for the shell to execute afterwards.
"""

import random
from collections.abc import Callable, Mapping
from typing import Any

from openblindysir_protocol.enums import AssetRole, ConnectionState, Role
from openblindysir_protocol.errors import ErrorCode
from openblindysir_protocol.http import LibraryResponse
from openblindysir_protocol.views import HostMcView, HostPlayerModeView, PlayerView
from openblindysir_server.game import (
    answers,
    assets,
    game_flow,
    library,
    manual,
    players,
    rounds,
    timers,
    views,
)
from openblindysir_server.game import commands as c
from openblindysir_server.game.clock import Instant
from openblindysir_server.game.config import CoreConfig
from openblindysir_server.game.effects import EffectSink, Outcome, SendError
from openblindysir_server.game.ids import IdFactory
from openblindysir_server.game.rejections import Rejected, require
from openblindysir_server.game.scoring import ScoreJournal
from openblindysir_server.game.state import AssetRecord, GameState, SessionState

Handler = Callable[[SessionState, Any, Instant, EffectSink], object]
HostHandler = Callable[[SessionState, Any, Any, Instant, EffectSink], None]

SETTLE_MAX_ITERATIONS = 16


def _tick(s: SessionState, cmd: c.Tick, at: Instant, fx: EffectSink) -> None:
    del s, cmd, at, fx


HOST_HANDLERS: dict[str, HostHandler] = {
    "select_track": manual.h_select_track,
    "configure": game_flow.h_configure,
    "set_mode": players.h_set_mode,
    "start_game": game_flow.h_start_game,
    "new_game": game_flow.h_new_game,
    "end_game": game_flow.h_end_game,
    "end_session": game_flow.h_end_session,
    "next": rounds.h_next,
    "force_start": rounds.h_force_start,
    "replay": rounds.h_replay,
    "stop": rounds.h_stop,
    "pause": rounds.h_pause,
    "resume": rounds.h_resume,
    "skip": rounds.h_skip,
    "add_time": rounds.h_add_time,
    "close": rounds.h_close,
    "score_draft": rounds.h_score_draft,
    "publish": rounds.h_publish,
    "track_metadata": rounds.h_track_metadata,
    "undo_publish": rounds.h_undo_publish,
    "adjust": game_flow.h_adjust,
    "to_final_review": game_flow.h_to_final_review,
    "final_set": game_flow.h_final_set,
    "final_reset": game_flow.h_final_reset,
    "final_validate": game_flow.h_final_validate,
    "finale_reveal": game_flow.h_finale_reveal,
    "finale_stop": game_flow.h_finale_stop,
    "kick": players.h_kick,
    "rename": players.h_rename,
    "participation": players.h_participation,
    "join_lock": game_flow.h_join_lock,
}


def _host(s: SessionState, cmd: c.HostIn, at: Instant, fx: EffectSink) -> None:
    """HOST check order: issuer is host, idempotency key, rule table, then mutation."""
    issuer = s.players.get(cmd.player_id)
    require(
        issuer is not None and issuer.connection is not ConnectionState.REMOVED,
        ErrorCode.UNKNOWN_PLAYER,
    )
    assert issuer is not None
    require(issuer.role is Role.HOST, ErrorCode.NOT_HOST)
    HOST_HANDLERS[cmd.msg.cmd](s, issuer, cmd.msg, at, fx)


HANDLERS: dict[type, Handler] = {
    c.Join: players.handle_join,
    c.Leave: players.handle_leave,
    c.Connected: players.handle_connected,
    c.Disconnected: players.handle_disconnected,
    c.ElevateHost: players.handle_elevate,
    c.AudioStatusIn: players.handle_audio_status,
    c.PlaybackReportIn: players.handle_playback_report,
    c.DraftIn: answers.handle_draft,
    c.SubmitIn: answers.handle_submit,
    c.HostIn: _host,
    c.FinaleReplayReady: game_flow.handle_finale_replay,
    c.BridgeConnected: game_flow.handle_bridge_connected,
    c.BridgeDisconnected: game_flow.handle_bridge_disconnected,
    c.CatalogLoaded: game_flow.handle_catalog_loaded,
    c.JobProgressIn: assets.handle_job_progress,
    c.UploadVerified: assets.handle_upload_verified,
    c.UploadRejected: assets.handle_upload_rejected,
    c.JobDoneIn: assets.handle_job_done,
    c.JobFailedIn: assets.handle_job_failed,
    c.CacheRefused: assets.handle_cache_refused,
    c.AssetEvicted: assets.handle_asset_evicted,
    c.Tick: _tick,
}

SETTLE_STEPS = (
    assets.settle_slots,
    rounds.promote,
    rounds.ready_check,
    rounds.auto_close,
    rounds.finish_last_round,
    assets.ensure_pipeline,
    assets.retire_unretained,
)


def settle(s: SessionState, at: Instant, fx: EffectSink) -> None:
    """Apply the derived rules until nothing changes."""
    for _ in range(SETTLE_MAX_ITERATIONS):
        changed = False
        for step in SETTLE_STEPS:
            changed |= step(s, at, fx)
        if not changed:
            return
    raise AssertionError("settle did not converge")


class GameEngine:
    def __init__(
        self, config: CoreConfig, *, ids: IdFactory, rng: random.Random, started_at: Instant
    ) -> None:
        self._s = SessionState(
            epoch=ids.epoch(),
            started_at=started_at,
            config=config,
            players={},
            game=GameState(game_id=ids.game_id()),
            journal=ScoreJournal(),
            played=set(),
            catalogs={},
            bridges={},
            assets={},
            jobs={},
            asset_ready={},
            ids=ids,
            rng=rng,
            last_at=started_at.mono_ms,
        )

    # --- mutation ---------------------------------------------------------------------------

    def dispatch(self, cmd: c.Command, at: Instant) -> Outcome:
        s = self._s
        fx = EffectSink()
        if at.mono_ms < s.last_at:
            fx.log("clock_clamped", by_ms=s.last_at - at.mono_ms)
            at = Instant(s.last_at, at.wall_ms)
        s.last_at = at.mono_ms
        s.touched = False
        timers.advance_to(s, at, fx, settle)
        error: ErrorCode | None = None
        value: object | None = None
        try:
            value = HANDLERS[type(cmd)](s, cmd, at, fx)
        except Rejected as rejection:
            error = rejection.code
            if isinstance(cmd, c.HostIn):
                fx.add(SendError(cmd.player_id, rejection.code))
        settle(s, at, fx)
        if s.touched:
            s.version += 1
        return Outcome(fx.freeze(), error, value, s.version, s.touched)

    def tick(self, at: Instant) -> Outcome:
        return self.dispatch(c.Tick(), at)

    # --- queries (no mutation) --------------------------------------------------------------

    @property
    def version(self) -> int:
        return self._s.version

    @property
    def state(self) -> SessionState:
        """Read-only by convention (tests, diagnostics)."""
        return self._s

    def next_wakeup(self) -> int | None:
        return timers.next_wakeup(self._s)

    def view_for(self, player_id: str) -> PlayerView | HostPlayerModeView | HostMcView:
        return views.view_for(self._s, player_id)

    def audio_servable(self) -> frozenset[str]:
        """Asset ids of ``audio.current``/``audio.next``: the same function as the views."""
        slots = views.audio_slots(self._s)
        return frozenset(ref.asset_id for ref in (slots.current, slots.next) if ref is not None)

    def retained_assets(self) -> Mapping[str, AssetRole]:
        return assets.retained_assets(self._s)

    def asset_info(self, asset_id: str) -> AssetRecord | None:
        return self._s.assets.get(asset_id)

    def player_exists(self, player_id: str) -> bool:
        p = self._s.players.get(player_id)
        return p is not None and p.connection is not ConnectionState.REMOVED

    def is_host(self, player_id: str) -> bool:
        p = self._s.players.get(player_id)
        return p is not None and p.connection is not ConnectionState.REMOVED and p.role is Role.HOST

    def catalog_needed(self, bridge_id: str, catalog_hash: str) -> bool:
        catalog = self._s.catalogs.get(bridge_id)
        return catalog is None or catalog.catalog_hash != catalog_hash

    def library(self) -> LibraryResponse:
        return library.library_response(self._s)

    def resolve_track_for_log(self, bridge_id: str, track_id: str) -> str | None:
        catalog = self._s.catalogs.get(bridge_id)
        entry = catalog.entries.get(track_id) if catalog is not None else None
        return entry.relpath if entry is not None else None
