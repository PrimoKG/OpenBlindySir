# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets>=14", "httpx>=0.27"]
# ///
"""Spike S1 Bridge client: outbound only (WSS + HTTPS), spec §11 / protocol §8.3.

Scans one root, connects to the relay, sends HELLO (catalog_hash + track_count), uploads the
gzip catalog when WELCOME asks for it, then serves PREPARE jobs:
    track_id lookup -> open-time sandbox check -> ffprobe -> start point -> exact FFmpeg
    template -> PUT clip (one-shot token + sha256) -> JOB_DONE / JOB_FAILED.

Accepted server messages: WELCOME, PREPARE, CANCEL, PING. Everything else is logged (type
only) and ignored. PREPARE must have exactly the documented fields.

Usage:
    set SPIKE_SECRET=...            (PowerShell: $env:SPIKE_SECRET = "...")
    uv run spikes/bridge/bridge_client.py --server https://relay.example.org --root D:/Music
         [--name Ayoub] [--ffmpeg PATH] [--ffprobe PATH] [--jobs 1] [--verbose-paths]
         [--exit-after SECONDS]

ws:// and http:// are refused except for localhost. TLS verification is always on (system
trust store), there is no option to disable it. The secret is read from the environment only
(never a CLI argument: it would show in the process list).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import ssl
import sys
import tempfile
import time
import uuid
from urllib.parse import urljoin, urlsplit

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge_common as bc  # noqa: E402

VERSION = "spike"
USER_AGENT = f"OpenBlindySir-Bridge/{VERSION}"
PROTOCOL = 1
HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE_ID_FILE = os.path.join(HERE, "_out", "bridge_id.txt")

ACCEPTED = frozenset({"WELCOME", "PREPARE", "CANCEL", "PING"})
PREPARE_FIELDS = frozenset({"t", "job_id", "track_id", "start_fraction", "duration", "upload_url",
                            "upload_token"})
JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# Bearer token: printable ASCII only (an HTTP header value; httpx raises UnicodeEncodeError
# on anything else, which must never reach the job worker).
UPLOAD_TOKEN_RE = re.compile(r"[\x21-\x7e]{1,256}")  # used with fullmatch ("$" accepts "\n")
MAX_WS_MESSAGE = 64 * 1024
MAX_CLIP_BYTES = 2 * 1024 * 1024
MAX_QUEUE = 4
INTERNAL = "INTERNAL"  # spike-only code (not in spec §7.3): unexpected error inside the Bridge
SILENCE_TIMEOUT_S = 45.0  # server PINGs every 15 s
BACKOFF_MIN_S, BACKOFF_MAX_S = 1.0, 30.0
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def ts() -> str:
    return time.strftime("%H:%M:%S")


def build_endpoints(server: str) -> tuple[str, str, ssl.SSLContext | None]:
    """Return (ws_url, http_base, ssl_context). Refuses clear text except to localhost."""
    u = urlsplit(server.strip())
    scheme = u.scheme.lower()
    host = (u.hostname or "").lower()
    if not host or u.username or u.password or u.query or u.fragment:
        raise SystemExit("--server must be a plain URL like https://relay.example.org")
    if scheme in ("https", "wss"):
        secure = True
    elif scheme in ("http", "ws"):
        if host not in LOCAL_HOSTS:
            raise SystemExit("refused: ws:// and http:// are only allowed to localhost; use https:// (TLS)")
        secure = False
    else:
        raise SystemExit("--server must start with https:// (or http:// for localhost)")
    netloc = u.netloc
    prefix = u.path.rstrip("/")
    if prefix.endswith("/bridge"):
        prefix = prefix[: -len("/bridge")]
    ws_url = f"{'wss' if secure else 'ws'}://{netloc}{prefix}/bridge"
    http_base = f"{'https' if secure else 'http'}://{netloc}{prefix}"
    ctx = None
    if secure:
        ctx = ssl.create_default_context()  # CERT_REQUIRED + check_hostname, system CAs
        assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    return ws_url, http_base, ctx


def resolve_upload_url(http_base: str, upload_url: str) -> str | None:
    """The upload must go back to the same origin and path prefix as the server."""
    target = urljoin(http_base + "/", upload_url)
    b, t = urlsplit(http_base), urlsplit(target)
    if (t.scheme, t.netloc.lower()) != (b.scheme, b.netloc.lower()):
        return None
    if not t.path.startswith(b.path + "/") or t.query or t.fragment or ".." in t.path:
        return None
    return target


def load_bridge_id() -> str:
    try:
        with open(BRIDGE_ID_FILE, encoding="ascii") as fh:
            value = fh.read().strip()
            uuid.UUID(value)
            return value
    except (OSError, ValueError):
        value = str(uuid.uuid4())
        os.makedirs(os.path.dirname(BRIDGE_ID_FILE), exist_ok=True)
        with open(BRIDGE_ID_FILE, "w", encoding="ascii") as fh:
            fh.write(value)
        return value


def purge_temp_dirs() -> int:
    """Spec §11: private temp dirs are purged at startup."""
    base = tempfile.gettempdir()
    n = 0
    for name in os.listdir(base):
        path = os.path.join(base, name)
        if name.startswith(bc.TEMP_PREFIX) and os.path.isdir(path) and not os.path.islink(path):
            try:
                bc.safe_rmtree(path)
                n += 1
            except OSError:
                pass
    return n


class Bridge:
    def __init__(self, args, secret: str) -> None:
        self.args = args
        self.secret = secret
        self.ws_url, self.http_base, self.ssl_ctx = build_endpoints(args.server)
        self.ffmpeg, self.ffprobe = bc.find_ffmpeg_pair(args.ffmpeg, args.ffprobe)
        self.ffmpeg_version, encoders = bc.ffmpeg_info(self.ffmpeg)
        self.formats = [f for f, enc in (("aac", "aac"), ("opus", "libopus")) if enc in encoders]
        if "aac" not in self.formats:
            raise SystemExit("this FFmpeg build has no 'aac' encoder")
        self.bridge_id = load_bridge_id()
        self.state = "SCANNING"
        self.clip_format = "aac"
        self.max_clip_s = bc.CLIP_MAX_S
        self.ok = 0
        self.failed = 0
        self.ignored = 0
        self.last = ""
        self.rtt_ms: float | None = None
        self.cancelled: set[str] = set()
        self.ws = None
        self.welcomed = False
        self.queue: asyncio.Queue | None = None
        self.last_rx = time.monotonic()
        self.http = httpx.AsyncClient(
            verify=self.ssl_ctx if self.ssl_ctx is not None else True,
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(bc.UPLOAD_TIMEOUT_S, connect=10.0),
            follow_redirects=False,
        )

    # ---------------------------------------------------------------- console
    def status(self, note: str = "") -> None:
        rtt = f"RTT {self.rtt_ms:.0f} ms" if self.rtt_ms is not None else "RTT -"
        line = (f"{ts()} {self.state:<10} {rtt:<12} | {len(self.tracks)} pistes | jobs {self.ok} OK · "
                f"{self.failed} échec{'s' if self.failed > 1 else ''}"
                + (f" · dernier {self.last}" if self.last else "")
                + (f" | ignorés {self.ignored}" if self.ignored else "")
                + (f" | {note}" if note else ""))
        print(line, flush=True)

    # ---------------------------------------------------------------- scan
    def scan(self) -> None:
        self.root_real, self.tracks, st = bc.scan_library(self.args.root)
        self.catalog_raw, self.catalog_gz, self.catalog_hash = bc.catalog_payload(self.tracks)
        print(f"OpenBlindySir Bridge {VERSION} — « {self.args.name} »  (bridge_id {self.bridge_id[:8]}…)")
        print(f"Serveur : {self.http_base}")
        print(f"Dossier : {self.root_real} — {len(self.tracks)} pistes (scan {st.elapsed_s:.2f} s; "
              f"ignorés: liens {st.symlinks_skipped}, junctions {st.junctions_skipped}, "
              f"cachés {st.dotfiles_skipped + st.hidden_attr_skipped + st.system_attr_skipped}, "
              f"hors liste {st.ext_skipped}, erreurs {st.errors})")
        print(f"Catalogue: {len(self.catalog_raw)} B brut, {len(self.catalog_gz)} B gzip, {self.catalog_hash[:23]}…")
        print(f"FFmpeg  : {self.ffmpeg_version.split(' Copyright')[0]} | formats {self.formats}")
        if self.args.verbose_paths:
            for t in sorted(self.tracks.values(), key=lambda t: t.relpath):
                print(f"  {t.track_id}  {t.relpath}")

    # ---------------------------------------------------------------- connection loop
    async def run_forever(self) -> None:
        backoff = BACKOFF_MIN_S
        while True:
            self.state = "CONNECTING"
            self.status()
            self.welcomed = False  # set by session(); survives the exception that ends it
            try:
                async with connect(
                    self.ws_url,
                    additional_headers={"Authorization": f"Bearer {self.secret}"},
                    user_agent_header=USER_AGENT,
                    ssl=self.ssl_ctx,
                    max_size=MAX_WS_MESSAGE,
                    ping_interval=15,
                    ping_timeout=20,
                    open_timeout=15,
                    close_timeout=5,
                ) as ws:
                    await self.session(ws)
            except InvalidStatus as exc:
                code = exc.response.status_code
                self.state = "REJECTED" if code in (401, 403) else "BACKOFF"
                self.status(f"handshake HTTP {code}" + (" (secret refusé ?)" if code in (401, 403) else ""))
                if code in (401, 403):
                    backoff = BACKOFF_MAX_S
            except ConnectionClosed as exc:
                self.state = "OFFLINE"
                rcvd = exc.rcvd
                self.status(f"connexion fermée ({rcvd.code if rcvd else 'sans code'}"
                            f"{' ' + rcvd.reason if rcvd and rcvd.reason else ''})")
            except (OSError, InvalidHandshake, asyncio.TimeoutError, ssl.SSLError) as exc:
                self.status(f"échec connexion: {exc.__class__.__name__}")
            if self.welcomed:
                backoff = BACKOFF_MIN_S
            delay = random.uniform(0.5, 1.0) * backoff  # jitter
            self.state = "BACKOFF"
            self.status(f"nouvel essai dans {delay:.1f} s")
            await asyncio.sleep(delay)
            backoff = min(BACKOFF_MAX_S, backoff * 2)

    async def send(self, msg: dict) -> None:
        if self.ws is not None:
            try:
                await self.ws.send(json.dumps(msg, separators=(",", ":")))
            except ConnectionClosed:
                pass

    async def session(self, ws) -> bool:  # returns normally only on a clean close
        self.ws = ws
        self.queue = asyncio.Queue()
        self.cancelled.clear()
        await ws.send(json.dumps({
            "t": "HELLO", "bridge_id": self.bridge_id, "name": self.args.name, "version": VERSION,
            "protocol": PROTOCOL, "catalog_hash": self.catalog_hash, "track_count": len(self.tracks),
            "formats": self.formats,
        }))
        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        try:
            welcome = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            welcome = {}
        if not isinstance(welcome, dict) or welcome.get("t") != "WELCOME":
            self.status("premier message différent de WELCOME: déconnexion")
            await ws.close()
            return False
        fmt = welcome.get("clip_format")
        self.clip_format = fmt if fmt in self.formats else "aac"
        limits = welcome.get("limits") if isinstance(welcome.get("limits"), dict) else {}
        try:  # the Bridge caps what the server asks
            self.max_clip_s = min(bc.CLIP_MAX_S, max(bc.CLIP_MIN_S, float(limits.get("max_clip_s", bc.CLIP_MAX_S))))
        except (TypeError, ValueError):
            self.max_clip_s = bc.CLIP_MAX_S
        if welcome.get("catalog_needed"):
            token = welcome.get("catalog_upload_token")
            if isinstance(token, str) and await self.upload_catalog(token):
                pass
            else:
                self.status("envoi du catalogue impossible: déconnexion")
                await ws.close()
                return False
        self.state = "ONLINE"
        self.welcomed = True
        self.rtt_ms = ws.latency * 1000 if ws.latency else None
        self.status(f"WELCOME format={self.clip_format} max_clip={self.max_clip_s:g}s "
                    f"catalogue {'envoyé' if welcome.get('catalog_needed') else 'déjà connu'}")
        self.last_rx = time.monotonic()
        workers = [asyncio.create_task(self.worker()) for _ in range(max(1, min(2, self.args.jobs)))]
        watchdog = asyncio.create_task(self.watchdog(ws))
        try:
            async for message in ws:
                self.last_rx = time.monotonic()
                self.rtt_ms = ws.latency * 1000 if ws.latency else self.rtt_ms
                await self.on_message(message)
        finally:
            for task in (*workers, watchdog):
                task.cancel()
            self.ws = None
        return True

    async def watchdog(self, ws) -> None:
        while True:
            await asyncio.sleep(5)
            if time.monotonic() - self.last_rx > SILENCE_TIMEOUT_S:
                self.status("aucun message du serveur depuis 45 s: reconnexion")
                await ws.close(code=4008, reason="heartbeat timeout")
                return

    async def upload_catalog(self, token: str) -> bool:
        t0 = time.perf_counter()
        try:
            r = await self.http.put(
                self.http_base + "/catalog", content=self.catalog_gz,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/gzip",
                         "X-Catalog-Hash": self.catalog_hash},
            )
        except httpx.HTTPError as exc:
            self.status(f"catalogue: {exc.__class__.__name__}")
            return False
        self.status(f"catalogue PUT HTTP {r.status_code} en {(time.perf_counter() - t0) * 1000:.0f} ms")
        return r.status_code == 200

    # ---------------------------------------------------------------- messages
    def ignore(self, why: str) -> None:
        self.ignored += 1
        print(f"{ts()} message ignoré: {why}", flush=True)

    async def on_message(self, message) -> None:
        if isinstance(message, bytes):
            self.ignore("trame binaire")
            return
        try:
            msg = json.loads(message)
        except json.JSONDecodeError:
            self.ignore("pas du JSON")
            return
        if not isinstance(msg, dict):
            self.ignore("JSON non objet")
            return
        kind = msg.get("t")
        if kind not in ACCEPTED:
            self.ignore(f"type non accepté {str(kind)[:24]!r}")
            return
        if kind == "PING":
            await self.send({"t": "PONG", "c": msg.get("c")})
        elif kind == "CANCEL":
            job_id = msg.get("job_id")
            if isinstance(job_id, str) and JOB_ID_RE.match(job_id):
                self.cancelled.add(job_id)
        elif kind == "PREPARE":
            await self.on_prepare(msg)
        else:  # WELCOME again: nothing to do in the spike
            self.ignore("WELCOME en cours de session")

    async def on_prepare(self, msg: dict) -> None:
        if set(msg) != PREPARE_FIELDS:
            extra = sorted(set(msg) - PREPARE_FIELDS)
            missing = sorted(PREPARE_FIELDS - set(msg))
            self.ignore(f"PREPARE invalide (en trop {extra[:5]}, manquants {missing})")
            return
        job_id = msg["job_id"]
        if not isinstance(job_id, str) or not JOB_ID_RE.match(job_id):
            self.ignore("PREPARE: job_id invalide")
            return
        for key in ("start_fraction", "duration"):
            if isinstance(msg[key], bool) or not isinstance(msg[key], (int, float)):
                self.ignore(f"PREPARE: {key} non numérique")
                return
        if not isinstance(msg["upload_token"], str) or not UPLOAD_TOKEN_RE.fullmatch(msg["upload_token"]) \
                or not isinstance(msg["upload_url"], str) or len(msg["upload_url"]) > 512:
            self.ignore("PREPARE: upload_url/upload_token invalides")
            return
        target = resolve_upload_url(self.http_base, msg["upload_url"])
        if target is None:
            await self.send({"t": "JOB_FAILED", "job_id": job_id, "code": "INVALID_REQUEST"})
            self.failed += 1
            self.status("PREPARE refusé: upload_url hors du serveur")
            return
        assert self.queue is not None
        if self.queue.qsize() >= MAX_QUEUE:
            await self.send({"t": "JOB_FAILED", "job_id": job_id, "code": "BRIDGE_BUSY"})
            return
        await self.queue.put({**msg, "upload_target": target, "received": time.perf_counter()})

    # ---------------------------------------------------------------- jobs
    def prepare_sync(self, job: dict) -> dict:
        """Steps 2-5 of spec §10, in a worker thread. Clip read into memory, temp dir deleted."""
        t0 = time.perf_counter()
        real = bc.resolve_for_open(self.root_real, self.tracks, job["track_id"])
        lookup_ms = (time.perf_counter() - t0) * 1000
        frac, clip = bc.clamp_request(job["start_fraction"], job["duration"])
        clip = min(clip, self.max_clip_s)
        work = tempfile.mkdtemp(prefix=bc.TEMP_PREFIX)
        try:
            res = bc.prepare_clip(self.ffmpeg, self.ffprobe, real, frac, clip, work, self.clip_format)
            if res["bytes"] > MAX_CLIP_BYTES:
                raise bc.JobError(bc.DECODE_ERROR, "clip larger than 2 MB")
            # The output check (empty / too short clip, re-encode with the real length) and the
            # bitrate-estimated duration check are done inside bc.prepare_clip.
            with open(res["out_path"], "rb") as fh:
                data = fh.read()
        finally:
            bc.safe_rmtree(work)
        if not bc.check_magic(data[:12], self.clip_format):
            raise bc.JobError(bc.DECODE_ERROR, "bad magic bytes")
        info = res["info"]
        tags = {k: str(v)[:200] for k in ("title", "artist") if (v := info.tag(k))}
        return {
            "data": data, "sha256": hashlib.sha256(data).hexdigest(),
            "actual_start": round(res["start"], 3), "clip_duration": round(res["clip_duration"], 3),
            "track_duration": round(info.duration, 3), "tags": tags or None,
            "timings": {"lookup_ms": round(lookup_ms, 1), "probe_ms": round(res["probe_ms"], 1),
                        "encode_ms": round(res["encode_ms"], 1), "verify_ms": round(res["verify_ms"], 1),
                        "measure_ms": round(res["measure_ms"], 1),
                        # spike flags, carried with the timings to the relay's /stats JSON
                        "reencoded": res["reencoded"], "duration_estimated": info.duration_estimated},
        }

    async def worker(self) -> None:
        assert self.queue is not None
        while True:
            job = await self.queue.get()
            job_id = job["job_id"]
            t_start = time.perf_counter()
            if job_id in self.cancelled:
                await self.send({"t": "JOB_FAILED", "job_id": job_id, "code": "CANCELLED"})
                continue
            try:
                await self.send({"t": "JOB_PROGRESS", "job_id": job_id, "stage": "ENCODING"})
                res = await asyncio.to_thread(self.prepare_sync, job)
                if job_id in self.cancelled:
                    raise bc.JobError("CANCELLED")
                await self.send({"t": "JOB_PROGRESS", "job_id": job_id, "stage": "UPLOADING"})
                tu = time.perf_counter()
                try:
                    r = await self.http.put(
                        job["upload_target"], content=res["data"],
                        headers={"Authorization": f"Bearer {job['upload_token']}",
                                 "Content-Type": bc.OUTPUT_FORMATS[self.clip_format]["content_type"],
                                 "X-Clip-SHA256": res["sha256"]},
                    )
                except httpx.TimeoutException:
                    raise bc.JobError(bc.TIMEOUT, "upload timeout") from None
                except httpx.HTTPError as exc:
                    raise bc.JobError("INVALID_UPLOAD", f"upload {exc.__class__.__name__}") from None
                if r.status_code != 200:
                    raise bc.JobError("INVALID_UPLOAD", f"upload HTTP {r.status_code}")
                res["timings"]["upload_ms"] = round((time.perf_counter() - tu) * 1000, 1)
                res["timings"]["queue_ms"] = round((t_start - job["received"]) * 1000, 1)
                await self.send({
                    "t": "JOB_DONE", "job_id": job_id, "actual_start": res["actual_start"],
                    "clip_duration": res["clip_duration"], "track_duration": res["track_duration"],
                    "bytes": len(res["data"]), "sha256": res["sha256"], "tags": res["tags"],
                    "timings": res["timings"],  # spike-only field (measurement)
                })
                self.ok += 1
                self.last = f"{job['track_id']} {time.perf_counter() - t_start:.2f} s"
                self.status()
            except bc.JobError as exc:
                await self.send({"t": "JOB_FAILED", "job_id": job_id, "code": exc.code})
                self.failed += 1
                tid = job["track_id"] if isinstance(job["track_id"], str) and job["track_id"] in self.tracks else "<id inconnu>"
                self.last = f"{tid} {exc.code}"
                detail = ""
                if self.args.verbose_paths:
                    detail = f" ({exc.reason}) {exc.detail.strip()[:200]}"
                self.status(f"JOB_FAILED {exc.code}{detail}")
            except Exception as exc:  # noqa: BLE001 - the worker must survive any job
                # Unexpected failure (bug, OSError on the temp dir, file locked by an antivirus):
                # answer the server with a generic code and keep serving the queue. Only the
                # exception class is printed (its message may contain a path).
                await self.send({"t": "JOB_FAILED", "job_id": job_id, "code": INTERNAL})
                self.failed += 1
                self.last = f"<job> {INTERNAL}"
                self.status(f"JOB_FAILED {INTERNAL} ({exc.__class__.__name__})"
                            + (f" {str(exc)[:200]}" if self.args.verbose_paths else ""))
            finally:
                self.cancelled.discard(job_id)


async def amain(args) -> int:
    secret = os.environ.get(args.secret_env, "")
    if not secret:
        raise SystemExit(f"set the shared secret in the environment variable {args.secret_env}")
    purged = purge_temp_dirs()
    bridge = Bridge(args, secret)
    if purged:
        print(f"{purged} dossier(s) temporaire(s) {bc.TEMP_PREFIX}* purgé(s) au démarrage")
    await asyncio.to_thread(bridge.scan)
    try:
        if args.exit_after:
            try:
                await asyncio.wait_for(bridge.run_forever(), timeout=args.exit_after)
            except asyncio.TimeoutError:
                pass
        else:
            await bridge.run_forever()
    finally:
        await bridge.http.aclose()
        print(f"{ts()} arrêt: {bridge.ok} OK, {bridge.failed} échec(s), {bridge.ignored} message(s) ignoré(s)")
    return 0


def main() -> int:
    bc.setup_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", required=True, help="https://relay.example.org (http://127.0.0.1:8765 locally)")
    ap.add_argument("--root", required=True, help="library root")
    ap.add_argument("--name", default="spike", help="display name sent in HELLO")
    ap.add_argument("--secret-env", default="SPIKE_SECRET", help="environment variable holding the secret")
    ap.add_argument("--ffmpeg")
    ap.add_argument("--ffprobe")
    ap.add_argument("--jobs", type=int, default=1, help="parallel jobs (1, max 2)")
    ap.add_argument("--exit-after", type=float, default=0, help="stop after N seconds (tests)")
    ap.add_argument("--verbose-paths", action="store_true", help="debug: print relpaths and tool errors")
    args = ap.parse_args()
    try:
        return asyncio.run(amain(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
