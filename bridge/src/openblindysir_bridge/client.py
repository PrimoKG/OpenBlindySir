"""Outbound client (spec §11): WSS to the server, HTTPS uploads, endless reconnection.

The Bridge accepts exactly WELCOME / PREPARE / CANCEL / PING from the server; anything
else is ignored (and counted) rather than trusted.
"""

import asyncio
import contextlib
import random
import ssl
from collections.abc import Callable
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
    ServerToBridge,
    Welcome,
)
from openblindysir_protocol.enums import ClipFormat, JobFailureCode
from openblindysir_protocol.settings import WS_BRIDGE_MAX_BYTES
from openblindysir_protocol.version import PROTOCOL_VERSION

USER_AGENT = f"OpenBlindySir-Bridge/{__version__}"
INBOUND = TypeAdapter(ServerToBridge)
MAX_BACKOFF_S = 30.0


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
    status: ClientStatus = field(default_factory=ClientStatus)
    welcome: Welcome | None = None
    _ws: object | None = None
    _outbox: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    _http: httpx.AsyncClient | None = None
    _announced_hash: str | None = None

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
        self._outbox.put_nowait(msg.model_dump_json())

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
                "Content-Encoding": "gzip",
                "Content-Type": "application/json",
            },
        )
        return response.status_code

    def notify_rescan(self) -> None:
        """After a rescan: tell the server if the catalogue changed."""
        current = self.catalog().catalog_hash
        if self._ws is not None and current != self._announced_hash:
            self._announced_hash = current
            self._outbox.put_nowait(f'{{"t":"CATALOG_CHANGED","catalog_hash":"{current}"}}')

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
                if isinstance(exc, websockets.ConnectionClosed) and exc.rcvd is not None:
                    self.status.replaced = exc.rcvd.reason == "replaced"
            finally:
                self._ws = None
                self.runner.clear()
            self.status.state = "BACKOFF"
            delay = min(MAX_BACKOFF_S, 2.0**attempt) * random.uniform(0.8, 1.2)  # noqa: S311
            attempt += 1
            await asyncio.sleep(delay)

    async def _session(self, ws: websockets.ClientConnection) -> None:
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
        )
        await ws.send(hello.model_dump_json())
        writer = asyncio.create_task(self._writer(ws))
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    self.status.ignored_messages += 1
                    continue
                await self._handle(raw)
        finally:
            writer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await writer

    async def _writer(self, ws: websockets.ClientConnection) -> None:
        while True:
            text = await self._outbox.get()
            await ws.send(text)

    def _fail(self, job_id: str, code: JobFailureCode) -> None:
        self.send(JobFailed(t="JOB_FAILED", job_id=job_id, code=code))

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
                    try:
                        await self.upload_catalog(msg.catalog_upload_token)
                    except httpx.HTTPError as exc:
                        self.status.last_error = type(exc).__name__
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
            case BridgePing(c=echo):
                self.send(BridgePong(t="PONG", c=echo))
