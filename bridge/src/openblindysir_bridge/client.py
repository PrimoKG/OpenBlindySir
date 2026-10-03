"""Outbound client (spec §11): WSS to the server, HTTPS uploads, endless reconnection.

The Bridge accepts exactly WELCOME / PREPARE / CANCEL / PING / SCAN_SOURCES; anything
else is ignored (and counted) rather than trusted.
"""

import asyncio
import contextlib
import random
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import websockets
from pydantic import TypeAdapter, ValidationError

from openblindysir_bridge import __version__
from openblindysir_bridge.catalog import LocalCatalog
from openblindysir_bridge.clip import clamp_request
from openblindysir_bridge.jobs import JobRunner
from openblindysir_bridge.urls import ServerUrl
from openblindysir_protocol.bridge import (
    BRIDGE_ID_HEADER,
    CATALOG_TOKEN_HEADER,
    UPLOAD_SHA256_HEADER,
    BridgeHello,
    BridgePing,
    BridgePong,
    Cancel,
    JobDone,
    JobFailed,
    JobProgress,
    Prepare,
    ScanSources,
    ServerToBridge,
    Welcome,
)
from openblindysir_protocol.compatibility import required_range
from openblindysir_protocol.enums import ClipFormat, JobFailureCode
from openblindysir_protocol.settings import WS_BRIDGE_MAX_BYTES
from openblindysir_protocol.version import PROTOCOL_VERSION

USER_AGENT = f"OpenBlindySir-Bridge/{__version__}"
INBOUND = TypeAdapter(ServerToBridge)
MAX_BACKOFF_S = 30.0
SOURCE_QUEUE_MAX = 4
OUTBOX_MAX = 64


class BridgeConnectionRejected(Exception):
    """A permanent registration failure, identified without server/exception text."""

    def __init__(self, code: str, protocol_range: tuple[int, int] | None = None) -> None:
        self.code = code
        self.protocol_range = protocol_range
        super().__init__(code)


@dataclass
class ClientStatus:
    state: str = "SCANNING"
    replaced: bool = False
    ignored_messages: int = 0
    rtt_ms: float | None = None
    last_error: str | None = None


