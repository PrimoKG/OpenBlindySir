"""Link with the active Bridge: outbound messages, one-shot upload and catalogue tokens.

V0.1 keeps a single active Bridge; a newly authenticated one replaces it.
"""

import asyncio
import secrets
from collections import deque
from dataclasses import dataclass, field

from starlette.websockets import WebSocket, WebSocketState

from openblindysir_protocol.base import InboundModel
from openblindysir_protocol.bridge import UPLOAD_TOKEN_TTL_S, Cancel, Prepare
from openblindysir_server.auth.sessions import hash_token
from openblindysir_server.game.effects import RequestPrepare
from openblindysir_server.logging import redaction

TOKEN_TTL_MS = UPLOAD_TOKEN_TTL_S * 1000


@dataclass(frozen=True, slots=True)
class UploadGrant:
    token_hash: str
    job_id: str
    bridge_id: str
    expires_mono: int


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

    def push(self, msg: InboundModel) -> None:
        self.outbox.append(msg.model_dump_json())
        self.wake.set()

    def request_close(self, code: int, reason: str = "") -> None:
        if self.close_code is None:
            self.close_code = code
            self.close_reason = reason
        self.wake.set()

    async def writer(self) -> None:
        try:
            while True:
                await self.wake.wait()
                self.wake.clear()
                while self.outbox:
                    await self.ws.send_text(self.outbox.popleft())
                if self.close_code is not None:
                    if self.ws.application_state is WebSocketState.CONNECTED:
                        await self.ws.close(self.close_code, self.close_reason)
                    return
        except Exception:
            return


class BridgeLink:
    def __init__(self) -> None:
        self.active: ActiveBridge | None = None
        self.upload_grants: dict[str, UploadGrant] = {}  # asset_id -> grant
        self.catalog_grants: dict[str, CatalogGrant] = {}  # bridge_id -> grant
        self.job_owner: dict[str, str] = {}  # job_id -> bridge_id

    def activate(self, bridge: ActiveBridge) -> ActiveBridge | None:
        previous, self.active = self.active, bridge
        return previous

    def deactivate(self, bridge: ActiveBridge) -> bool:
        if self.active is bridge:
            self.active = None
            self.catalog_grants.pop(bridge.bridge_id, None)
            for asset_id in [
                a for a, g in self.upload_grants.items() if g.bridge_id == bridge.bridge_id
            ]:
                del self.upload_grants[asset_id]
            return True
        return False

    def prepare(self, eff: RequestPrepare, now_ms: int) -> bool:
        """Send PREPARE with a fresh one-shot upload token; False if the Bridge is absent."""
        bridge = self.active
        if bridge is None or bridge.bridge_id != eff.bridge_id:
            return False
        token = secrets.token_urlsafe(32)
        redaction().add_secret(token)
        self.upload_grants[eff.asset_id] = UploadGrant(
            hash_token(token), eff.job_id, eff.bridge_id, now_ms + TOKEN_TTL_MS
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
            )
        )
        return True

    def cancel(self, job_id: str) -> None:
        for asset_id in [a for a, g in self.upload_grants.items() if g.job_id == job_id]:
            del self.upload_grants[asset_id]
        bridge = self.active
        if bridge is not None and self.job_owner.get(job_id) == bridge.bridge_id:
            bridge.push(Cancel(t="CANCEL", job_id=job_id))

    def owns_job(self, bridge_id: str, job_id: str) -> bool:
        return self.job_owner.get(job_id) == bridge_id

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
