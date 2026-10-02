#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["fastapi>=0.110", "uvicorn[standard]>=0.29", "numpy>=1.26"]
# ///
"""Spike S0 (audio sync and formats) - throwaway test server. Never merged into main.

Run:  uv run spikes/audio-sync/server.py --host 0.0.0.0 --port 8077 [--ffmpeg PATH]

At startup, generates synthetic clips into ``_generated/`` (test signal in 4 formats, one
calibration clip per voice), then serves:

    GET  /                 player test page (static/index.html)
    GET  /admin            admin page (?token=... if --admin-token is set)
    GET  /api/manifest     clip list, voices, probe results
    GET  /clips/{name}     generated clips only
    WS   /ws?cid=...       PING{c} -> PONG{c,s}; server pushes WELCOME, PLAY, STOP, SYNC
    POST /report           client reports (formats, playback, status)
    GET  /api/admin/state  live state for the admin page
    POST /api/admin/play   {kind: "calibration"|"clip", clip?, lead_ms, clip_offset?}
    POST /api/admin/stop   stop everything
    POST /api/admin/sync   ask every client for a sync burst
    GET  /results.json     everything collected (also saved under _results/)

Server time is a monotonic clock in milliseconds (spec section 9.2). On Python < 3.13 under
Windows, time.monotonic() has a 15.6 ms resolution, so the server falls back to
time.perf_counter_ns() (QueryPerformanceCounter, also monotonic) and says so at startup.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "tools"))
import calibration_clip as cc

GENERATED = HERE / "_generated"
RESULTS_DIR = HERE / "_results"
STATIC = HERE / "static"
SAMPLE_RATE = 48000
TEST_DURATION_S = 10.0
MARKER_FREQ_HZ = 2000.0
MARKER_ONSET_S = 0.5  # test clips: isolated marker burst, used to measure decoder offsets
MAX_REPORT_BYTES = 256 * 1024
STALE_S = 15.0  # clients ping every 5 s: a socket silent this long is considered dead


# --------------------------------------------------------------------------------------------
# Server clock
# --------------------------------------------------------------------------------------------


def _pick_clock() -> tuple[Any, str]:
    if time.get_clock_info("monotonic").resolution <= 1e-3:
        return time.monotonic_ns, "monotonic"
    return time.perf_counter_ns, "perf_counter (monotonic resolution too coarse)"


_CLOCK_NS, CLOCK_NAME = _pick_clock()


def server_now_ms() -> float:
    return _CLOCK_NS() / 1e6


# --------------------------------------------------------------------------------------------
# Clip generation
# --------------------------------------------------------------------------------------------

# name -> (ffmpeg codec args, MIME type, label)
TEST_FORMATS: dict[str, tuple[list[str], str, str]] = {
    "test_aac.m4a": (
        ["-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"],
        "audio/mp4",
        "AAC-LC 128k / MP4 (.m4a)",
    ),
    "test_opus.webm": (["-c:a", "libopus", "-b:a", "96k"], "audio/webm", "Opus 96k / WebM"),
    "test_opus.ogg": (["-c:a", "libopus", "-b:a", "96k"], "audio/ogg", "Opus 96k / Ogg"),
    "test_mp3.mp3": (["-c:a", "libmp3lame", "-b:a", "128k"], "audio/mpeg", "MP3 128k (reference)"),
}


def make_test_signal() -> np.ndarray:
    """10 s mono test signal: a marker burst at 0.5 s, then 8 synthetic notes from 1.0 s."""
    fs = SAMPLE_RATE
    out = np.zeros(round(TEST_DURATION_S * fs))
    marker = 0.8 * cc.hann_burst(MARKER_FREQ_HZ, fs, round(0.010 * fs))
    start = round(MARKER_ONSET_S * fs)
    out[start : start + len(marker)] += marker
    notes = [261.63, 329.63, 392.00, 523.25, 392.00, 329.63, 293.66, 261.63]
    t = np.arange(fs) / fs
    envelope = np.minimum(t / 0.02, 1.0) * np.exp(-3.0 * t)
    for i, f0 in enumerate(notes):
        tone = sum(a * np.sin(2 * np.pi * h * f0 * t) for h, a in ((1, 1.0), (2, 0.4), (3, 0.2)))
        s = round((1.0 + i) * fs)
        out[s : s + fs] += 0.25 * envelope * tone
    return out


def ffmpeg_template(
    ffmpeg: str, src: Path, dst: Path, codec_args: list[str], fade: bool
) -> list[str]:
    """Spec section 10 template (arguments as a list, never through a shell)."""
    cmd = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-threads",
        "1",
        "-protocol_whitelist",
        "file",
        "-ss",
        "0",
        "-i",
        "file:" + str(src.resolve()),
        "-t",
        f"{TEST_DURATION_S if fade else cc.DEFAULT_DURATION_S:g}",
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-ac",
        "2",
        "-ar",
        "48000",
    ]
    if fade:
        out_start = TEST_DURATION_S - 1.5
        cmd += ["-af", f"afade=t=in:st=0:d=0.3,afade=t=out:st={out_start:g}:d=1.5"]
    return cmd + codec_args + ["-y", str(dst)]


def probe(ffprobe: str | None, path: Path) -> dict[str, Any]:
    if not ffprobe:
        return {"error": "ffprobe not found"}
    cmd = [ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    try:
        data = json.loads(subprocess.run(cmd, capture_output=True, check=True, timeout=30).stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {"error": str(exc)}
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    return {
        "format_name": fmt.get("format_name"),
        "duration_s": float(fmt.get("duration", "nan")),
        "bit_rate": int(fmt.get("bit_rate", 0) or 0),
        "codec": audio.get("codec_name"),
        "profile": audio.get("profile"),
        "sample_rate": int(audio.get("sample_rate", 0) or 0),
        "channels": audio.get("channels"),
        "stream_count": len(streams),
        "format_tags": fmt.get("tags", {}),
        "stream_tags": audio.get("tags", {}),
    }


def burst_centroid_s(
    x: np.ndarray, fs: int, lo_s: float, hi_s: float, half_ms: float = 15.0
) -> float | None:
    """Energy centroid (s) of the strongest burst in [lo_s, hi_s]. Mirrors static/measure.js."""
    lo, hi = max(0, round(lo_s * fs)), min(len(x), round(hi_s * fs))
    if hi <= lo:
        return None
    peak = lo + int(np.argmax(np.abs(x[lo:hi])))
    half = round(half_ms * 1e-3 * fs)
    a, b = max(0, peak - half), min(len(x), peak + half)
    energy = x[a:b] ** 2
    if energy.sum() <= 0:
        return None
    return float((np.arange(a, b) * energy).sum() / energy.sum()) / fs


def ffmpeg_marker_offset_ms(ffmpeg: str, path: Path, expected_center_s: float) -> float | None:
    """Decode with ffmpeg (which honours edit lists / pre-skip) and measure the marker shift."""
    cmd = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-f",
        "f32le",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-",
    ]
    try:
        raw = subprocess.run(cmd, capture_output=True, check=True, timeout=60).stdout
    except subprocess.SubprocessError:
        return None
    x = np.frombuffer(raw, dtype="<f4").astype(np.float64)
    center = burst_centroid_s(x, SAMPLE_RATE, expected_center_s - 0.2, expected_center_s + 0.2)
    return None if center is None else (center - expected_center_s) * 1e3


def generate_clips(ffmpeg: str, ffprobe: str | None) -> dict[str, Any]:
    src_dir, clip_dir = GENERATED / "src", GENERATED / "clips"
    for d in (src_dir, clip_dir):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    clips: list[dict[str, Any]] = []

    test_wav = src_dir / "test_signal.wav"
    cc.write_wav(test_wav, make_test_signal(), SAMPLE_RATE)
    marker_center = MARKER_ONSET_S + 0.005
    for name, (codec_args, mime, label) in TEST_FORMATS.items():
        dst = clip_dir / name
        t0 = time.perf_counter()
        subprocess.run(
            ffmpeg_template(ffmpeg, test_wav, dst, codec_args, fade=True), check=True, timeout=60
        )
        clips.append(
            {
                "name": name,
                "kind": "test",
                "label": label,
                "mime": mime,
                "bytes": dst.stat().st_size,
                "encode_s": round(time.perf_counter() - t0, 3),
                "marker_center_s": marker_center,
                "marker_freq_hz": MARKER_FREQ_HZ,
                "expected_duration_s": TEST_DURATION_S,
                "probe": probe(ffprobe, dst),
                "ffmpeg_marker_offset_ms": ffmpeg_marker_offset_ms(ffmpeg, dst, marker_center),
            }
        )

    voices = []
    for k, freq in enumerate(cc.DEFAULT_FREQS_HZ):
        spec = cc.CalibrationSpec(freq_hz=freq, sample_rate=SAMPLE_RATE)
        wav = src_dir / f"calib_v{k}.wav"
        cc.write_wav(wav, cc.render(spec), SAMPLE_RATE)
        name = f"calib_v{k}.m4a"
        dst = clip_dir / name
        codec = TEST_FORMATS["test_aac.m4a"][0]
        subprocess.run(ffmpeg_template(ffmpeg, wav, dst, codec, fade=False), check=True, timeout=60)
        first_center = spec.lead_in_s + spec.burst_ms / 2000
        clips.append(
            {
                "name": name,
                "kind": "calibration",
                "voice": k,
                "freq_hz": freq,
                "label": f"Calibration voix {k} ({freq:g} Hz)",
                "mime": "audio/mp4",
                "bytes": dst.stat().st_size,
                "marker_center_s": first_center,
                "marker_freq_hz": freq,
                "expected_duration_s": spec.duration_s,
                "bursts": len(spec.onset_samples()),
                "probe": probe(ffprobe, dst),
                "ffmpeg_marker_offset_ms": ffmpeg_marker_offset_ms(ffmpeg, dst, first_center),
            }
        )
        voices.append({"voice": k, "freq_hz": freq, "clip": name})

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ffmpeg": ffmpeg,
        "calibration": {
            "period_s": cc.DEFAULT_PERIOD_S,
            "burst_ms": cc.DEFAULT_BURST_MS,
            "lead_in_s": cc.DEFAULT_LEAD_IN_S,
            "duration_s": cc.DEFAULT_DURATION_S,
        },
        "voices": voices,
        "clips": clips,
    }


# --------------------------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------------------------


def ua_family(ua: str) -> str:
    if re.search(r"iPhone|iPad|iPod", ua):
        engine = "CriOS" if "CriOS" in ua else "FxiOS" if "FxiOS" in ua else "Safari"
        m = re.search(r"OS (\d+)[_.](\d+)", ua)
        return f"iOS {m.group(1)}.{m.group(2)} {engine}" if m else f"iOS {engine}"
    if "Android" in ua:
        m = re.search(r"Android (\d+)", ua)
        browser = (
            "Firefox" if "Firefox" in ua else "Samsung" if "SamsungBrowser" in ua else "Chrome"
        )
        return f"Android {m.group(1) if m else '?'} {browser}"
    if "Firefox/" in ua:
        return "Firefox desktop"
    if "Edg/" in ua:
        return "Edge desktop"
    if "Chrome/" in ua:
        return "Chrome desktop"
    if "Safari/" in ua and "Macintosh" in ua:
        return "Safari macOS (ou iPad en mode bureau)"
    return "autre"


@dataclass
class Client:
    id: str
    voice: int
    tab: str = ""  # random id of the page instance (one per page load)
    user_agent: str = ""
    connected: bool = False
    connected_at: float = 0.0
    last_seen: float = 0.0
    ws: WebSocket | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    status: dict[str, Any] = field(default_factory=dict)
    hello: dict[str, Any] = field(default_factory=dict)
    reports: list[dict[str, Any]] = field(default_factory=list)

    async def send(self, msg: dict[str, Any]) -> None:
        if self.ws is None:
            return
        # a dying socket must not break a broadcast
        async with self.lock:
            with contextlib.suppress(Exception):
                await self.ws.send_text(json.dumps(msg))

    def summary(self) -> dict[str, Any]:
        last = {}
        for r in self.reports:
            last[r.get("kind", "?")] = r
        return {
            "id": self.id,
            "voice": self.voice,
            "freq_hz": cc.DEFAULT_FREQS_HZ[self.voice % len(cc.DEFAULT_FREQS_HZ)],
            "ua": self.user_agent,
            "ua_family": ua_family(self.user_agent),
            "connected": self.connected,
            "connected_at": self.connected_at,
            "last_seen": self.last_seen,
            "status": self.status,
            "hello": self.hello,
            "last_reports": last,
            "report_count": len(self.reports),
        }


class State:
    def __init__(
        self, manifest: dict[str, Any], admin_token: str | None, stale_s: float = STALE_S
    ) -> None:
        self.manifest = manifest
        self.admin_token = admin_token
        self.stale_s = stale_s
        self.clients: dict[str, Client] = {}
        self.plays: list[dict[str, Any]] = []
        self.current_play: dict[str, Any] | None = None  # re-sent to (re)connecting clients
        self.started_at = time.strftime("%Y%m%d-%H%M%S")
        self.results_path = RESULTS_DIR / f"results-{self.started_at}.json"

    def assign_voice(self, preferred: int | None) -> int:
        used = {c.voice for c in self.clients.values() if c.connected}
        n = len(cc.DEFAULT_FREQS_HZ)
        if preferred is not None and preferred not in used:
            return preferred
        for v in range(n):
            if v not in used:
                return v
        return len(used) % n  # more than 6 devices: voices are shared

    def results(self) -> dict[str, Any]:
        return {
            "server_clock": CLOCK_NAME,
            "started_at": self.started_at,
            "manifest": self.manifest,
            "clients": [c.summary() | {"reports": c.reports} for c in self.clients.values()],
            "plays": self.plays,
        }

    def save(self) -> None:
        RESULTS_DIR.mkdir(exist_ok=True)
        tmp = self.results_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.results(), indent=1), encoding="utf-8")
        tmp.replace(self.results_path)


# --------------------------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------------------------


async def close_quietly(ws: WebSocket, code: int = 4000) -> None:
    with contextlib.suppress(Exception):
        await ws.close(code=code)


def drop_socket(client: Client) -> None:
    """Forget the client's current socket (dead, or replaced) and close it in the background."""
    old = client.ws
    client.connected, client.ws = False, None
    if old is not None:
        asyncio.get_running_loop().create_task(close_quietly(old))


