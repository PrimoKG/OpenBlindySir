# /// script
# requires-python = ">=3.12"
# dependencies = ["fastapi>=0.115", "uvicorn[standard]>=0.30", "httpx>=0.27"]
# ///
"""Spike S1 relay server: stands in for the game server's Bridge endpoints (spec §8.3).

Self-contained (one file to copy on the VPS). Runs behind Caddy for TLS (see README), or
locally on 127.0.0.1 for a dry run.

Endpoints
    WS   /bridge             Authorization: Bearer $SPIKE_SECRET. HELLO -> WELCOME, PREPARE jobs,
                             JOB_PROGRESS / JOB_DONE / JOB_FAILED, PING/PONG every 15 s.
    PUT  /catalog            gzip JSON catalog, one-shot token from WELCOME (Bearer).
    PUT  /upload/{job_id}    clip, one-shot upload token (Bearer) + X-Clip-SHA256; cut at 2 MB,
                             magic bytes + sha256 checked, kept in RAM only, then dropped.
    POST /run?n=20           n sequential PREPARE on random track_ids of the connected Bridge
                             (&duration=30 &crafted=1 &seed=.. &wait=1). Admin: Bearer $SPIKE_SECRET.
    POST /poke               sends hostile/unknown messages to the Bridge (closed-protocol test).
    GET  /stats              per-job timings (PREPARE sent -> upload complete), p50/p95/max,
                             G2 verdict (p95 < 5 s). &format=text for a table. Admin.
    GET  /healthz

Usage
    SPIKE_SECRET=... uv run relay_server.py serve [--host 127.0.0.1] [--port 8765]
    SPIKE_SECRET=... uv run relay_server.py trigger --url https://relay.example.org -n 20
                                                    [--duration 30] [--crafted]
    SPIKE_SECRET=... uv run relay_server.py stats --url https://relay.example.org

No file names are ever received: the catalog holds relpaths (spec §11 documents that leak),
the relay prints only track_ids and counters.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import math
import os
import random
import secrets
import sys
import time
import zlib
from collections import Counter
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse, PlainTextResponse

PROTOCOL = 1
MAX_CLIP_BYTES = 2 * 1024 * 1024
MAX_CATALOG_GZ = 16 * 1024 * 1024
MAX_CATALOG_RAW = 128 * 1024 * 1024
MAX_WS_MESSAGE = 64 * 1024
PING_INTERVAL_S = 15.0
JOB_TIMEOUT_S = 120.0  # > ffprobe 10 + ffmpeg 30 + upload 60 on the Bridge side
G2_P95_MS = 5000.0
G2_MIN_SAMPLE = 20
# Failures caused by the file itself: excluded from the G2 time sample (listed separately).
# Every other failure (TIMEOUT, BRIDGE_OFFLINE, INVALID_UPLOAD, BRIDGE_BUSY, CANCELLED,
# INTERNAL, ...) is a pipeline/transport failure: it counts as an INFINITE time in the p95,
# and any such failure makes a passing p95 INCONCLUSIVE.
CONTENT_CODES = frozenset({"NOT_FOUND", "TOO_SHORT", "DECODE_ERROR"})
BRIDGE_CLIP_MAX_S = 30.0  # the spike Bridge clamps longer requests (bridge_common.CLIP_MAX_S)
CRAFTED_IDS = [
    "..",
    "../../../../Windows/win.ini",
    "C:\\Windows\\win.ini",
    "/etc/passwd",
    "t_0000000000000000",
    "file:C:/Windows/win.ini",
]


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S ") + msg, flush=True)


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile (conservative on small samples), same as the other tools."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, math.ceil(p / 100.0 * len(ordered))) - 1]


def catalog_hash(entries: list[dict]) -> str:
    canonical = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def bearer_ok(header: str | None, expected: str | None) -> bool:
    if not header or not expected or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header[7:].encode(), expected.encode())


def load_secret() -> str:
    secret = os.environ.get("SPIKE_SECRET", "")
    if len(secret) < 32 or secret.lower() in {"changeme", "secret"}:
        raise SystemExit(
            "SPIKE_SECRET missing or weak (< 32 chars). Generate one with:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    return secret


# --------------------------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------------------------


@dataclass
class Job:
    job_id: str
    run_id: str
    track_id: str
    start_fraction: float
    duration: float
    crafted: bool
    token: str | None
    status: str = "PENDING"  # PENDING | OK | FAILED
    code: str | None = None
    t_sent: float = 0.0
    t_upload_start: float | None = None
    t_upload_done: float | None = None
    t_reply: float | None = None
    bytes: int = 0
    upload_ok: bool = False
    report: dict = field(default_factory=dict)
    stages: dict = field(default_factory=dict)
    done: asyncio.Event = field(default_factory=asyncio.Event)

    def finish(self, status: str, code: str | None = None) -> None:
        if self.status == "PENDING":
            self.status, self.code = status, code
            self.token = None
        self.done.set()

    def total_ms(self) -> float | None:
        if self.t_upload_done is None:
            return None
        return (self.t_upload_done - self.t_sent) * 1000

    def public(self) -> dict:
        r = self.report
        timings = r.get("timings") or {}
        return {
            "job_id": self.job_id, "run_id": self.run_id, "track_id": self.track_id,
            "crafted": self.crafted, "status": self.status, "code": self.code,
            "start_fraction": round(self.start_fraction, 4), "duration": self.duration,
            "total_ms": _r(self.total_ms()),
            "server_upload_ms": _r(None if self.t_upload_start is None or self.t_upload_done is None
                                   else (self.t_upload_done - self.t_upload_start) * 1000),
            "reply_ms": _r(None if self.t_reply is None else (self.t_reply - self.t_sent) * 1000),
            "bytes": self.bytes, "actual_start": r.get("actual_start"),
            "clip_duration": r.get("clip_duration"), "track_duration": r.get("track_duration"),
            "bridge_timings": timings,
            "has_tags": bool(r.get("tags")),
        }


def _r(v: float | None) -> float | None:
    return None if v is None else round(v, 1)


@dataclass
class BridgeConn:
    ws: object
    peer: str
    user_agent: str
    hello: dict = field(default_factory=dict)
    connected_at: float = field(default_factory=time.time)
    rtts_ms: list[float] = field(default_factory=list)
    unknown_messages: int = 0


class State:
    def __init__(self) -> None:
        self.secret = ""
        self.bridge: BridgeConn | None = None
        self.catalogs: dict[str, dict] = {}  # bridge_id -> {hash, track_ids, ...}
        self.catalog_upload: dict | None = None  # {token, bridge_id, hash}
        self.jobs: dict[str, Job] = {}
        self.runs: dict[str, dict] = {}
        self.run_lock = asyncio.Lock()
        self.poke_replies: list[dict] = []
        self.events: list[str] = []
        self.connections = 0
        self.rejected = 0

    def event(self, msg: str) -> None:
        log(msg)
        self.events.append(time.strftime("%H:%M:%S ") + msg)
        del self.events[:-50]


STATE = State()


# --------------------------------------------------------------------------------------------
# FastAPI app
# --------------------------------------------------------------------------------------------


def build_app():
    app = FastAPI(title="OpenBlindySir S1 relay (spike)", docs_url=None, redoc_url=None,
                  openapi_url=None)

    def require_admin(request: Request) -> None:
        if not bearer_ok(request.headers.get("authorization"), STATE.secret):
            raise HTTPException(status_code=401, detail="unauthorized")

    async def send(conn: BridgeConn, msg: dict) -> None:
        await conn.ws.send_text(json.dumps(msg, separators=(",", ":")))  # type: ignore[attr-defined]

    @app.get("/healthz")
    async def healthz():
        return {"ok": True, "bridge": STATE.bridge is not None}

    # ---------------------------------------------------------------- WebSocket /bridge
    @app.websocket("/bridge")
    async def bridge_ws(ws: WebSocket):
        if not bearer_ok(ws.headers.get("authorization"), STATE.secret):
            STATE.rejected += 1
            STATE.event(f"bridge REJECTED (bad secret) from {ws.client.host if ws.client else '?'}")
            await ws.close(code=1008)  # before accept: the handshake gets HTTP 403
            return
        await ws.accept()
        conn = BridgeConn(ws=ws, peer=ws.client.host if ws.client else "?",
                          user_agent=ws.headers.get("user-agent", ""))
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=10)
            hello = json.loads(raw)
            if hello.get("t") != "HELLO" or hello.get("protocol") != PROTOCOL:
                await ws.close(code=4002, reason="HELLO/protocol mismatch")
                STATE.event("bridge closed: bad HELLO or protocol")
                return
        except (asyncio.TimeoutError, json.JSONDecodeError, ValueError):
            await ws.close(code=4002, reason="HELLO expected")
            return
        conn.hello = {k: hello.get(k) for k in
                      ("bridge_id", "name", "version", "protocol", "catalog_hash", "track_count", "formats")}
        bridge_id = str(hello.get("bridge_id"))
        old = STATE.bridge
        if old is not None:
            try:
                await old.ws.close(code=4000, reason="superseded")  # type: ignore[attr-defined]
            except Exception:
                pass
        STATE.bridge = conn
        STATE.connections += 1
        known = STATE.catalogs.get(bridge_id, {}).get("hash")
        catalog_needed = known != hello.get("catalog_hash")
        welcome = {
            "t": "WELCOME", "protocol": PROTOCOL, "clip_format": "aac", "bitrate": 128,
            "limits": {"max_clip_s": 30, "max_bytes": MAX_CLIP_BYTES, "max_queue": 4},
            "catalog_needed": catalog_needed,
        }
        if catalog_needed:
            token = secrets.token_urlsafe(32)
            STATE.catalog_upload = {"token": token, "bridge_id": bridge_id,
                                    "hash": hello.get("catalog_hash")}
            welcome["catalog_upload_token"] = token
        await send(conn, welcome)
        STATE.event(f"bridge CONNECTED ua={conn.user_agent!r} tracks={hello.get('track_count')} "
                    f"catalog_needed={catalog_needed}")

        async def pinger():
            while True:
                await asyncio.sleep(PING_INTERVAL_S)
                await send(conn, {"t": "PING", "c": time.perf_counter()})

        ping_task = asyncio.create_task(pinger())
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                text = message.get("text")
                if text is None:
                    conn.unknown_messages += 1
                    continue
                if len(text) > MAX_WS_MESSAGE:
                    await ws.close(code=1009)
                    break
                try:
                    msg = json.loads(text)
                    kind = msg.get("t")
                except (json.JSONDecodeError, AttributeError):
                    conn.unknown_messages += 1
                    continue
                await handle_bridge_message(conn, kind, msg)
        except Exception as exc:  # noqa: BLE001 - spike: log and drop the connection
            STATE.event(f"bridge connection error: {exc.__class__.__name__}")
        finally:
            ping_task.cancel()
            if STATE.bridge is conn:
                STATE.bridge = None
                for job in STATE.jobs.values():
                    if job.status == "PENDING":
                        job.finish("FAILED", "BRIDGE_OFFLINE")
                STATE.event("bridge DISCONNECTED")

    async def handle_bridge_message(conn: BridgeConn, kind: object, msg: dict) -> None:
        now = time.perf_counter()
        if kind == "PONG":
            c = msg.get("c")
            if isinstance(c, (int, float)):
                conn.rtts_ms.append((now - c) * 1000)
                del conn.rtts_ms[:-100]
            return
        if kind == "PING":
            await send(conn, {"t": "PONG", "c": msg.get("c")})
            return
        if kind == "CATALOG_CHANGED":
            STATE.event("bridge says CATALOG_CHANGED (spike: reconnect to upload it)")
            return
        if kind in ("JOB_PROGRESS", "JOB_DONE", "JOB_FAILED"):
            job_id = msg.get("job_id")
            if isinstance(job_id, str) and job_id.startswith("poke-"):
                STATE.poke_replies.append(msg)
                return
            job = STATE.jobs.get(job_id) if isinstance(job_id, str) else None
            if job is None:
                STATE.event(f"{kind} for unknown job ignored")
                return
            if kind == "JOB_PROGRESS":
                job.stages[str(msg.get("stage"))[:16]] = round((now - job.t_sent) * 1000, 1)
            elif kind == "JOB_DONE":
                job.t_reply = now
                job.report = {k: msg.get(k) for k in
                              ("actual_start", "clip_duration", "track_duration", "bytes", "sha256",
                               "tags", "timings")}
                if job.upload_ok:
                    job.finish("OK")
                else:
                    job.finish("FAILED", "INVALID_UPLOAD")
            else:
                job.t_reply = now
                code = msg.get("code")
                job.finish("FAILED", str(code)[:32] if code else "UNKNOWN")
            return
        conn.unknown_messages += 1
        STATE.event(f"unknown message from bridge ignored (t={str(kind)[:24]!r})")

    # ---------------------------------------------------------------- PUT /catalog
    @app.put("/catalog")
    async def put_catalog(request: Request):
        pending = STATE.catalog_upload
        if pending is None or not bearer_ok(request.headers.get("authorization"), pending["token"]):
            raise HTTPException(status_code=403, detail="no catalog upload pending")
        STATE.catalog_upload = None  # one-shot
        t0 = time.perf_counter()
        body = bytearray()
        async for chunk in request.stream():
            body += chunk
            if len(body) > MAX_CATALOG_GZ:
                raise HTTPException(status_code=413, detail="catalog too large")
        try:
            d = zlib.decompressobj(wbits=31)
            raw = d.decompress(bytes(body), MAX_CATALOG_RAW)
            if d.unconsumed_tail:
                raise HTTPException(status_code=413, detail="catalog too large once inflated")
            data = json.loads(raw)
            entries = data["entries"]
            ids = [e["track_id"] for e in entries]
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="catalog unreadable") from None
        computed = catalog_hash(entries)
        if computed != pending["hash"] or data.get("catalog_hash") != computed:
            raise HTTPException(status_code=400, detail="catalog_hash mismatch")
        folders = Counter(e.get("folder", "").split("/")[0] for e in entries)
        STATE.catalogs[pending["bridge_id"]] = {
            "hash": computed, "track_ids": ids, "gz_bytes": len(body), "raw_bytes": len(raw),
            "top_folders": len(folders), "received_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
        STATE.event(f"catalog received: {len(ids)} tracks, gzip {len(body)} B, raw {len(raw)} B")
        return {"ok": True, "track_count": len(ids)}

    # ---------------------------------------------------------------- PUT /upload/{job_id}
    @app.put("/upload/{job_id}")
    async def put_upload(job_id: str, request: Request):
        job = STATE.jobs.get(job_id)
        if job is None or job.token is None or not bearer_ok(request.headers.get("authorization"), job.token):
            raise HTTPException(status_code=403, detail="no upload pending for this token")
        job.token = None  # one-shot: consumed before reading anything
        declared = (request.headers.get("x-clip-sha256") or "").lower()
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > MAX_CLIP_BYTES):
            job.finish("FAILED", "INVALID_UPLOAD")
            raise HTTPException(status_code=413, detail="too large")
        job.t_upload_start = time.perf_counter()
        body = bytearray()
        async for chunk in request.stream():
            body += chunk
            if len(body) > MAX_CLIP_BYTES:
                job.finish("FAILED", "INVALID_UPLOAD")
                raise HTTPException(status_code=413, detail="too large")
        job.t_upload_done = time.perf_counter()
        head = bytes(body[:12])
        magic_ok = head[4:8] == b"ftyp" or head[:4] == b"OggS"
        sha_ok = hmac.compare_digest(hashlib.sha256(body).hexdigest(), declared)
        if not magic_ok or not sha_ok or not body:
            job.finish("FAILED", "INVALID_UPLOAD")
            raise HTTPException(status_code=422, detail="invalid clip (magic bytes or sha256)")
        job.bytes = len(body)
        job.upload_ok = True  # the clip is dropped here: RAM only, never written to disk
        return {"ok": True, "bytes": len(body)}

    # ---------------------------------------------------------------- jobs
    async def one_job(run_id: str, track_id: str, frac: float, duration: float, crafted: bool) -> Job:
        conn = STATE.bridge
        job = Job(job_id="j_" + secrets.token_hex(8), run_id=run_id, track_id=track_id,
                  start_fraction=frac, duration=duration, crafted=crafted,
                  token=secrets.token_urlsafe(32))
        STATE.jobs[job.job_id] = job
        if conn is None:
            job.finish("FAILED", "BRIDGE_OFFLINE")
            return job
        job.t_sent = time.perf_counter()
        await send(conn, {
            "t": "PREPARE", "job_id": job.job_id, "track_id": track_id,
            "start_fraction": frac, "duration": duration,
            "upload_url": f"upload/{job.job_id}",  # relative to the server base URL
            "upload_token": job.token,
        })
        try:
            await asyncio.wait_for(job.done.wait(), timeout=JOB_TIMEOUT_S)
        except asyncio.TimeoutError:
            job.finish("FAILED", "TIMEOUT")
            try:
                await send(conn, {"t": "CANCEL", "job_id": job.job_id})
            except Exception:
                pass
        total = job.total_ms()
        log(f"job {job.job_id} {track_id if not crafted else '<crafted>'} {job.status} "
            f"{job.code or ''} total {('%.0f ms' % total) if total else '-'}")
        return job

    async def run_jobs(run_id: str, n: int, duration: float, crafted: bool, seed: int | None) -> None:
        run = STATE.runs[run_id]
        rng = random.Random(seed)
        async with STATE.run_lock:
            run["state"] = "RUNNING"
            conn = STATE.bridge
            catalog = STATE.catalogs.get(str(conn.hello.get("bridge_id"))) if conn else None
            ids = catalog["track_ids"] if catalog else []
            plan = [(rng.choice(ids), False) for _ in range(n)] if ids else []
            if crafted:
                plan += [(c, True) for c in CRAFTED_IDS]
            for track_id, is_crafted in plan:
                job = await one_job(run_id, track_id, rng.random(), duration, is_crafted)
                run["job_ids"].append(job.job_id)
            run["state"] = "DONE"

    @app.post("/run")
    async def post_run(request: Request, n: int = 20, duration: float = 30.0, crafted: int = 0,
                       seed: int | None = None, wait: int = 0):
        require_admin(request)
        conn = STATE.bridge
        if conn is None:
            raise HTTPException(status_code=409, detail="no bridge connected")
        if str(conn.hello.get("bridge_id")) not in STATE.catalogs:
            raise HTTPException(status_code=409, detail="catalog not received yet")
        if STATE.run_lock.locked():
            raise HTTPException(status_code=409, detail="a run is already in progress")
        n = max(0, min(n, 500))
        run_id = "r_" + secrets.token_hex(4)
        STATE.runs[run_id] = {"run_id": run_id, "n": n, "duration": duration, "crafted": bool(crafted),
                              "state": "QUEUED", "job_ids": [], "started": time.strftime("%Y-%m-%d %H:%M:%S")}
        task = asyncio.create_task(run_jobs(run_id, n, duration, bool(crafted), seed))
        if wait:
            await task
            return JSONResponse(summary(run_id))
        return {"run_id": run_id, "state": "started", "stats": f"/stats?run={run_id}"}

    @app.post("/poke")
    async def post_poke(request: Request):
        """Closed-protocol test: none of these may make the Bridge read or send a file outside its
        root, and none may kill its job worker (checked by a final liveness PREPARE)."""
        require_admin(request)
        conn = STATE.bridge
        if conn is None:
            raise HTTPException(status_code=409, detail="no bridge connected")
        STATE.poke_replies.clear()
        valid_id = None
        catalog = STATE.catalogs.get(str(conn.hello.get("bridge_id")))
        if catalog and catalog["track_ids"]:
            # Prefer a track that already produced a clip (run `trigger` first), so the jobs
            # below reach clamp_request, FFmpeg and the upload step.
            done_ok = [j.track_id for j in STATE.jobs.values()
                       if j.status == "OK" and j.track_id in set(catalog["track_ids"])]
            valid_id = done_ok[-1] if done_ok else catalog["track_ids"][0]

        def prep(job_id: str, **over) -> dict:
            msg = {"t": "PREPARE", "job_id": job_id, "track_id": valid_id, "start_fraction": 0.5,
                   "duration": 10, "upload_url": f"upload/{job_id}", "upload_token": "x"}
            msg.update(over)
            return msg

        hostile = [
            ("unknown type", {"t": "READ_FILE", "path": "C:/Windows/win.ini"}),
            ("unknown type", {"t": "LIST", "folder": ""}),
            ("unknown type", {"t": "RESCAN", "root": "C:/"}),
            ("PREPARE + extra ffmpeg args", prep("poke-1", args=["-i", "C:/Windows/win.ini"])),
            ("PREPARE missing field", {"t": "PREPARE", "job_id": "poke-2", "track_id": valid_id}),
            ("PREPARE foreign upload_url", prep("poke-3", upload_url="https://attacker.invalid/upload")),
            ("PREPARE path as track_id", prep("poke-4", track_id="../../../../Windows/win.ini")),
            # Valid track_id so the bounds are really exercised (clamp_request, then FFmpeg).
            ("PREPARE huge duration/neg fraction", prep("poke-5", start_fraction=-5, duration=1e9)),
            ("PREPARE integer duration overflowing float", prep("poke-6", duration=10**400)),
            ("PREPARE non-ASCII upload_token", prep("poke-7", upload_token="tok\u00e9")),
            ("non-JSON text", "this is not json"),
            ("JSON array", [1, 2, 3]),
        ]
        for _label, payload in hostile:
            text = payload if isinstance(payload, str) else json.dumps(payload)
            await conn.ws.send_text(text)  # type: ignore[attr-defined]
        await conn.ws.send_bytes(b"\x00binary frame")  # type: ignore[attr-defined]
        # Liveness: a well-formed PREPARE after the hostile ones must still get an answer
        # (the upload is refused with 403 since no such job exists: INVALID_UPLOAD is the
        # expected reply; any terminal reply proves the job worker survived).
        await asyncio.sleep(0.5)
        await send(conn, prep("poke-alive"))
        terminal = ("JOB_DONE", "JOB_FAILED")
        deadline = time.perf_counter() + 20.0
        while time.perf_counter() < deadline:
            if any(r.get("job_id") == "poke-alive" and r.get("t") in terminal for r in STATE.poke_replies):
                break
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.3)  # late replies for the other pokes
        final = {r.get("job_id"): f"{r.get('t')} {r.get('code') or ''}".strip()
                 for r in STATE.poke_replies if r.get("t") in terminal}
        content_or_upload = "JOB_FAILED INVALID_UPLOAD (or a content code: TOO_SHORT/DECODE_ERROR)"
        expected = {"poke-1": "ignored (no reply)", "poke-2": "ignored (no reply)",
                    "poke-3": "JOB_FAILED INVALID_REQUEST", "poke-4": "JOB_FAILED NOT_FOUND",
                    "poke-5": content_or_upload, "poke-6": content_or_upload,
                    "poke-7": "ignored (no reply)", "poke-alive": content_or_upload}
        return {
            "sent": [label for label, _ in hostile] + ["binary frame", "liveness PREPARE"],
            "valid_track_id": valid_id,
            "expected": expected,
            "final_replies": final,
            "replies": STATE.poke_replies,
            "worker_alive": "poke-alive" in final,
            "bridge_still_connected": STATE.bridge is conn,
        }

    # ---------------------------------------------------------------- stats
    def summary(run_id: str | None) -> dict:
        jobs = [j for j in STATE.jobs.values() if run_id is None or j.run_id == run_id]
        normal = [j for j in jobs if not j.crafted]
        crafted = [j for j in jobs if j.crafted]
        ok = [j for j in normal if j.status == "OK"]
        totals = [j.total_ms() for j in ok if j.total_ms() is not None]
        up = [(j.t_upload_done - j.t_upload_start) * 1000 for j in ok
              if j.t_upload_start is not None and j.t_upload_done is not None]
        enc = [float(j.report.get("timings", {}).get("encode_ms", 0)) for j in ok if j.report.get("timings")]
        fails = Counter(j.code for j in normal if j.status == "FAILED")
        content = {c: n for c, n in fails.items() if c in CONTENT_CODES}
        infra = {str(c): n for c, n in fails.items() if c not in CONTENT_CODES}
        n_infra = sum(infra.values())
        pending = sum(1 for j in normal if j.status == "PENDING")
        # G2 sample: successful jobs (measured time) + infrastructure failures (infinite time).
        g2_values = totals + [math.inf] * n_infra
        g2_p95 = percentile(g2_values, 95)
        counts = (f"OK {len(ok)}/{len(normal)}"
                  + (f", content failures {content}" if content else "")
                  + (f", infra failures {infra}" if infra else "")
                  + (f", pending {pending}" if pending else ""))
        if not g2_values:
            verdict = "NO_DATA"
        elif g2_p95 is not None and g2_p95 >= G2_P95_MS:
            verdict = "FAIL"
        elif n_infra:
            verdict = f"INCONCLUSIVE ({n_infra} infra failure(s): rerun after fixing the cause)"
        elif len(g2_values) < G2_MIN_SAMPLE:
            verdict = f"PASS_SMALL_SAMPLE (n={len(g2_values)} < {G2_MIN_SAMPLE})"
        else:
            verdict = "PASS"
        conn = STATE.bridge
        rtts = conn.rtts_ms if conn else []
        catalog = STATE.catalogs.get(str(conn.hello.get("bridge_id"))) if conn else None
        return {
            "run": STATE.runs.get(run_id) if run_id else None,
            "bridge": None if conn is None else {
                **conn.hello, "user_agent": conn.user_agent,
                "connected_for_s": round(time.time() - conn.connected_at, 1),
                "app_rtt_ms_p50": _r(percentile(rtts, 50)), "app_rtt_ms_max": _r(max(rtts) if rtts else None),
                "unknown_messages": conn.unknown_messages,
            },
            "catalog": None if catalog is None else {k: v for k, v in catalog.items() if k != "track_ids"}
                       | {"track_count": len(catalog["track_ids"])},
            "connections": STATE.connections, "rejected_handshakes": STATE.rejected,
            "jobs_total": len(normal), "jobs_ok": len(ok),
            "failures": dict(fails), "content_failures": content, "infra_failures": infra,
            "total_ms": {"p50": _r(percentile(totals, 50)), "p95": _r(percentile(totals, 95)),
                         "max": _r(max(totals) if totals else None)},
            # JSON has no infinity: "inf" when infra failures push the p95 out.
            "G2_p95_ms": None if g2_p95 is None else ("inf" if math.isinf(g2_p95) else _r(g2_p95)),
            "G2_sample": len(g2_values), "G2_counts": counts,
            "server_upload_ms": {"p50": _r(percentile(up, 50)), "p95": _r(percentile(up, 95))},
            "bridge_encode_ms": {"p50": _r(percentile(enc, 50)), "p95": _r(percentile(enc, 95))},
            "G2_prepare_upload_p95_lt_5s": verdict,
            "crafted": {
                "n": len(crafted),
                "all_refused_NOT_FOUND": all(j.code == "NOT_FOUND" for j in crafted) if crafted else None,
                "codes": dict(Counter(j.code for j in crafted)),
            },
            "jobs": [j.public() for j in jobs],
            "events": STATE.events[-15:],
        }

    @app.get("/stats")
    async def get_stats(request: Request, run: str | None = None, format: str = "json"):
        require_admin(request)
        data = summary(run)
        if format == "text":
            return PlainTextResponse(render_text(data))
        return JSONResponse(data)

    return app


def render_text(s: dict) -> str:
    out = []
    b = s.get("bridge")
    out.append("=== relay stats (spike S1) ===")
    if b:
        out.append(f"bridge   : {b.get('name')!r} ua={b.get('user_agent')!r} tracks={b.get('track_count')} "
                   f"connected {b.get('connected_for_s')} s, app RTT p50 {b.get('app_rtt_ms_p50')} ms "
                   f"max {b.get('app_rtt_ms_max')} ms, unknown msgs {b.get('unknown_messages')}")
    else:
        out.append("bridge   : not connected")
    if s.get("catalog"):
        c = s["catalog"]
        out.append(f"catalog  : {c['track_count']} tracks, gzip {c['gz_bytes']} B, raw {c['raw_bytes']} B, {c['hash'][:23]}…")
    out.append(f"sessions : {s['connections']} accepted, {s['rejected_handshakes']} rejected")
    if s.get("run"):
        r = s["run"]
        out.append(f"run      : {r['run_id']} n={r['n']} duration={r['duration']} crafted={r['crafted']} state={r['state']}")
    out.append(f"{'job_id':<20} {'track_id':<20} {'status':<7} {'code':<14} {'total':>7} {'probe':>6} "
               f"{'encode':>7} {'upload':>7} {'bytes':>8} {'start':>8} {'clip':>6}")
    for j in s["jobs"]:
        t = j.get("bridge_timings") or {}
        tid = "<crafted>" if j["crafted"] else j["track_id"]
        out.append(f"{j['job_id']:<20} {tid:<20} {j['status']:<7} {str(j['code'] or ''):<14} "
                   f"{_f(j['total_ms']):>7} {_f(t.get('probe_ms')):>6} {_f(t.get('encode_ms')):>7} "
                   f"{_f(t.get('upload_ms')):>7} {j['bytes']:>8} {str(j['actual_start'] or '-'):>8} "
                   f"{str(j['clip_duration'] or '-'):>6}")
    tm = s["total_ms"]
    out.append(f"OK {s['jobs_ok']}/{s['jobs_total']}  failures {s['failures'] or '{}'}")
    out.append(f"PREPARE sent -> upload complete (OK jobs only): p50 {tm['p50']} ms, p95 {tm['p95']} ms, "
               f"max {tm['max']} ms")
    out.append(f"server-side upload: p50 {s['server_upload_ms']['p50']} ms, p95 {s['server_upload_ms']['p95']} ms; "
               f"bridge encode p50 {s['bridge_encode_ms']['p50']} ms, p95 {s['bridge_encode_ms']['p95']} ms")
    out.append(f"G2 p95 (OK + infra failures counted as infinite, n={s['G2_sample']}): {s['G2_p95_ms']} ms")
    out.append(f"G2 (p95 < 5 s): {s['G2_prepare_upload_p95_lt_5s']}  [{s['G2_counts']}]")
    r = s.get("run")
    if r and r.get("duration", 0) > BRIDGE_CLIP_MAX_S:
        out.append(f"note: --duration {r['duration']:g} requested, but the Bridge clamps clips to "
                   f"{BRIDGE_CLIP_MAX_S:g} s (see the 'clip' column)")
    if s["crafted"]["n"]:
        out.append(f"crafted track_ids: {s['crafted']['n']} sent, all refused NOT_FOUND: "
                   f"{s['crafted']['all_refused_NOT_FOUND']} {s['crafted']['codes']}")
    return "\n".join(out) + "\n"


def _f(v) -> str:
    return "-" if v is None else f"{float(v):.0f}"


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def cmd_serve(args) -> int:
    import uvicorn

    STATE.secret = load_secret()
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        log(f"listening on {args.host}: put Caddy (TLS) in front, never expose plain HTTP")
    uvicorn.run(build_app(), host=args.host, port=args.port, log_level="warning",
                ws_max_size=MAX_WS_MESSAGE, proxy_headers=False)
    return 0


def _client(args):
    import httpx

    secret = load_secret()
    return httpx.Client(base_url=args.url.rstrip("/"), timeout=httpx.Timeout(900.0, connect=10.0),
                        headers={"Authorization": f"Bearer {secret}"})


def cmd_trigger(args) -> int:
    with _client(args) as c:
        params = {"n": args.n, "duration": args.duration, "crafted": int(args.crafted), "wait": 1}
        if args.seed is not None:
            params["seed"] = args.seed
        r = c.post("/run", params=params)
        if r.status_code != 200:
            print(f"error {r.status_code}: {r.text}")
            return 1
        run_id = r.json()["run"]["run_id"]
        text = c.get("/stats", params={"run": run_id, "format": "text"}).text
        print(text)
        if args.json_out:
            data = c.get("/stats", params={"run": run_id}).json()
            os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
            with open(args.json_out, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=1)
            print(f"saved: {os.path.abspath(args.json_out)}")
    return 0


def cmd_stats(args) -> int:
    with _client(args) as c:
        params = {"format": "text"}
        if args.run:
            params["run"] = args.run
        print(c.get("/stats", params=params).text)
    return 0


def cmd_poke(args) -> int:
    with _client(args) as c:
        print(json.dumps(c.post("/poke").json(), indent=1))
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="run the relay (default)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    t = sub.add_parser("trigger", help="POST /run?wait=1 then print /stats for that run")
    t.add_argument("--url", required=True, help="relay base URL, e.g. https://relay.example.org")
    t.add_argument("-n", type=int, default=20)
    t.add_argument("--duration", type=float, default=30.0)
    t.add_argument("--crafted", action="store_true", help="also send crafted track_ids (must be NOT_FOUND)")
    t.add_argument("--seed", type=int)
    t.add_argument("--json-out", help="save the run stats JSON (track_ids only)")
    st = sub.add_parser("stats", help="print /stats as text")
    st.add_argument("--url", required=True)
    st.add_argument("--run")
    p = sub.add_parser("poke", help="POST /poke: hostile messages to the Bridge")
    p.add_argument("--url", required=True)
    argv = sys.argv[1:]
    if not any(a in ("serve", "trigger", "stats", "poke", "-h", "--help") for a in argv):
        argv = ["serve", *argv]
    args = ap.parse_args(argv)
    if args.cmd == "serve":
        return cmd_serve(args)
    return {"trigger": cmd_trigger, "stats": cmd_stats, "poke": cmd_poke}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
