"""Runtime: the shell around the pure core.

``dispatch`` is SYNCHRONOUS: the core mutates, then the effects are executed by queueing
messages (never awaiting), then the cache retention and the next timer are updated.
Commands produced while executing effects are dispatched FIFO in the same call.
"""

import asyncio
import contextlib
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field, replace

from openblindysir_protocol.enums import AnswerAckStatus, JobFailureCode, Role
from openblindysir_protocol.errors import CloseCode
from openblindysir_protocol.server import AnswerAck, ErrorMsg, PlayMsg, StopMsg
from openblindysir_protocol.views import AnyView
from openblindysir_server.audio.cache import AudioCache
from openblindysir_server.audio.review import ReviewTransfers
from openblindysir_server.auth.bridges import BridgeCredentials
from openblindysir_server.auth.sessions import SessionRegistry
from openblindysir_server.config import Settings
from openblindysir_server.game import Clock, GameEngine, Instant
from openblindysir_server.game import commands as c
from openblindysir_server.game import effects as e
from openblindysir_server.game.history import RETENTION_DAYS, retained
from openblindysir_server.game.state import Player, is_participant
from openblindysir_server.logging import get, log_event
from openblindysir_server.persistence import SnapshotStore
from openblindysir_server.ws.bridge_link import ActiveBridge, BridgeLink
from openblindysir_server.ws.hub import PlayerHub

LOG_GAME = get("game")
NORMAL_CLOSE = 1000
_ = AnyView, AnswerAckStatus


@dataclass(eq=False)
class TimerDriver:
    """Arms one loop timer at the core's next due instant; fires a Tick."""

    runtime: "Runtime"
    handle: asyncio.TimerHandle | None = None
    enabled: bool = True

    def reschedule(self, due_mono_ms: int | None) -> None:
        if self.handle is not None:
            self.handle.cancel()
            self.handle = None
        if due_mono_ms is None or not self.enabled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        delay_ms = max(0, due_mono_ms - self.runtime.clock.now().mono_ms)
        self.handle = loop.call_later(delay_ms / 1000, self._fire)

    def _fire(self) -> None:
        self.handle = None
        self.runtime.dispatch(c.Tick())