async def reap_stale(state: State) -> None:
    """Mark as disconnected the clients whose socket stayed silent for ``stale_s``: a phone
    that vanished (background, network switch) must not keep its voice nor receive PLAYs."""
    while True:
        await asyncio.sleep(min(5.0, state.stale_s / 2))
        now = time.time()
        for c in list(state.clients.values()):
            if c.connected and now - c.last_seen > state.stale_s:
                print(f"event=ws_stale client={c.id} silent_s={now - c.last_seen:.1f}")
                drop_socket(c)


def create_app(state: State) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
        task = asyncio.create_task(reap_stale(state))
        yield
        task.cancel()

    app = FastAPI(
        title="OpenBlindySir spike S0", docs_url=None, redoc_url=None, lifespan=lifespan
    )
    clip_index = {c["name"]: c for c in state.manifest["clips"]}

    @app.middleware("http")
    async def no_store(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, private"
        return response

    def check_admin(request: Request) -> None:
        if state.admin_token and request.query_params.get("token") != state.admin_token:
            raise HTTPException(status_code=403, detail="admin token required (?token=...)")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/admin")
    async def admin(request: Request) -> FileResponse:
        check_admin(request)
        return FileResponse(STATIC / "admin.html")

    @app.get("/api/manifest")
    async def manifest() -> dict[str, Any]:
        return state.manifest | {"server_clock": CLOCK_NAME}

    @app.get("/clips/{name}")
    async def clip(name: str) -> FileResponse:
        info = clip_index.get(name)
        if info is None:
            raise HTTPException(status_code=404)
        return FileResponse(GENERATED / "clips" / name, media_type=info["mime"])

    @app.post("/report")
    async def report(request: Request) -> dict[str, Any]:
        body = await request.body()
        if len(body) > MAX_REPORT_BYTES:
            raise HTTPException(status_code=413)
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid JSON") from exc
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="object expected")
        client = state.clients.get(str(data.get("client_id")))
        if client is None:
            raise HTTPException(status_code=404, detail="unknown client_id")
        data["received_at_server_ms"] = server_now_ms()
        data["received_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        client.reports.append(data)
        state.save()
        print(f"event=report client={client.id} voice={client.voice} kind={data.get('kind')}")
        return {"ok": True}

    @app.get("/api/admin/state")
    async def admin_state(request: Request) -> dict[str, Any]:
        check_admin(request)
        return {
            "server_now": server_now_ms(),
            "server_clock": CLOCK_NAME,
            "stale_s": state.stale_s,
            "clients": [c.summary() for c in state.clients.values()],
            "plays": state.plays[-20:],
            "clips": [
                {"name": c["name"], "label": c["label"], "kind": c["kind"]}
                for c in state.manifest["clips"]
            ],
        }

    @app.post("/api/admin/play")
    async def admin_play(request: Request) -> dict[str, Any]:
        check_admin(request)
        body = await request.json()
        kind = body.get("kind", "calibration")
        lead_ms = float(body.get("lead_ms", 3000))
        clip_offset = float(body.get("clip_offset", 0.0))
        clip_name = body.get("clip")
        if kind == "clip" and clip_name not in clip_index:
            raise HTTPException(status_code=400, detail="unknown clip")
        play_id = uuid.uuid4().hex[:8]
        start_at = server_now_ms() + lead_ms
        targets = []
        for c in state.clients.values():
            if not c.connected:
                continue
            name = f"calib_v{c.voice}.m4a" if kind == "calibration" else clip_name
            targets.append({"client": c.id, "voice": c.voice, "clip": name})
            await c.send(
                {
                    "t": "PLAY",
                    "play_id": play_id,
                    "kind": kind,
                    "clip": name,
                    "start_at": start_at,
                    "clip_offset": clip_offset,
                }
            )
        play = {
            "play_id": play_id,
            "kind": kind,
            "start_at": start_at,
            "lead_ms": lead_ms,
            "clip_offset": clip_offset,
            "targets": targets,
            "issued_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        state.plays.append(play)
        duration_s = (
            cc.DEFAULT_DURATION_S
            if kind == "calibration"
            else clip_index[clip_name]["expected_duration_s"]
        )
        state.current_play = {
            "play_id": play_id,
            "kind": kind,
            "clip": clip_name,
            "start_at": start_at,
            "clip_offset": clip_offset,
            "end_at": start_at + (duration_s - clip_offset) * 1000,
        }
        state.save()
        print(
            f"event=play play_id={play_id} kind={kind} lead_ms={lead_ms:g} clients={len(targets)}"
        )
        return play

    @app.post("/api/admin/stop")
    async def admin_stop(request: Request) -> dict[str, Any]:
        check_admin(request)
        play_id = state.plays[-1]["play_id"] if state.plays else None
        state.current_play = None
        for c in state.clients.values():
            if c.connected:
                await c.send({"t": "STOP", "play_id": play_id})
        return {"ok": True, "play_id": play_id}

    @app.post("/api/admin/sync")
    async def admin_sync(request: Request) -> dict[str, Any]:
        check_admin(request)
        for c in state.clients.values():
            if c.connected:
                await c.send({"t": "SYNC"})
        return {"ok": True}

    @app.get("/results.json")
    async def results(request: Request) -> JSONResponse:
        check_admin(request)
        return JSONResponse(state.results())

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        cid = ws.query_params.get("cid") or ""
        tab = (ws.query_params.get("tab") or "")[:40]
        previous = state.clients.get(cid)
        if previous is not None and previous.connected:
            same_page = bool(tab) and tab == previous.tab
            silent_s = time.time() - previous.last_seen
            if same_page or silent_s > state.stale_s:
                # The same page reconnecting before its old socket was noticed dead (iOS or
                # Android back from background, Wi-Fi <-> 4G): take over, keep the voice.
                print(
                    f"event=ws_takeover client={cid} same_page={same_page} "
                    f"silent_s={silent_s:.1f}"
                )
                drop_socket(previous)
            else:
                cid = ""  # another live page with the same id (duplicated tab): new identity
                previous = None
        if not re.fullmatch(r"[A-Za-z0-9_-]{4,40}", cid):
            cid = uuid.uuid4().hex[:10]
        voice = state.assign_voice(previous.voice if previous else None)
        client = previous or Client(id=cid, voice=voice)
        client.voice = voice
        client.tab = tab
        client.ws, client.connected = ws, True
        client.connected_at = client.last_seen = time.time()
        client.user_agent = ws.headers.get("user-agent", "")
        state.clients[cid] = client
        print(
            f"event=ws_open client={cid} voice={voice} ua_family={ua_family(client.user_agent)!r}"
        )
        await client.send(
            {
                "t": "WELCOME",
                "client_id": cid,
                "voice": voice,
                "freq_hz": cc.DEFAULT_FREQS_HZ[voice],
                "calib_clip": f"calib_v{voice}.m4a",
                "server_now": server_now_ms(),
                "server_clock": CLOCK_NAME,
            }
        )
        play = state.current_play
        if play is not None and server_now_ms() < play["end_at"]:
            # late arrival / reconnection during playback (spec 9.6): same PLAY, the client
            # applies the "T already past" rule
            name = f"calib_v{voice}.m4a" if play["kind"] == "calibration" else play["clip"]
            await client.send(
                {
                    "t": "PLAY",
                    "play_id": play["play_id"],
                    "kind": play["kind"],
                    "clip": name,
                    "start_at": play["start_at"],
                    "clip_offset": play["clip_offset"],
                    "rejoin": True,
                }
            )
        try:
            while True:
                text = await ws.receive_text()
                received = server_now_ms()  # read before anything else (spec 9.2)
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(msg, dict):
                    continue
                if client.ws is not ws:
                    break  # replaced by a newer socket of the same client (takeover)
                client.last_seen = time.time()
                kind = msg.get("t")
                if kind == "PING":
                    await client.send({"t": "PONG", "c": msg.get("c"), "s": received})
                elif kind == "HELLO":
                    client.hello = msg
                elif kind == "AUDIO_STATUS":
                    client.status = msg | {"at": time.time()}
        except (WebSocketDisconnect, RuntimeError):
            pass  # RuntimeError: socket closed by drop_socket() while receiving
        finally:
            if client.ws is ws:
                client.connected, client.ws = False, None
            print(f"event=ws_close client={cid}")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def find_exe(explicit: str | None, env_var: str, name: str) -> str | None:
    for candidate in (explicit, os.environ.get(env_var)):
        if candidate:
            return candidate
    return shutil.which(name)


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenBlindySir spike S0 test server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8077)
    parser.add_argument("--ffmpeg", default=None, help="ffmpeg binary (else $FFMPEG, else PATH)")
    parser.add_argument(
        "--ffprobe",
        default=None,
        help="ffprobe binary (else $FFPROBE, else next to ffmpeg, else PATH)",
    )
    parser.add_argument(
        "--admin-token",
        default=os.environ.get("SPIKE_ADMIN_TOKEN"),
        help="protect /admin, /api/admin/* and /results.json (?token=...)",
    )
    parser.add_argument(
        "--stale-s",
        type=float,
        default=STALE_S,
        help="a client socket silent this long is considered dead (clients ping every 5 s)",
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]  # logs when redirected

    ffmpeg = find_exe(args.ffmpeg, "FFMPEG", "ffmpeg")
    if ffmpeg is None:
        print("error: ffmpeg not found (use --ffmpeg PATH or set FFMPEG)", file=sys.stderr)
        return 2
    ffprobe = find_exe(args.ffprobe, "FFPROBE", "ffprobe")
    if ffprobe is None:
        sibling = Path(ffmpeg).with_name(Path(ffmpeg).name.replace("ffmpeg", "ffprobe"))
        ffprobe = str(sibling) if sibling.exists() else None

    print(f"server clock: {CLOCK_NAME}")
    print("generating clips...")
    t0 = time.perf_counter()
    manifest = generate_clips(ffmpeg, ffprobe)
    for c in manifest["clips"]:
        p = c["probe"]
        print(
            f"  {c['name']:<16} {c['bytes']:>7} B  {p.get('codec')}/{p.get('sample_rate')}Hz/"
            f"{p.get('channels')}ch  {p.get('duration_s', 0):.3f} s  tags={p.get('format_tags')}"
            f"  ffmpeg marker offset {c['ffmpeg_marker_offset_ms'] or float('nan'):+.2f} ms"
        )
    print(f"done in {time.perf_counter() - t0:.1f} s")
    (GENERATED / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    state = State(manifest, args.admin_token, args.stale_s)
    app = create_app(state)
    suffix = f"?token={args.admin_token}" if args.admin_token else ""
    hosts = ["127.0.0.1"]
    if args.host == "0.0.0.0":
        with contextlib.suppress(OSError):
            hosts += [
                ip
                for ip in socket.gethostbyname_ex(socket.gethostname())[2]
                if not ip.startswith("127.")
            ]
    for h in hosts:
        print(f"player: http://{h}:{args.port}/   admin: http://{h}:{args.port}/admin{suffix}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
