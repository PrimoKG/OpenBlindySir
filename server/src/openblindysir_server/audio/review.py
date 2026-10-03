"""Host-only on-demand replay. At most two bounded clips, never a complete source file."""

import asyncio
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import Response

from openblindysir_protocol.bridge import JobDone, JobFailed, JobProgress
from openblindysir_protocol.enums import GamePhase
from openblindysir_protocol.errors import ErrorCode
from openblindysir_server.auth.routes import current_player
from openblindysir_server.game.effects import RequestPrepare
from openblindysir_server.security import error
from openblindysir_server.state import app_state

router = APIRouter()


@dataclass
class PendingReplay:
    asset_id: str
    owner: str
    bridge_id: str
    expected_hash: str | None
    future: asyncio.Future[tuple[bytes, str] | None]
    upload: tuple[bytes, str, str] | None = None


class ReviewTransfers:
    def __init__(self) -> None:
        self.jobs: dict[str, PendingReplay] = {}

    def accepts(self, asset_id: str) -> bool:
        return any(p.asset_id == asset_id for p in self.jobs.values())

    def uploaded(self, asset_id: str, data: bytes, mime: str, digest: str) -> None:
        for p in self.jobs.values():
            if p.asset_id == asset_id:
                p.upload = data, mime, digest

    def reject(self, asset_id: str) -> None:
        for p in self.jobs.values():
            if p.asset_id == asset_id and not p.future.done():
                p.future.set_result(None)

    def bridge_disconnected(self, bridge_id: str) -> None:
        for p in self.jobs.values():
            if p.bridge_id == bridge_id and not p.future.done():
                p.future.set_result(None)

    def report(self, msg: JobDone | JobFailed | JobProgress) -> bool:
        p = self.jobs.get(msg.job_id)
        if p is None:
            return False
        if p.future.done() or isinstance(msg, JobProgress):
            return True
        result = None
        if isinstance(msg, JobDone) and p.upload is not None:
            data, mime, digest = p.upload
            if (
                msg.sha256 == digest
                and msg.bytes == len(data)
                and (p.expected_hash is None or p.expected_hash == digest)
            ):
                result = data, mime
        p.future.set_result(result)
        return True

    def clear(self) -> None:
        for p in self.jobs.values():
            if not p.future.done():
                p.future.set_result(None)


async def wait_replay(
    request: Request, pending: PendingReplay, allowed: Callable[[], bool]
) -> tuple[bytes, str] | None:
    """Free the Bridge job promptly when seeking, changing round or closing the tab."""
    deadline = asyncio.get_running_loop().time() + 75
    while not pending.future.done():
        if (
            not allowed()
            or await request.is_disconnected()
            or asyncio.get_running_loop().time() >= deadline
        ):
            return None
        await asyncio.wait({pending.future}, timeout=0.25)
    return pending.future.result()


@router.get("/api/host/review/{round_id}/audio")
async def get_review_audio(
    round_id: str, request: Request, mode: Literal["excerpt", "full"] = "excerpt", offset: float = 0
) -> Response:
    state = app_state(request)
    runtime = state.runtime
    pid = current_player(request, state)
    if pid is None:
        return error(401, ErrorCode.UNAUTHENTICATED)
    if not runtime.engine.is_host(pid):
        return error(403, ErrorCode.NOT_HOST)
    s = runtime.engine.state
    game_id = s.game.game_id
    if s.game.phase not in {GamePhase.FINAL_SCORE_REVIEW, GamePhase.FINAL_RESULTS}:
        return error(409, ErrorCode.INVALID_STATE)
    r = next(
        (r for r in s.game.rounds if r.id == round_id and r.official_start_at is not None), None
    )
    asset = s.assets.get(r.slot.asset_id or "") if r else None
    if (
        r is None
        or r.slot.track_ref is None
        or asset is None
        or asset.upload is None
        or asset.actual_start_s is None
    ):
        return error(404, ErrorCode.REVIEW_UNAVAILABLE)
    if mode == "full" and asset.source_revision is None:
        return error(404, ErrorCode.REVIEW_UNAVAILABLE)
    if not math.isfinite(offset) or offset < 0 or offset >= (asset.track_duration_ms or 0) / 1000:
        return error(400, ErrorCode.INVALID_ARGS)
    manager = runtime.reviews
    if len(manager.jobs) >= 2 or any(p.owner == pid for p in manager.jobs.values()):
        return error(429, ErrorCode.RATE_LIMITED)
    job_id, asset_id = s.ids.job_id(), s.ids.asset_id()
    pending = PendingReplay(
        asset_id,
        pid,
        r.slot.track_ref.bridge_id,
        asset.upload.sha256 if mode == "excerpt" else None,
        asyncio.get_running_loop().create_future(),
    )
    manager.jobs[job_id] = pending
    duration = (
        (asset.input_duration_s or (asset.clip_duration_ms or 0) / 1000)
        if mode == "excerpt"
        else min(30, (asset.track_duration_ms or 0) / 1000 - offset)
    )
    effect = RequestPrepare(
        bridge_id=r.slot.track_ref.bridge_id,
        job_id=job_id,
        asset_id=asset_id,
        track_id=r.slot.track_ref.track_id,
        start_fraction=0,
        duration_s=duration,
        normalize_audio=asset.normalize_audio if mode == "excerpt" else False,
        avoid_silence=False,
        exact_start=asset.actual_start_s if mode == "excerpt" else offset,
        review_mode=mode,
        replay_sha256=pending.expected_hash,
        expected_source_revision=asset.source_revision,
    )

    def allowed() -> bool:
        current = runtime.engine.state.game
        return (
            current_player(request, state) == pid
            and runtime.engine.is_host(pid)
            and current.game_id == game_id
            and current.phase in {GamePhase.FINAL_SCORE_REVIEW, GamePhase.FINAL_RESULTS}
        )

    try:
        if not runtime.bridge.prepare(effect, runtime.clock.now().mono_ms):
            return error(503, ErrorCode.BRIDGE_OFFLINE)
        result = await wait_replay(request, pending, allowed)
        if not allowed():
            return error(409, ErrorCode.STALE_COMMAND)
        if result is None:
            return error(503, ErrorCode.REVIEW_UNAVAILABLE)
        data, mime = result
        return Response(
            data,
            media_type=mime,
            headers={
                "Cache-Control": "no-store, private",
                "X-Audio-Offset": str(offset if mode == "full" else 0),
            },
        )
    finally:
        manager.jobs.pop(job_id, None)
        runtime.bridge.cancel(job_id)
