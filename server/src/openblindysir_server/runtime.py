"""Runtime: the shell around the pure core.

``dispatch`` is SYNCHRONOUS: the core mutates, then the effects are executed by queueing
messages (never awaiting), then the cache retention and the next timer are updated.
Commands produced while executing effects are dispatched FIFO in the same call.
"""

import asyncio
import contextlib
from collections import deque
from dataclasses import dataclass, field

from openblindysir_protocol.enums import AnswerAckStatus, JobFailureCode
from openblindysir_protocol.errors import CloseCode
from openblindysir_protocol.server import AnswerAck, ErrorMsg, PlayMsg, StopMsg
from openblindysir_protocol.views import AnyView
from openblindysir_server.audio.cache import AudioCache
from openblindysir_server.auth.sessions import SessionRegistry
from openblindysir_server.config import Settings
from openblindysir_server.game import Clock, GameEngine, Instant
from openblindysir_server.game import commands as c
from openblindysir_server.game import effects as e
from openblindysir_server.logging import get, log_event
from openblindysir_server.persistence import SnapshotStore
from openblindysir_server.ws.bridge_link import BridgeLink
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

    def __post_init__(self) -> None:
        self.timers = TimerDriver(self)
        if self.settings.state_dir is not None:
            self.snapshots = SnapshotStore(self.settings.state_dir, self.settings.secrets)
            self.snapshots.restore(self.engine, self.sessions, self.clock.now())
            self.engine.state.persistence_status = "ready"

    def save_snapshot(self) -> None:
        if self.snapshots is None:
            return
        previous = self.engine.state.persistence_status
        try:
            self.snapshots.save(self.engine, self.sessions, self.clock.now())
            self.engine.state.persistence_status = "ready"
        except (OSError, ValueError):
            self.engine.state.persistence_status = "failed"
            log_event(LOG_GAME, "snapshot_failed")
        if previous != self.engine.state.persistence_status:
            self.hub.mark_dirty()

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
        try:
            while self._queue:
                command, when = self._queue.popleft()
                outcome = self.engine.dispatch(command, when or self.clock.now())
                first = first or outcome
                changed |= outcome.changed
                for effect in outcome.effects:
                    self._execute(effect)
        finally:
            self._running = False
        self.cache.retain(self.engine.retained_assets())
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
                self.hub.close_all(int(CloseCode.SESSION_ENDED))
                self.cache.clear()
                self.bridge.reset_tokens()
            case e.Log(event=event, fields=fields):
                log_event(LOG_GAME, event, **dict(fields))

    def shutdown(self) -> None:
        self.save_snapshot()
        self.timers.enabled = False
        self.timers.reschedule(None)
        self.hub.cancel_pending()
        with contextlib.suppress(Exception):
            self.hub.close_all(1001)
