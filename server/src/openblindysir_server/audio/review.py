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
from openblindysir_server.game import commands as c
from openblindysir_server.game import selection
from openblindysir_server.game.effects import RequestPrepare
from openblindysir_server.game.state import TrackRef
from openblindysir_server.library.management import host_access
from openblindysir_server.security import check_origin, error
from openblindysir_server.state import app_state

router = APIRouter()


@router.get("/api/host/library/{bridge_id}/{track_id}/preview")
async def library_preview(bridge_id: str, track_id: str, request: Request) -> Response:
    """Private, bounded midpoint excerpt; never enters the game pool or public cache."""
    state = app_state(request)
    denied = host_access(request, state)
    if denied is not None:
        return denied
    runtime = state.runtime
    pid = current_player(request, state)
    assert pid is not None
    s = runtime.engine.state
    ref = TrackRef(bridge_id, track_id)
    if not selection.track_exists(s, ref):
        return error(404, ErrorCode.NOT_FOUND)
    if not selection.online(s, ref):
        return error(503, ErrorCode.BRIDGE_OFFLINE)
    manager = runtime.reviews
    if len(manager.jobs) >= 2 or any(p.owner == pid for p in manager.jobs.values()):
        return error(429, ErrorCode.RATE_LIMITED)
    game_id = s.game.game_id
    phase = s.game.phase
    job_id, asset_id = s.ids.job_id(), s.ids.asset_id()
    pending = PendingReplay(
        asset_id, pid, bridge_id, None, asyncio.get_running_loop().create_future()
    )
    manager.jobs[job_id] = pending
    effect = RequestPrepare(
        bridge_id, job_id, asset_id, track_id, 0.5, 15, avoid_silence=False, review_mode="preview"
    )

    def allowed() -> bool:
        return (
            current_player(request, state) == pid
            and host_access(request, state) is None
            and runtime.engine.state.game.game_id == game_id
            and runtime.engine.state.game.phase is phase
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
        return Response(data, media_type=mime, headers={"Cache-Control": "no-store, private"})
    finally:
        manager.jobs.pop(job_id, None)
        runtime.bridge.cancel(job_id)


@router.post("/api/host/finale/{round_id}/listen")
async def listen_together(round_id: str, request: Request) -> Response:
    """Prepare once, then offer the verified excerpt to everyone through normal PLAY."""
    state = app_state(request)
    runtime = state.runtime
    if not check_origin(request.headers.get("origin"), state.settings):
        return error(403, ErrorCode.FORBIDDEN_ORIGIN)
    pid = current_player(request, state)
    if pid is None:
        return error(401, ErrorCode.UNAUTHENTICATED)
    if not runtime.engine.is_host(pid):
        return error(403, ErrorCode.NOT_HOST)
    s = runtime.engine.state
    game_id = s.game.game_id
    revision = s.game.finale_audio_revision
    if s.game.phase is not GamePhase.FINAL_SCORE_REVIEW or s.game.finale_round_id != round_id:
        return error(409, ErrorCode.INVALID_STATE)
    r = next(r for r in s.game.rounds if r.id == round_id)
    asset_id = r.slot.asset_id
    if asset_id is None:
        return error(404, ErrorCode.REVIEW_UNAVAILABLE)
    evicted_ids: tuple[str, ...] = ()
    if not runtime.cache.has(asset_id):
        response = await get_review_audio(round_id, request, "excerpt", 0)
        if response.status_code != 200:
            return response
        if (
            current_player(request, state) != pid
            or not runtime.engine.is_host(pid)
            or runtime.engine.state.game.game_id != game_id
            or runtime.engine.state.game.finale_round_id != round_id
            or runtime.engine.state.game.phase is not GamePhase.FINAL_SCORE_REVIEW
            or runtime.engine.state.game.finale_audio_revision != revision
        ):
            return error(409, ErrorCode.STALE_COMMAND)
        keep = frozenset(runtime.engine.retained_assets())
        stored = runtime.cache.put_pending(
            asset_id, bytes(response.body), response.media_type or "audio/aac", keep
        )
        evicted_ids = stored.evicted
        if not stored.stored:
            for evicted in evicted_ids:
                runtime.dispatch(c.AssetEvicted(evicted))
            return error(503, ErrorCode.REVIEW_UNAVAILABLE)
    outcome = runtime.dispatch(c.FinaleReplayReady(pid, game_id, round_id, revision))
    for evicted in evicted_ids:
        runtime.dispatch(c.AssetEvicted(evicted))
    if outcome.error:
        return error(409, outcome.error)
    return Response(status_code=204)


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
