#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.27", "websockets>=12"]
# ///
"""Smoke test of a running spike S0 server (no browser): HTTP routes, clips, WS PING/PONG,
voice assignment, PLAY/STOP/SYNC broadcast, /report and /results.json.

    uv run spikes/audio-sync/smoke_test.py [--base http://127.0.0.1:8077] [--token T]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time

import httpx
import websockets

MAGIC = {
    ".m4a": lambda b: b[4:8] == b"ftyp",
    ".webm": lambda b: b[:4] == b"\x1a\x45\xdf\xa3",
    ".ogg": lambda b: b[:4] == b"OggS",
    ".mp3": lambda b: b[:3] == b"ID3" or (b[0] == 0xFF and b[1] & 0xE0 == 0xE0),
}

failures: list[str] = []


def check(cond: bool, what: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        failures.append(what)


class FakeClient:
    def __init__(self, ws: websockets.ClientConnection) -> None:
        self.ws = ws
        self.welcome: dict = {}
        self.samples: list[tuple[float, float]] = []  # (rtt, theta)
        self.inbox: asyncio.Queue[dict] = asyncio.Queue()
        self.task = asyncio.create_task(self._reader())

    async def _reader(self) -> None:
        async for raw in self.ws:
            t1 = time.perf_counter() * 1000
            msg = json.loads(raw)
            if msg.get("t") == "PONG":
                t0 = msg["c"]
                self.samples.append((t1 - t0, msg["s"] - (t0 + t1) / 2))
            else:
                await self.inbox.put(msg)

    async def burst(self) -> None:
        for _ in range(8):
            await self.ws.send(json.dumps({"t": "PING", "c": time.perf_counter() * 1000}))
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)

    def estimate(self) -> tuple[float, float]:
        best = sorted(self.samples[-30:])[:3]
        return statistics.median(t for _, t in best), best[0][0]

    async def expect(self, kind: str, timeout: float = 3.0) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            msg = await asyncio.wait_for(self.inbox.get(), deadline - time.monotonic())
            if msg.get("t") == kind:
                return msg


async def run(base: str, token: str | None) -> None:
    q = {"token": token} if token else {}
    ws_base = base.replace("http", "ws", 1)
    async with httpx.AsyncClient(base_url=base, timeout=10) as http:
        print("HTTP")
        r = await http.get("/")
        check(r.status_code == 200 and "Tester mon audio" in r.text, "GET / serves the player page")
        check(
            r.headers.get("cache-control") == "no-store, private",
            "Cache-Control: no-store, private",
        )
        r = await http.get("/admin", params=q)
        check(r.status_code == 200 and "admin" in r.text, "GET /admin")
        for path in (
            "/static/app.js",
            "/static/clock.js",
            "/static/measure.js",
            "/static/admin.js",
        ):
            r = await http.get(path)
            check(
                r.status_code == 200 and "javascript" in r.headers.get("content-type", ""),
                f"GET {path}",
            )
        manifest = (await http.get("/api/manifest")).json()
        names = [c["name"] for c in manifest["clips"]]
        check(len(names) == 10, f"manifest lists 10 clips ({len(names)})")
        for c in manifest["clips"]:
            r = await http.get(f"/clips/{c['name']}")
            ext = c["name"][c["name"].rfind(".") :]
            check(
                r.status_code == 200
                and r.headers["content-type"].startswith(c["mime"])
                and MAGIC[ext](r.content)
                and len(r.content) == c["bytes"],
                f"GET /clips/{c['name']} ({len(r.content)} B, {r.headers['content-type']})",
            )
        r = await http.get("/clips/..%2Fserver.py")
        check(r.status_code == 404, "unknown clip name -> 404")

        print("WebSocket")
        async with (
            websockets.connect(f"{ws_base}/ws?cid=smoke-a") as wa,
            websockets.connect(f"{ws_base}/ws?cid=smoke-b") as wb,
        ):
            a, b = FakeClient(wa), FakeClient(wb)
            a.welcome, b.welcome = await a.expect("WELCOME"), await b.expect("WELCOME")
            check(a.welcome["client_id"] == "smoke-a", "WELCOME keeps the requested client id")
            check(
                a.welcome["voice"] != b.welcome["voice"],
                f"distinct voices ({a.welcome['voice']}, {b.welcome['voice']})",
            )
            await asyncio.gather(a.burst(), b.burst())
            check(len(a.samples) == 8 and len(b.samples) == 8, "8 PONG per burst")
            theta_a, rtt_a = a.estimate()
            check(all(r >= 0 for r, _ in a.samples), f"RTT >= 0 (min {rtt_a:.2f} ms)")
            print(f"       client A: theta={theta_a:.2f} ms rtt_min={rtt_a:.3f} ms")
            await wa.send(
                json.dumps(
                    {
                        "t": "AUDIO_STATUS",
                        "state": "READY",
                        "clock": {"offset": theta_a, "rtt_min": rtt_a},
                    }
                )
            )

            r = await http.post(
                "/report",
                json={
                    "client_id": "smoke-a",
                    "kind": "formats",
                    "results": [{"name": "x", "ok": True}],
                },
            )
            check(r.status_code == 200, "POST /report accepted")
            r = await http.post("/report", json={"client_id": "nobody", "kind": "formats"})
            check(r.status_code == 404, "POST /report with unknown client -> 404")

            sent_local = time.perf_counter() * 1000
            r = await http.post(
                "/api/admin/play", params=q, json={"kind": "calibration", "lead_ms": 3000}
            )
            check(r.status_code == 200, "POST /api/admin/play (calibration)")
            pa, pb = await a.expect("PLAY"), await b.expect("PLAY")
            check(
                pa["play_id"] == pb["play_id"] and pa["start_at"] == pb["start_at"],
                "same play_id/start_at for all",
            )
            check(
                pa["clip"] == f"calib_v{a.welcome['voice']}.m4a"
                and pb["clip"] == f"calib_v{b.welcome['voice']}.m4a",
                f"per-voice calibration clips ({pa['clip']}, {pb['clip']})",
            )
            lead_local = pa["start_at"] - theta_a - sent_local
            check(
                2900 < lead_local < 3100,
                f"start_at is ~3000 ms ahead in local time ({lead_local:.1f} ms)",
            )
            r = await http.post(
                "/api/admin/play",
                params=q,
                json={"kind": "clip", "clip": "test_opus.webm", "lead_ms": 1500},
            )
            pa = await a.expect("PLAY")
            check(pa["clip"] == "test_opus.webm", "PLAY test clip")
            await http.post("/api/admin/stop", params=q, json={})
            check((await a.expect("STOP"))["play_id"] == pa["play_id"], "STOP broadcast")
            await http.post("/api/admin/sync", params=q, json={})
            await b.expect("SYNC")
            check(True, "SYNC broadcast")

            state = (await http.get("/api/admin/state", params=q)).json()
            by_id = {c["id"]: c for c in state["clients"]}
            check(
                by_id["smoke-a"]["status"].get("state") == "READY",
                "AUDIO_STATUS visible in admin state",
            )
            results = (await http.get("/results.json", params=q)).json()
            check(
                any(c["id"] == "smoke-a" and c["reports"] for c in results["clients"]),
                "report stored in results.json",
            )
            check(len(results["plays"]) >= 2, "plays recorded")
            for t in (a.task, b.task):
                t.cancel()

        # reconnect with the same id gets the same voice back
        async with websockets.connect(f"{ws_base}/ws?cid=smoke-a") as wa2:
            w = json.loads(await wa2.recv())
            check(w["voice"] == a.welcome["voice"], "reconnect keeps the voice")

        print("Reconnection before the old socket is noticed dead")
        async with websockets.connect(f"{ws_base}/ws?cid=smoke-t&tab=page1") as old:
            w_old = json.loads(await old.recv())
            # same page, new socket, old one still open on the server side (network switch)
            async with websockets.connect(f"{ws_base}/ws?cid=smoke-t&tab=page1") as new:
                w_new = json.loads(await new.recv())
                check(
                    w_new["client_id"] == "smoke-t" and w_new["voice"] == w_old["voice"],
                    f"same page takes over: same id, same voice ({w_new['voice']})",
                )
                code = None
                try:
                    await asyncio.wait_for(old.recv(), 3.0)
                except websockets.ConnectionClosed as exc:
                    code = exc.rcvd.code if exc.rcvd else None
                check(code == 4000, f"old socket closed by the server (code {code})")
                await new.send(json.dumps({"t": "PING", "c": 0.0}))  # fresh last_seen
                # a duplicated tab (other page id, live socket): new identity and voice
                async with websockets.connect(f"{ws_base}/ws?cid=smoke-t&tab=page2") as dup:
                    w_dup = json.loads(await dup.recv())
                    check(
                        w_dup["client_id"] != "smoke-t" and w_dup["voice"] != w_new["voice"],
                        f"duplicated tab gets a new id ({w_dup['client_id']}) and voice "
                        f"({w_dup['voice']})",
                    )
                state = (await http.get("/api/admin/state", params=q)).json()
                entries = [c for c in state["clients"] if c["id"] == "smoke-t"]
                check(
                    len(entries) == 1 and entries[0]["connected"],
                    "one connected entry for smoke-t",
                )

        stale_s = state.get("stale_s", 15.0)
        if stale_s <= 3.0:
            async with websockets.connect(f"{ws_base}/ws?cid=smoke-s&tab=p") as ghost:
                await ghost.recv()
                await asyncio.sleep(stale_s + min(5.0, stale_s / 2) + 1.0)  # stay silent
                state = (await http.get("/api/admin/state", params=q)).json()
                entry = next(c for c in state["clients"] if c["id"] == "smoke-s")
                check(not entry["connected"], f"silent socket reaped after {stale_s:g} s")
        else:
            print(f"  skip stale-socket check (server --stale-s {stale_s:g} > 3)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8077")
    parser.add_argument("--token", default=None)
    args = parser.parse_args()
    asyncio.run(run(args.base, args.token))
    print(f"\n{'PASS' if not failures else 'FAIL'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