@dataclass(eq=False)
class Runtime:
    settings: Settings
    engine: GameEngine
    clock: Clock
    hub: PlayerHub
    bridge: BridgeLink
    cache: AudioCache
    sessions: SessionRegistry
    timers: TimerDriver = field(init=False)
    _queue: deque[tuple[c.Command, Instant | None]] = field(default_factory=deque)
    _running: bool = False
    snapshots: SnapshotStore | None = field(init=False, default=None)
    reviews: ReviewTransfers = field(default_factory=ReviewTransfers)
    credentials: BridgeCredentials = field(init=False)
    _history_purge_pending: bool = False

    def __post_init__(self) -> None:
        self.timers = TimerDriver(self)
        self.credentials = BridgeCredentials(
            self.settings.state_dir / "bridge-credentials.json"
            if self.settings.state_dir
            else None,
            self.settings.bridge_secret,
            self.settings.bridge_secrets,
        )
        if self.settings.state_dir is not None:
            self.snapshots = SnapshotStore(self.settings.state_dir, self.settings.secrets)
            self._history_purge_pending = self.snapshots.restore(
                self.engine, self.sessions, self.clock.now()
            )
            self.engine.state.persistence_status = "ready"

    def prune_history(self) -> None:
        records = self.engine.state.archives
        cutoff = self.clock.now().wall_ms - RETENTION_DAYS * 86_400_000
        if any(row["finished_at"] < cutoff for row in records):
            self.engine.state.archives = retained(records, self.clock.now().wall_ms)
            self._history_purge_pending = True
            self.engine.state.version += 1
            self.hub.mark_dirty()

    def save_snapshot(self) -> None:
        self.prune_history()
        if self.snapshots is None:
            return
        previous = self.engine.state.persistence_status
        try:
            self.snapshots.save(
                self.engine,
                self.sessions,
                self.clock.now(),
                purge_previous=self._history_purge_pending,
            )
            self._history_purge_pending = False
            self.engine.state.persistence_status = "ready"
        except (OSError, ValueError):
            self.engine.state.persistence_status = "failed"
            log_event(LOG_GAME, "snapshot_failed")
        if previous != self.engine.state.persistence_status:
            self.hub.mark_dirty()

    def commit_sessions(self, candidate: SessionRegistry, *, player: Player | None = None) -> bool:
        """Persist candidate credentials before changing live identities or closing sockets.

        Synchronous and without effects/awaits: a failed write leaves old tokens,
        pending approvals and participation intact. No full game/catalogue deepcopy.
        """
        self.prune_history()
        state = self.engine.state
        players = state.players if player is None else {**state.players, player.id: player}
        proposed = replace(state, players=players, version=state.version + 1)
        if self.snapshots is not None:
            proposed.persistence_status = "ready"
            try:
                self.snapshots.save(
                    self.engine,
                    candidate,
                    self.clock.now(),
                    purge_previous=self._history_purge_pending,
                    state=proposed,
                )
            except (OSError, ValueError):
                state.persistence_status = "failed"
                self.hub.mark_dirty()
                log_event(LOG_GAME, "snapshot_failed")
                return False
            self._history_purge_pending = False
        self.sessions = candidate
        state.players = players
        state.version = proposed.version
        state.persistence_status = proposed.persistence_status
        self.hub.mark_dirty()
        return True

    def transfer_identity(self, pid: str, candidate: SessionRegistry, now: int) -> str | None:
        player = replace(self.engine.state.players[pid])
        player.spectator = not is_participant(player)
        player.role = Role.PLAYER  # Shared access never grants host privileges.
        candidate.revoke((pid,))
        token = candidate.issue(pid, now)
        if not self.commit_sessions(candidate, player=player):
            return None
        self.hub.close(pid, int(CloseCode.SUPERSEDED))
        self.dispatch(c.Disconnected(pid))
        return token

    def session_candidate(self) -> SessionRegistry:
        return deepcopy(self.sessions)

    def bridge_credentials_current(self, bridge: ActiveBridge) -> bool:
        try:
            digest = self.credentials.active_hash(bridge.bridge_id)
            return digest is not None and digest == bridge.credential_hash
        except (OSError, ValueError):
            return False

    def refresh_bridge_credentials(self) -> None:
        for bridge in list(self.bridge.connections.values()):
            if not self.bridge_credentials_current(bridge):
                bridge.request_close(1008, "authentication")
                if self.bridge.deactivate(bridge):
                    self.dispatch(c.BridgeDisconnected(bridge.bridge_id))

    def view_json(self, player_id: str) -> str | None:
        if not self.engine.player_exists(player_id):
            return None
        return self.engine.view_for(player_id).model_dump_json()

    def post(self, cmd: c.Command) -> None:
        self._queue.append((cmd, None))

    def dispatch(self, cmd: c.Command, at: Instant | None = None) -> e.Outcome:
        """Dispatch a command and everything it triggers; returns the first outcome."""
        self._queue.append((cmd, at))
        if self._running:
            raise RuntimeError("Runtime.dispatch is not reentrant; use post()")
        self._running = True
        first: e.Outcome | None = None
        changed = False
        previous_archives = {row["game_id"] for row in self.engine.state.archives}
        try:
            while self._queue:
                command, when = self._queue.popleft()
                if isinstance(command, c.BridgeDisconnected):
                    self.reviews.bridge_disconnected(command.bridge_id)
                elif isinstance(command, c.UploadRejected):
                    self.reviews.reject(command.asset_id)
                outcome = self.engine.dispatch(command, when or self.clock.now())
                first = first or outcome
                changed |= outcome.changed
                for effect in outcome.effects:
                    self._execute(effect)
        finally:
            self._running = False
        self.cache.retain(self.engine.retained_assets())
        if previous_archives - {row["game_id"] for row in self.engine.state.archives}:
            self._history_purge_pending = True
        if changed:
            self.hub.mark_dirty()
        if changed or isinstance(cmd, c.DraftIn):
            self.save_snapshot()
        self.timers.reschedule(self.engine.next_wakeup())
        assert first is not None
        return first

    def _execute(self, effect: e.Effect) -> None:
        match effect:
            case e.SendPlay(play=play):
                self.hub.broadcast_critical(
                    PlayMsg(
                        t="PLAY",
                        play_id=play.play_id,
                        asset_id=play.asset_id,
                        start_at=play.start_at,
                        clip_offset=play.clip_offset_s,
                    )
                )
            case e.SendStop(play_id=play_id, stop_at=stop_at):
                self.hub.broadcast_critical(StopMsg(t="STOP", play_id=play_id, stop_at=stop_at))
            case e.SendAck(player_id=pid, round_id=rid, status=status, reason=reason):
                self.hub.send_critical(
                    pid, AnswerAck(t="ANSWER_ACK", round_id=rid, status=status, reason=reason)
                )
            case e.SendError(player_id=pid, code=code):
                self.hub.send_critical(pid, ErrorMsg(t="ERROR", code=code))
            case e.RequestPrepare():
                if not self.bridge.prepare(effect, self.clock.now().mono_ms):
                    self.post(c.JobFailedIn(effect.job_id, JobFailureCode.QUEUE_FULL))
            case e.CancelJob(job_id=job_id):
                self.bridge.cancel(job_id)
            case e.CloseConnection(player_id=pid, code=code):
                self.hub.close(pid, int(code) if code is not None else NORMAL_CLOSE)
            case e.RevokeTokens(player_ids=ids):
                if ids == "ALL":
                    self.sessions.revoke_all()
                else:
                    self.sessions.revoke(ids)
            case e.ResetSession():
                self.reviews.clear()
                self.hub.close_all(int(CloseCode.SESSION_ENDED))
                self.cache.clear()
                self.bridge.reset_tokens()
            case e.Log(event=event, fields=fields):
                log_event(LOG_GAME, event, **dict(fields))

    def shutdown(self) -> None:
        self.reviews.clear()
        self.save_snapshot()
        self.timers.enabled = False
        self.timers.reschedule(None)
        self.hub.cancel_pending()
        with contextlib.suppress(Exception):
            self.hub.close_all(1001)
