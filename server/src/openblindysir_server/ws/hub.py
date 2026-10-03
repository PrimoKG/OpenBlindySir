"""Player WebSocket hub: connection registry, critical messages and batched STATE views.

``STATE.v`` is a per-connection counter bumped only when THIS recipient's serialised view
changed; a change invisible to a recipient sends it nothing (patch 2: no leak through
version gaps). Critical messages (PLAY, STOP, PONG, ANSWER_ACK, ERROR) are never delayed.
"""

import asyncio
import contextlib
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from starlette.websockets import WebSocket, WebSocketState

from openblindysir_protocol.base import OutboundModel
from openblindysir_protocol.enums import BrowserFamily
from openblindysir_server.logging import get, log_event
from openblindysir_server.ratelimit import TokenBucket

BATCH_DELAY_S = 0.05
CRITICAL_QUEUE_MAX = 64
LOG = get("ws")
ViewProvider = Callable[[str], OutboundModel]


@dataclass(eq=False)
class PlayerConnection:
    conn_id: int
    player_id: str
    ws: WebSocket
    ip: str
    browser_family: BrowserFamily
    last_rx_mono: int
    bucket: TokenBucket
    critical: deque[str] = field(default_factory=deque)
    pending_state: str | None = None
    last_sent_view_json: str | None = None
    state_seq: int = 0
    dropped: int = 0
    close_code: int | None = None
    wake: asyncio.Event = field(default_factory=asyncio.Event)

    def push_critical(self, text: str) -> None:
        if self.close_code is not None:
            return
        if len(self.critical) >= CRITICAL_QUEUE_MAX:
            self.critical.clear()
            self.pending_state = None
            self.request_close(1013)
            return
        self.critical.append(text)
        self.wake.set()

    def push_state(self, text: str) -> None:
        if self.close_code is not None:
            return
        self.pending_state = text
        self.wake.set()

    def request_close(self, code: int) -> None:
        if self.close_code is None:
            self.close_code = code
        self.wake.set()

    async def writer(self) -> None:
        """Drains critical messages first, then the latest STATE; honours close requests."""
        try:
            while True:
                await self.wake.wait()
                self.wake.clear()
                while self.critical:
                    await self.ws.send_text(self.critical.popleft())
                if self.pending_state is not None:
                    text, self.pending_state = self.pending_state, None
                    await self.ws.send_text(text)
                if self.close_code is not None:
                    if self.ws.application_state is WebSocketState.CONNECTED:
                        await self.ws.close(self.close_code)
                    return
        except Exception:
            return


def state_frame(seq: int, view_json: str) -> str:
    return f'{{"t":"STATE","v":{seq},"view":{view_json}}}'


class PlayerHub:
    def __init__(self, view_json: Callable[[str], str | None]) -> None:
        self._view_json = view_json
        self._current: dict[str, PlayerConnection] = {}
        self._next_id = 0
        self._flush_handle: asyncio.TimerHandle | None = None

    def next_conn_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def connections(self) -> list[PlayerConnection]:
        return list(self._current.values())

    def current(self, player_id: str) -> PlayerConnection | None:
        return self._current.get(player_id)

    def register(self, conn: PlayerConnection) -> PlayerConnection | None:
        """Last connection wins: returns the previous one, to be closed with 4001."""
        previous = self._current.get(conn.player_id)
        self._current[conn.player_id] = conn
        return previous

    def unregister(self, conn: PlayerConnection) -> bool:
        if self._current.get(conn.player_id) is conn:
            del self._current[conn.player_id]
            return True
        return False

    def send_critical(self, player_id: str, msg: OutboundModel) -> None:
        conn = self._current.get(player_id)
        if conn is not None:
            conn.push_critical(msg.model_dump_json())

    def send_on(self, conn: PlayerConnection, msg: OutboundModel) -> None:
        conn.push_critical(msg.model_dump_json())

    def broadcast_critical(self, msg: OutboundModel) -> None:
        text = msg.model_dump_json()
        for conn in self._current.values():
            conn.push_critical(text)

    def mark_dirty(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self.flush()
            return
        if self._flush_handle is None:
            self._flush_handle = loop.call_later(BATCH_DELAY_S, self.flush)

    def flush(self) -> None:
        self._flush_handle = None
        for conn in list(self._current.values()):
            self._send_view(conn)

    def _send_view(self, conn: PlayerConnection) -> None:
        view_json = self._view_json(conn.player_id)
        if view_json is None or view_json == conn.last_sent_view_json:
            return
        conn.state_seq += 1
        conn.last_sent_view_json = view_json
        conn.push_state(state_frame(conn.state_seq, view_json))

    def send_state_now(self, player_id: str) -> None:
        conn = self._current.get(player_id)
        if conn is not None:
            self._send_view(conn)

    def close(self, player_id: str, code: int) -> None:
        conn = self._current.pop(player_id, None)
        if conn is not None:
            conn.request_close(code)

    def close_all(self, code: int) -> None:
        for player_id in list(self._current):
            self.close(player_id, code)

    def cancel_pending(self) -> None:
        if self._flush_handle is not None:
            with contextlib.suppress(Exception):
                self._flush_handle.cancel()
            self._flush_handle = None


def log_refused(reason: str, ip: str) -> None:
    log_event(LOG, "ws_refused", reason=reason, ip=ip)
