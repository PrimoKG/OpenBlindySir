"""Fake players (spec §16, §20.2): integration tests and manual load tests.

Each bot joins with the game password, opens the player WebSocket, downloads each clip it
is offered (like a browser would), declares READY, and answers when the round is OPEN.
A host bot drives a complete game up to FINAL_RESULTS.

    uv run python tools/bots.py --server http://localhost:8000 --players 10 --rounds 2
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import random
import ssl
import sys
from collections.abc import Callable
from typing import Any

import httpx
import websockets

from openblindysir_protocol.version import PROTOCOL_VERSION

PROTOCOL = PROTOCOL_VERSION
CLOCK = {"offset": 0.0, "rtt_min": 5.0}
Predicate = Callable[[dict[str, Any]], bool]


class BotError(RuntimeError):
    pass


class Bot:
    def __init__(
        self,
        base_url: str,
        nickname: str,
        password: str,
        *,
        answer_delay_s: float = 0.2,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.origin = self.base_url
        self.nickname = nickname
        self.password = password
        self.answer_delay_s = answer_delay_s
        self.ssl_context = ssl_context
        self.socket_options: dict[str, Any] = (
            {"ssl": ssl_context} if self.base_url.startswith("https:") and ssl_context else {}
        )
        self.http = httpx.AsyncClient(
            base_url=self.base_url, timeout=10.0, verify=ssl_context or True
        )
        self.player_id: str | None = None
        self.view: dict[str, Any] = {}
        self.acks: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.plays: list[dict[str, Any]] = []
        self.received: list[dict[str, Any]] = []
        self.close_code: int | None = None
        self.answered: set[str] = set()
        self.ready_assets: set[str] = set()
        self.auto_answer = True
        self.answer_text: Callable[[str], str] = lambda rid: f"réponse de {self.nickname}"
        self._ws: Any = None
        self._reader: asyncio.Task[None] | None = None
        self._changed = asyncio.Event()
        self._tasks: set[asyncio.Task[None]] = set()

    # --- HTTP ---------------------------------------------------------------------------

    def cookie_header(self) -> str:
        return "; ".join(f"{name}={value}" for name, value in self.http.cookies.items())

    async def join(self) -> str:
        response = await self.http.post(
            "/api/session/join",
            json={"password": self.password, "nickname": self.nickname},
            headers={"Origin": self.origin},
        )
        if response.status_code != 200:
            raise BotError(f"join {self.nickname}: {response.status_code} {response.text}")
        player_id: str = response.json()["player_id"]
        self.player_id = player_id
        return player_id

    # --- WebSocket ----------------------------------------------------------------------

    async def connect(self) -> None:
        ws_url = self.base_url.replace("http", "ws", 1) + "/api/ws"
        self._ws = await websockets.connect(
            ws_url,
            additional_headers={"Cookie": self.cookie_header(), "Origin": self.origin},
            max_size=4 * 1024 * 1024,
            **self.socket_options,
        )
        await self.send({"t": "HELLO", "client_version": "bot", "protocol": PROTOCOL})
        await self.send({"t": "AUDIO_STATUS", "state": "IDLE", "clock": CLOCK})
        self._reader = asyncio.create_task(self._read())
        self._spawn(self._heartbeat())

    async def drop(self) -> None:
        """Abrupt network loss: the socket dies without a closing handshake."""
        transport = getattr(self._ws, "transport", None)
        if transport is not None:
            transport.abort()
        if self._reader is not None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(self._reader, 5)

    async def reconnect(self) -> None:
        """Same cookie, new socket; re-declares the clips it already has (kept buffers)."""
        self.view = {}
        await self.connect()
        current = await self.wait_for(lambda v: True)
        ref = (current.get("audio") or {}).get("current")
        if ref and ref["asset_id"] in self.ready_assets:
            await self.send(
                {"t": "AUDIO_STATUS", "state": "READY", "asset_id": ref["asset_id"], "clock": CLOCK}
            )

    async def raw_socket(self) -> Any:
        """A second, unmanaged connection with the same session (another tab)."""
        ws_url = self.base_url.replace("http", "ws", 1) + "/api/ws"
        ws = await websockets.connect(
            ws_url,
            additional_headers={"Cookie": self.cookie_header(), "Origin": self.origin},
            **self.socket_options,
        )
        await ws.send(json.dumps({"t": "HELLO", "client_version": "bot", "protocol": PROTOCOL}))
        return ws

    async def draft(self, round_id: str, text: str) -> None:
        await self.send({"t": "ANSWER_DRAFT", "round_id": round_id, "text": text})

    async def submit(self, round_id: str, text: str) -> None:
        await self.send({"t": "ANSWER_SUBMIT", "round_id": round_id, "text": text})

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
        await self.http.aclose()

    async def send(self, msg: dict[str, Any]) -> None:
        await self._ws.send(json.dumps(msg))

    async def _read(self) -> None:
        try:
            await self._read_loop()
        except websockets.ConnectionClosed as exc:
            self.close_code = exc.rcvd.code if exc.rcvd is not None else 1006
            return
        except Exception as exc:  # report instead of dying silently
            print(f"{self.nickname}: reader failed: {exc!r}", file=sys.stderr, flush=True)
            raise

    async def _read_loop(self) -> None:
        async for raw in self._ws:
            msg = json.loads(raw)
            self.received.append(msg)
            kind = msg["t"]
            if kind == "STATE":
                self.view = msg["view"]
                await self._react()
            elif kind == "ANSWER_ACK":
                self.acks.append(msg)
            elif kind == "ERROR":
                self.errors.append(msg["code"])
            elif kind == "PLAY":
                self.plays.append(msg)
            self._changed.set()

    async def _react(self) -> None:
        """Behave like a browser: fetch + decode offered clips, then answer when OPEN."""
        for slot in ("current", "next"):
            ref = (self.view.get("audio") or {}).get(slot)
            if ref and ref["asset_id"] not in self.ready_assets:
                self.ready_assets.add(ref["asset_id"])
                self._spawn(self._fetch_and_ready(ref))
        rnd = self.view.get("round")
        participant = self.view.get("me", {}).get("participant", False)
        if (
            self.auto_answer
            and participant
            and rnd
            and rnd.get("state") == "OPEN"
            and rnd["round_id"] not in self.answered
        ):
            self.answered.add(rnd["round_id"])
            self._spawn(self._answer(rnd["round_id"]))

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _heartbeat(self) -> None:
        """PING every 5 s like a browser; the server marks silent players OFFLINE."""
        loop = asyncio.get_running_loop()
        ws = self._ws
        while True:
            await asyncio.sleep(5)
            if ws is not self._ws:
                return  # a newer connection has its own heartbeat
            try:
                await ws.send(json.dumps({"t": "PING", "c": loop.time() * 1000}))
            except websockets.ConnectionClosed:
                return

    async def _fetch_and_ready(self, ref: dict[str, Any]) -> None:
        response = await self.http.get(ref["url"])
        if response.status_code == 200:
            await self.send(
                {"t": "AUDIO_STATUS", "state": "READY", "asset_id": ref["asset_id"], "clock": CLOCK}
            )
        else:
            self.ready_assets.discard(ref["asset_id"])

    async def _answer(self, round_id: str) -> None:
        await asyncio.sleep(self.answer_delay_s * random.uniform(0.5, 1.5))  # noqa: S311
        text = self.answer_text(round_id)
        await self.send({"t": "ANSWER_DRAFT", "round_id": round_id, "text": text[:3]})
        await self.send({"t": "ANSWER_SUBMIT", "round_id": round_id, "text": text})

    async def wait_for(self, predicate: Predicate, timeout_s: float = 30.0) -> dict[str, Any]:
        async def loop() -> dict[str, Any]:
            while not (self.view and predicate(self.view)):
                self._changed.clear()
                await self._changed.wait()
            return self.view

        try:
            return await asyncio.wait_for(loop(), timeout_s)
        except TimeoutError as exc:
            state = self.view.get("phase"), (self.view.get("round") or {}).get("state")
            raise BotError(f"{self.nickname}: timeout waiting, view at {state}") from exc


class HostBot(Bot):
    async def elevate(self, host_password: str) -> None:
        response = await self.http.post(
            "/api/session/host",
            json={"host_password": host_password},
            headers={"Origin": self.origin},
        )
        if response.status_code != 200:
            raise BotError(f"host elevation: {response.status_code}")

    async def host(self, cmd: str, args: dict[str, Any] | None = None, **key: Any) -> None:
        msg = {"t": "HOST", "cmd": cmd, "args": args or {}, **key}
        await self.send(msg)

    async def on_round(self, cmd: str, args: dict[str, Any] | None = None) -> None:
        await self.host(cmd, args, round_id=self.view["round"]["round_id"])

    async def on_phase(self, cmd: str, args: dict[str, Any] | None = None) -> None:
        await self.host(cmd, args, expected_phase=self.view["phase"])


def round_state(view: dict[str, Any]) -> str | None:
    return (view.get("round") or {}).get("state")


async def play_game(
    base_url: str,
    *,
    players: int,
    rounds: int,
    password: str,
    host_password: str,
    final_correction: int = 1,
    on_round: Callable[[int, HostBot, list[Bot]], Any] | None = None,
    ssl_context: ssl.SSLContext | None = None,
) -> dict[str, Any]:
    """Play a full game: join, configure, rounds (ready, play, answers, scoring), final review."""
    host = HostBot(base_url, "Hôte", password, ssl_context=ssl_context)
    bots = [
        Bot(base_url, f"Bot{i:02d}", password, ssl_context=ssl_context)
        for i in range(1, players + 1)
    ]
    everyone: list[Bot] = [host, *bots]
    try:
        for bot in everyone:
            await bot.join()
        await host.elevate(host_password)
        for bot in everyone:
            await bot.connect()
        await host.wait_for(
            lambda v: v.get("kind") == "host_player" and v["host"]["bridge"]["state"] == "ONLINE"
        )
        bridge_id = (await host.http.get("/api/host/library")).json()["bridges"][0]["bridge_id"]
        await host.on_phase(
            "configure",
            {
                "rounds": rounds,
                "clip_seconds": 10,
                "sources": [{"bridge_id": bridge_id, "folder_prefix": ""}],
            },
        )
        await host.wait_for(lambda v: v["host"]["settings"]["rounds"] == rounds)
        await host.on_phase("start_game")
        for number in range(1, rounds + 1):
            view = await host.wait_for(
                lambda v, n=number: (
                    v["phase"] == "FINAL_SCORE_REVIEW"
                    or (
                        (v.get("round") or {}).get("number") == n
                        and round_state(v) in ("OPEN", "REVIEW")
                    )
                ),
                timeout_s=90,
            )
            if on_round is not None:
                await on_round(number, host, bots)
            if round_state(view) == "OPEN":
                await host.wait_for(
                    lambda v: round_state(v) == "REVIEW" or v["phase"] == "FINAL_SCORE_REVIEW",
                    timeout_s=90,
                )
            if number < rounds:
                await host.on_round("next")
        await host.wait_for(lambda v: v["phase"] == "FINAL_SCORE_REVIEW")
        for review in host.view["host"]["review_rounds"]:
            for row in review["answers"]:
                points = 3 if row["order"] == 1 else 1 if row["status"] == "LOCKED" else 0
                await host.host(
                    "score_draft",
                    {"player_id": row["player_id"], "points": points},
                    round_id=review["round_id"],
                )
        await host.wait_for(
            lambda v: all(
                row["reviewed"] for r in v["host"]["review_rounds"] for row in r["answers"]
            )
        )
        await host.on_phase("final_set", {"player_id": host.player_id, "delta": final_correction})
        await host.wait_for(
            lambda v: any(r["draft_delta"] for r in v["host"]["final_review"] or [])
        )
        await host.on_phase("final_validate")
        final = await bots[0].wait_for(lambda v: v["phase"] == "FINAL_RESULTS")
        return {
            "final_results": final["final_results"],
            "acks": {b.nickname: [a["status"] for a in b.acks] for b in everyone},
            "errors": {b.nickname: b.errors for b in everyone if b.errors},
        }
    finally:
        for bot in everyone:
            await bot.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenBlindySir bots")
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--players", type=int, default=10)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--password", default=os.environ.get("BLIND_PASSWORD", ""))
    parser.add_argument("--host-password", default=os.environ.get("HOST_PASSWORD", ""))
    args = parser.parse_args(argv)
    result = asyncio.run(
        play_game(
            args.server,
            players=args.players,
            rounds=args.rounds,
            password=args.password,
            host_password=args.host_password,
        )
    )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