@dataclass
class BridgeClient:
    server: ServerUrl
    secret: str
    bridge_id: str
    name: str
    formats: list[ClipFormat]
    catalog: Callable[[], LocalCatalog]
    runner: JobRunner
    rescan: Callable[[list[str] | None], Awaitable[None]] | None = None
    status: ClientStatus = field(default_factory=ClientStatus)
    welcome: Welcome | None = None
    _ws: object | None = None
    _outbox: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(maxsize=OUTBOX_MAX))
    _overflow: asyncio.Event = field(default_factory=asyncio.Event)
    _http: httpx.AsyncClient | None = None
    _announced_hash: str | None = None
    _source_queue: asyncio.Queue[ScanSources] = field(
        default_factory=lambda: asyncio.Queue(maxsize=SOURCE_QUEUE_MAX)
    )
    _source_task: asyncio.Task[None] | None = None
    _catalog_task: asyncio.Task[None] | None = None
    _catalog_token: str | None = None

    def ssl_context(self) -> ssl.SSLContext | None:
        """TLS verification is always on; plain ws:// only towards localhost."""
        return ssl.create_default_context() if self.server.scheme == "https" else None

    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                verify=True, timeout=60.0, headers={"User-Agent": USER_AGENT}
            )
        return self._http

    def send(self, msg: JobProgress | JobDone | JobFailed | BridgeHello | BridgePong) -> None:
        self._enqueue(msg.model_dump_json())

    def _enqueue(self, text: str) -> None:
        if self._overflow.is_set():
            return
        try:
            self._outbox.put_nowait(text)
        except asyncio.QueueFull:
            self._overflow.set()

    def _reset_control(self) -> None:
        self.welcome = None
        while not self._outbox.empty():
            self._outbox.get_nowait()
        self._overflow.clear()

    async def upload(self, path: str, token: str, file: Path, sha256: str, mime: str) -> int:
        url = self.server.join_path(path)
        response = await self.http().put(
            url,
            content=file.read_bytes(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": mime,
                UPLOAD_SHA256_HEADER: sha256,
            },
        )
        return response.status_code

    async def upload_catalog(self, token: str) -> int:
        response = await self.http().put(
            self.server.join_path("/api/bridge/catalog"),
            content=self.catalog().to_upload(self.bridge_id),
            headers={
                "Authorization": f"Bearer {self.secret}",
                CATALOG_TOKEN_HEADER: token,
                BRIDGE_ID_HEADER: self.bridge_id,
                "Content-Encoding": "gzip",
                "Content-Type": "application/json",
            },
        )
        return response.status_code

    def notify_rescan(self, *, force: bool = False) -> None:
        """After a rescan: tell the server if the catalogue changed."""
        current = self.catalog().catalog_hash
        if self._ws is not None and (force or current != self._announced_hash):
            self._announced_hash = current
            self._enqueue(f'{{"t":"CATALOG_CHANGED","catalog_hash":"{current}"}}')

    async def run_forever(self) -> None:
        attempt = 0
        while True:
            self.status.state = "CONNECTING"
            try:
                async with websockets.connect(
                    self.server.ws_url(),
                    additional_headers={"Authorization": f"Bearer {self.secret}"},
                    user_agent_header=USER_AGENT,
                    max_size=WS_BRIDGE_MAX_BYTES,
                    ping_interval=15,
                    ping_timeout=30,
                    open_timeout=10,
                    ssl=self.ssl_context(),
                ) as ws:
                    attempt = 0
                    self.status.replaced = False
                    await self._session(ws)
            except (OSError, websockets.WebSocketException, TimeoutError) as exc:
                self.status.last_error = type(exc).__name__
                if isinstance(
                    exc, websockets.exceptions.InvalidStatus
                ) and exc.response.status_code in {401, 403}:
                    raise BridgeConnectionRejected("authentication") from None
                if (
                    isinstance(exc, websockets.ConnectionClosed)
                    and exc.rcvd is not None
                    and exc.rcvd.code == 1008
                ):
                    raise BridgeConnectionRejected(
                        "authentication" if exc.rcvd.reason == "authentication" else "protocol",
                        required_range(exc.rcvd.reason),
                    ) from None
                if isinstance(exc, websockets.ConnectionClosed) and exc.rcvd is not None:
                    self.status.replaced = exc.rcvd.reason == "replaced"
            finally:
                self._ws = None
                self.runner.clear()
                await self._stop_scans()
                await self._stop_catalog_uploads()
                self._reset_control()
            self.status.state = "BACKOFF"
            delay = min(MAX_BACKOFF_S, 2.0**attempt) * random.uniform(0.8, 1.2)  # noqa: S311
            attempt = min(attempt + 1, 5)
            await asyncio.sleep(delay)

    async def _session(self, ws: websockets.ClientConnection) -> None:
        self._reset_control()
        self._ws = ws
        catalog = self.catalog()
        self._announced_hash = catalog.catalog_hash
        hello = BridgeHello(
            t="HELLO",
            bridge_id=self.bridge_id,
            name=self.name,
            version=__version__,
            protocol=PROTOCOL_VERSION,
            catalog_hash=catalog.catalog_hash,
            track_count=len(catalog.entries),
            formats=self.formats,
            allow_full_review=self.runner.allow_full_review,
        )
        tasks: list[asyncio.Task] = []
        try:
            await ws.send(hello.model_dump_json())
            tasks = [
                asyncio.create_task(self._reader(ws)),
                asyncio.create_task(self._writer(ws)),
                asyncio.create_task(self._overflow.wait()),
            ]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if self._overflow.is_set():
                raise ConnectionError("outbound queue full")
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._ws = None
            self.runner.clear()
            await self._stop_scans()
            await self._stop_catalog_uploads()
            self._reset_control()

    async def _reader(self, ws: websockets.ClientConnection) -> None:
        async for raw in ws:
            if isinstance(raw, bytes):
                self.status.ignored_messages += 1
                continue
            await self._handle(raw)

    async def _writer(self, ws: websockets.ClientConnection) -> None:
        while True:
            text = await self._outbox.get()
            await ws.send(text)

    def _fail(self, job_id: str, code: JobFailureCode) -> None:
        self.send(JobFailed(t="JOB_FAILED", job_id=job_id, code=code))

    async def _upload_catalogs(self) -> None:
        """Upload serially; only the newest queued one-shot token can remain valid."""
        while self._catalog_token is not None:
            token, self._catalog_token = self._catalog_token, None
            try:
                for attempt in range(4):
                    status = await self.upload_catalog(token)
                    if status != 429 or self._catalog_token is not None:
                        break
                    if attempt < 3:
                        await asyncio.sleep(0.25 * 2**attempt)
                if not 200 <= status < 300:
                    self.status.last_error = f"CatalogUpload{status}"
            except Exception as exc:
                self.status.last_error = type(exc).__name__

    async def _stop_catalog_uploads(self) -> None:
        self._catalog_token = None
        if self._catalog_task is not None:
            self._catalog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._catalog_task
            self._catalog_task = None

    async def _scan_sources(self) -> None:
        """One bounded worker; filesystem scans never block the WebSocket reader."""
        while not self._source_queue.empty():
            command = self._source_queue.get_nowait()
            if self.rescan is not None:
                try:
                    await self.rescan(command.folders)
                except Exception as exc:
                    self.status.last_error = type(exc).__name__

    async def _stop_scans(self) -> None:
        while not self._source_queue.empty():
            self._source_queue.get_nowait()
        if self._source_task is not None:
            self._source_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._source_task
            self._source_task = None

    async def _handle(self, raw: str) -> None:
        try:
            msg = INBOUND.validate_json(raw)
        except ValidationError:
            self.status.ignored_messages += 1
            return
        match msg:
            case Welcome():
                self.welcome = msg
                self.status.state = "ONLINE"
                if msg.catalog_needed and msg.catalog_upload_token:
                    self._catalog_token = msg.catalog_upload_token
                    if self._catalog_task is None or self._catalog_task.done():
                        self._catalog_task = asyncio.create_task(self._upload_catalogs())
            case Prepare():
                welcome = self.welcome
                if welcome is None:
                    self._fail(msg.job_id, JobFailureCode.QUEUE_FULL)
                    return
                if welcome.clip_format not in self.formats:
                    self.send(
                        JobFailed(
                            t="JOB_FAILED", job_id=msg.job_id, code=JobFailureCode.DECODE_ERROR
                        )
                    )
                    return
                refused = self.runner.submit(msg, clamp_request(msg, welcome))
                if refused is not None:
                    self._fail(msg.job_id, refused)
            case Cancel(job_id=job_id):
                self.runner.cancel(job_id)
            case ScanSources():
                if self.rescan is not None:
                    try:
                        self._source_queue.put_nowait(msg)
                    except asyncio.QueueFull:
                        self.status.ignored_messages += 1
                    else:
                        if self._source_task is None or self._source_task.done():
                            self._source_task = asyncio.create_task(self._scan_sources())
            case BridgePing(c=echo):
                self.send(BridgePong(t="PONG", c=echo))
