"""Links keyed by Bridge identity, with owner-bound jobs and one-shot upload tokens."""

from __future__ import annotations

import asyncio
import secrets
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from starlette.websockets import WebSocket, WebSocketState

from openblindysir_protocol.base import InboundModel
from openblindysir_protocol.bridge import UPLOAD_TOKEN_TTL_S, Cancel, Prepare
from openblindysir_server.auth.sessions import hash_token
from openblindysir_server.game.effects import RequestPrepare
from openblindysir_server.logging import redaction

TOKEN_TTL_MS = UPLOAD_TOKEN_TTL_S * 1000
OUTBOX_MAX = 64


@dataclass(frozen=True, slots=True)
class UploadGrant:
    token_hash: str
    job_id: str
    bridge_id: str
    expires_mono: int
    connection: ActiveBridge


@dataclass(frozen=True, slots=True)
class CatalogGrant:
    token_hash: str
    expires_mono: int


@dataclass(eq=False)
class ActiveBridge:
    bridge_id: str
    name: str
    ws: WebSocket
    last_rx_mono: int
    outbox: deque[str] = field(default_factory=deque)
    close_code: int | None = None
    close_reason: str = ""
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    credential_hash: str | None = None

    def push(self, msg: InboundModel) -> None:
        if self.close_code is not None:
            return
        if len(self.outbox) >= OUTBOX_MAX:
            self.request_close(1013, "outbound queue full")
            return
        self.outbox.append(msg.model_dump_json())
        self.wake.set()

    def request_close(self, code: int, reason: str = "") -> None:
        if self.close_code is None:
            self.close_code = code
            self.close_reason = reason
        self.outbox.clear()
        self.wake.set()

    async def writer(self) -> None:
        try:
            while True:
                await self.wake.wait()
                self.wake.clear()
                while self.outbox and self.close_code is None:
                    await self.ws.send_text(self.outbox.popleft())
                if self.close_code is not None:
                    if self.ws.application_state is WebSocketState.CONNECTED:
                        await self.ws.close(self.close_code, self.close_reason)
                    return
        except Exception:
            return


class BridgeLink:
    def __init__(self) -> None:
        self.connections: dict[str, ActiveBridge] = {}
        self.upload_grants: dict[str, UploadGrant] = {}  # asset_id -> grant
        self.catalog_grants: dict[str, CatalogGrant] = {}  # bridge_id -> grant
        self.job_owner: dict[str, str] = {}  # job_id -> bridge_id
        self._catalog_uploads: set[str] = set()

    @contextmanager
    def catalog_upload(self, bridge_id: str) -> Iterator[bool]:
        """One receiving catalogue per identity, eight globally including replaced links."""
        if bridge_id in self._catalog_uploads or len(self._catalog_uploads) >= 8:
            yield False
            return
        self._catalog_uploads.add(bridge_id)
        try:
            yield True
        finally:
            self._catalog_uploads.discard(bridge_id)

    def activate(self, bridge: ActiveBridge) -> ActiveBridge | None:
        previous = self.connections.get(bridge.bridge_id)
        if previous is not None:
            self.deactivate(previous)
        self.connections[bridge.bridge_id] = bridge
        return previous

    @property
    def active(self) -> ActiveBridge | None:
        return next(iter(self.connections.values()), None)

    def deactivate(self, bridge: ActiveBridge) -> bool:
        if self.connections.get(bridge.bridge_id) is bridge:
            del self.connections[bridge.bridge_id]
            self.catalog_grants.pop(bridge.bridge_id, None)
            for asset_id in [
                a for a, g in self.upload_grants.items() if g.bridge_id == bridge.bridge_id
            ]:
                del self.upload_grants[asset_id]
            return True
        return False

    def prepare(self, eff: RequestPrepare, now_ms: int) -> bool:
        """Send PREPARE with a fresh one-shot upload token; False if the Bridge is absent."""
        bridge = self.connections.get(eff.bridge_id)
        if bridge is None:
            return False
        token = secrets.token_urlsafe(32)
        redaction().add_secret(token)
        self.upload_grants[eff.asset_id] = UploadGrant(
            hash_token(token), eff.job_id, eff.bridge_id, now_ms + TOKEN_TTL_MS, bridge
        )
        self.job_owner[eff.job_id] = eff.bridge_id
        bridge.push(
            Prepare(
                t="PREPARE",
                job_id=eff.job_id,
                track_id=eff.track_id,
                start_fraction=eff.start_fraction,
                duration=eff.duration_s,
                upload_url=f"/api/bridge/assets/{eff.asset_id}",
                upload_token=token,
                normalize_audio=eff.normalize_audio,
                avoid_silence=eff.avoid_silence,
                exact_start=eff.exact_start,
                review_mode=eff.review_mode,
                replay_sha256=eff.replay_sha256,
                expected_source_revision=eff.expected_source_revision,
            )
        )
        return True

    def cancel(self, job_id: str) -> None:
        for asset_id in [a for a, g in self.upload_grants.items() if g.job_id == job_id]:
            del self.upload_grants[asset_id]
        bridge = self.connections.get(self.job_owner.pop(job_id, ""))
        if bridge is not None:
            bridge.push(Cancel(t="CANCEL", job_id=job_id))

    def owns_job(self, bridge_id: str, job_id: str) -> bool:
        return self.job_owner.get(job_id) == bridge_id

    def upload_authorized(self, grant: UploadGrant, now_ms: int) -> bool:
        return (
            self.connections.get(grant.bridge_id) is grant.connection
            and grant.connection.close_code is None
            and self.owns_job(grant.bridge_id, grant.job_id)
            and grant.expires_mono >= now_ms
        )

    def consume_upload_token(self, asset_id: str, token: str, now_ms: int) -> UploadGrant | None:
        grant = self.upload_grants.get(asset_id)
        if grant is None or grant.expires_mono < now_ms:
            return None
        if not secrets.compare_digest(grant.token_hash, hash_token(token)):
            return None
        del self.upload_grants[asset_id]
        return grant

    def issue_catalog_token(self, bridge_id: str, now_ms: int) -> str:
        token = secrets.token_urlsafe(32)
        redaction().add_secret(token)
        self.catalog_grants[bridge_id] = CatalogGrant(hash_token(token), now_ms + TOKEN_TTL_MS)
        return token

    def consume_catalog_token(self, bridge_id: str, token: str, now_ms: int) -> bool:
        grant = self.catalog_grants.get(bridge_id)
        if grant is None or grant.expires_mono < now_ms:
            return False
        if not secrets.compare_digest(grant.token_hash, hash_token(token)):
            return False
        del self.catalog_grants[bridge_id]
        return True

    def reset_tokens(self) -> None:
        self.upload_grants.clear()
        self.catalog_grants.clear()
        self.job_owner.clear()
