"""Audio assets (spec §7.3): state machine, slot failure policy, prefetch and retention."""

import unicodedata

from openblindysir_protocol.enums import (
    AssetFailureCode,
    AssetRole,
    AssetState,
    BridgeState,
    GamePhase,
    JobFailureCode,
    JobStage,
    RoundState,
)
from openblindysir_server.game import commands as c
from openblindysir_server.game import selection
from openblindysir_server.game.clock import Instant
from openblindysir_server.game.effects import CancelJob, EffectSink, RequestPrepare
from openblindysir_server.game.state import (
    IN_FLIGHT_ASSET_STATES,
    AssetRecord,
    Round,
    SessionState,
    Slot,
    TrackRef,
    UploadInfo,
    current_round,
)

TRACK_FAILURES = frozenset(
    {
        AssetFailureCode.NOT_FOUND,
        AssetFailureCode.DECODE_ERROR,
        AssetFailureCode.TOO_SHORT,
        AssetFailureCode.TIMEOUT,
    }
)
TAG_MAX = 200


def map_job_failure(code: JobFailureCode) -> AssetFailureCode:
    """A full Bridge queue is not the track's fault: retry later like an offline Bridge."""
    if code is JobFailureCode.QUEUE_FULL:
        return AssetFailureCode.BRIDGE_OFFLINE
    return AssetFailureCode(code.value)


def sanitize_tag(value: str | None) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFC", value)
    text = "".join(ch for ch in text if unicodedata.category(ch) not in {"Cc", "Cf"}).strip()
    return text[:TAG_MAX] or None


def bridge_online(s: SessionState, bridge_id: str) -> bool:
    info = s.bridges.get(bridge_id)
    return info is not None and info.state is BridgeState.ONLINE


# --- asset machine -----------------------------------------------------------------------


def request_asset(s: SessionState, slot: Slot, at: Instant, fx: EffectSink) -> None:
    track = slot.track_ref
    assert track is not None
    asset_id = s.ids.asset_id()
    job_id = s.ids.job_id()
    s.assets[asset_id] = AssetRecord(
        asset_id=asset_id,
        track_ref=track,
        job_id=job_id,
        state=AssetState.REQUESTED,
        requested_at=at.mono_ms,
        job_deadline=at.mono_ms + s.config.job_timeout_ms,
    )
    s.jobs[job_id] = asset_id
    slot.asset_id = asset_id
    fx.add(
        RequestPrepare(
            bridge_id=track.bridge_id,
            job_id=job_id,
            asset_id=asset_id,
            track_id=track.track_id,
            start_fraction=s.rng.random(),
            duration_s=float(s.game.settings.clip_seconds),
        )
    )
    fx.log("job_requested", track_id=track.track_id, job_id=job_id)


def fail_asset(s: SessionState, asset: AssetRecord, code: AssetFailureCode, fx: EffectSink) -> None:
    if asset.state not in IN_FLIGHT_ASSET_STATES:
        return
    asset.state = AssetState.FAILED
    asset.error = code
    s.touched = True
    fx.log("job_failed", job_id=asset.job_id, code=code.value)


def asset_for_job(s: SessionState, job_id: str) -> AssetRecord | None:
    asset_id = s.jobs.get(job_id)
    return s.assets.get(asset_id) if asset_id else None


def handle_job_progress(s: SessionState, cmd: c.JobProgressIn, at: Instant, fx: EffectSink) -> None:
    del at
    asset = asset_for_job(s, cmd.job_id)
    if asset is None or asset.state not in IN_FLIGHT_ASSET_STATES:
        fx.log("job_late", job_id=cmd.job_id)
        return
    asset.stage = cmd.stage
    if cmd.stage is JobStage.UPLOADING:
        asset.state = AssetState.UPLOADING
    elif asset.state is AssetState.REQUESTED:
        asset.state = AssetState.ENCODING
    s.touched = True


def handle_upload_verified(
    s: SessionState, cmd: c.UploadVerified, at: Instant, fx: EffectSink
) -> None:
    del at
    asset = s.assets.get(cmd.asset_id)
    if asset is None or asset.state not in IN_FLIGHT_ASSET_STATES:
        fx.log("job_late", asset_ref=cmd.asset_id[:10])
        return
    asset.upload = UploadInfo(size=cmd.size, sha256=cmd.sha256, mime=cmd.mime)
    asset.state = AssetState.UPLOADING
    s.touched = True


def handle_upload_rejected(
    s: SessionState, cmd: c.UploadRejected, at: Instant, fx: EffectSink
) -> None:
    del at
    asset = s.assets.get(cmd.asset_id)
    if asset is not None:
        fail_asset(s, asset, AssetFailureCode.INVALID_UPLOAD, fx)


def handle_cache_refused(s: SessionState, cmd: c.CacheRefused, at: Instant, fx: EffectSink) -> None:
    del at
    asset = s.assets.get(cmd.asset_id)
    if asset is not None and asset.state in IN_FLIGHT_ASSET_STATES:
        r = current_round(s.game)
        s.game.cache_full_round = r.id if r is not None else None
        fail_asset(s, asset, AssetFailureCode.INVALID_UPLOAD, fx)


def handle_job_done(s: SessionState, cmd: c.JobDoneIn, at: Instant, fx: EffectSink) -> None:
    msg = cmd.msg
    asset = asset_for_job(s, msg.job_id)
    if asset is None or asset.state not in IN_FLIGHT_ASSET_STATES:
        fx.log("job_late", job_id=msg.job_id)
        return
    upload = asset.upload
    if upload is None or upload.sha256 != msg.sha256 or upload.size != msg.bytes:
        fail_asset(s, asset, AssetFailureCode.INVALID_UPLOAD, fx)
        return
    asset.state = AssetState.STORED
    asset.actual_start_s = msg.actual_start
    asset.clip_duration_ms = round(msg.clip_duration * 1000)
    asset.track_duration_ms = round(msg.track_duration * 1000)
    if msg.tags is not None:
        asset.title = sanitize_tag(msg.tags.title)
        asset.artist = sanitize_tag(msg.tags.artist)
    s.touched = True
    wake_waiting_slots(s, asset.track_ref.bridge_id)
    fx.log("asset_stored", job_id=msg.job_id, bytes=msg.bytes)
    fx.log("job_done", job_id=msg.job_id, ms=at.mono_ms - asset.requested_at, bytes=msg.bytes)


def handle_job_failed(s: SessionState, cmd: c.JobFailedIn, at: Instant, fx: EffectSink) -> None:
    del at
    asset = asset_for_job(s, cmd.job_id)
    if asset is None or asset.state not in IN_FLIGHT_ASSET_STATES:
        fx.log("job_late", job_id=cmd.job_id)
        return
    fail_asset(s, asset, map_job_failure(cmd.code), fx)
    if cmd.code is not JobFailureCode.QUEUE_FULL:
        wake_waiting_slots(s, asset.track_ref.bridge_id)


def handle_asset_evicted(s: SessionState, cmd: c.AssetEvicted, at: Instant, fx: EffectSink) -> None:
    del at
    asset = s.assets.get(cmd.asset_id)
    if asset is None or asset.state is not AssetState.STORED:
        fx.log("job_late", asset_ref=cmd.asset_id[:10])
        return
    asset.state = AssetState.EVICTED
    s.touched = True
    for slot in s.game.pipeline:
        if slot.asset_id == cmd.asset_id:
            slot.asset_id = None
    fx.log("asset_evicted", reason="cache_full")


def fail_in_flight_of_bridge(s: SessionState, bridge_id: str, fx: EffectSink) -> None:
    for asset in s.assets.values():
        if asset.track_ref.bridge_id == bridge_id and asset.state in IN_FLIGHT_ASSET_STATES:
            fail_asset(s, asset, AssetFailureCode.BRIDGE_OFFLINE, fx)


def expire_job(s: SessionState, asset: AssetRecord, fx: EffectSink) -> None:
    """Timer ``job_timeout``: FAILED(TIMEOUT) and the Bridge is told to cancel."""
    if asset.state in IN_FLIGHT_ASSET_STATES:
        fx.add(CancelJob(asset.track_ref.bridge_id, asset.job_id))
        fail_asset(s, asset, AssetFailureCode.TIMEOUT, fx)


# --- slots: failure policy and requests ---------------------------------------------------


def _replace_track(s: SessionState, slot: Slot) -> bool:
    """Move the slot to a new track; False when the slot ran out of attempts."""
    if slot.attempts >= s.config.max_track_attempts:
        return False
    slot.track_ref = selection.take(s)
    slot.asset_id = None
    slot.same_track_retries = 0
    slot.waiting_bridge = False
    if slot.track_ref is not None:
        slot.attempts += 1
    return True


def _settle_slot(s: SessionState, slot: Slot, at: Instant, fx: EffectSink) -> bool | None:
    """Advance one slot. Returns True if it changed, False if not, None if exhausted."""
    if slot.track_ref is None:
        ref = selection.take(s)
        if ref is None:
            return False
        slot.track_ref = ref
        slot.attempts += 1
        return True
    asset = s.assets.get(slot.asset_id) if slot.asset_id else None
    if asset is not None and asset.state is AssetState.FAILED:
        code = asset.error or AssetFailureCode.DECODE_ERROR
        if code is AssetFailureCode.BRIDGE_OFFLINE:
            slot.asset_id = None
            slot.waiting_bridge = True
            return True
        if code is AssetFailureCode.CANCELLED:
            slot.asset_id = None
            return True
        if (
            code is AssetFailureCode.INVALID_UPLOAD
            and slot.same_track_retries < s.config.max_same_track_retries
        ):
            slot.same_track_retries += 1
            slot.asset_id = None
            return True
        s.game.unavailable.add(slot.track_ref)
        fx.log("track_unavailable", track_id=slot.track_ref.track_id, code=code.value)
        if not _replace_track(s, slot):
            return None
        return True
    if asset is not None and asset.state is AssetState.EVICTED:
        slot.asset_id = None
        return True
    if slot.asset_id is None:
        if slot.waiting_bridge:
            return False  # woken up by wake_waiting_slots when the Bridge can take a job
        if not bridge_online(s, slot.track_ref.bridge_id):
            slot.waiting_bridge = True
            return True
        request_asset(s, slot, at, fx)
        return True
    return False


def wake_waiting_slots(s: SessionState, bridge_id: str) -> None:
    """A Bridge came back or freed a place in its queue: waiting slots may request again."""
    if not bridge_online(s, bridge_id):
        return
    r = current_round(s.game)
    slots = [*s.game.pipeline, *([r.slot] if r is not None else [])]
    for slot in slots:
        if (
            slot.waiting_bridge
            and slot.track_ref is not None
            and slot.track_ref.bridge_id == bridge_id
        ):
            slot.waiting_bridge = False
            s.touched = True


def settle_slots(s: SessionState, at: Instant, fx: EffectSink) -> bool:
    """Request, retry or replace tracks of the current round and of the prefetch pipeline."""
    from openblindysir_server.game import rounds  # noqa: PLC0415 - mutual recursion

    changed = False
    r = current_round(s.game)
    if r is not None and r.state in (RoundState.QUEUED, RoundState.PREPARING):
        result = _settle_slot(s, r.slot, at, fx)
        if result is None:
            rounds.fail_current_round(s, r, at, fx)
            return True
        changed |= result
    for slot in list(s.game.pipeline):
        result = _settle_slot(s, slot, at, fx)
        if result is None:
            s.game.pipeline.remove(slot)
            changed = True
        else:
            changed |= result
    if changed:
        s.touched = True
    return changed


# --- prefetch pipeline ---------------------------------------------------------------------


def pipeline_target(s: SessionState) -> int:
    g = s.game
    r = current_round(g)
    if g.phase is not GamePhase.IN_GAME or g.ending is not None or r is None:
        return 0  # spec §7.1: prefetch stops when the end is requested
    if r.state in (RoundState.QUEUED, RoundState.PREPARING):
        return 0  # spec §7.3: N+1 is requested only once N enters LOADING
    remaining = g.settings.rounds - r.number
    return max(0, min(g.settings.prefetch_depth, remaining))


def ensure_pipeline(s: SessionState, at: Instant, fx: EffectSink) -> bool:
    del at, fx
    pipeline = s.game.pipeline
    target = pipeline_target(s)
    changed = False
    while len(pipeline) < target:
        ref = selection.take(s)
        if ref is None:
            break
        pipeline.append(Slot(track_ref=ref, attempts=1))
        changed = True
    while len(pipeline) > target:
        slot = pipeline.pop()
        if slot.track_ref is not None:
            s.game.queue.appendleft(slot.track_ref)
        changed = True
    if changed:
        s.touched = True
    return changed


# --- retention -----------------------------------------------------------------------------


def previous_round(s: SessionState) -> Round | None:
    """The last REVEALED round before the current one."""
    g = s.game
    if g.current_index is None or g.phase is not GamePhase.IN_GAME:
        return None
    for r in reversed(g.rounds[: g.current_index]):
        if r.state is RoundState.REVEALED:
            return r
    return None


def retained_assets(s: SessionState) -> dict[str, AssetRole]:
    """Assets kept in RAM: previous, current, next (and next2). Everything else is evicted."""
    roles: dict[str, AssetRole] = {}
    previous = previous_round(s)
    if previous is not None and previous.slot.asset_id:
        roles[previous.slot.asset_id] = AssetRole.PREVIOUS
    r = current_round(s.game)
    if (
        r is not None
        and r.state not in (RoundState.CANCELLED, RoundState.FAILED)
        and r.slot.asset_id
    ):
        roles[r.slot.asset_id] = AssetRole.CURRENT
    for index, slot in enumerate(s.game.pipeline):
        if slot.asset_id:
            roles[slot.asset_id] = AssetRole.NEXT if index == 0 else AssetRole.NEXT2
    return roles


def retire_unretained(s: SessionState, at: Instant, fx: EffectSink) -> bool:
    del at
    retained = retained_assets(s)
    changed = False
    for asset in s.assets.values():
        if asset.asset_id in retained:
            continue
        if asset.state is AssetState.STORED:
            asset.state = AssetState.EVICTED
            fx.log("asset_evicted", job_id=asset.job_id)
            changed = True
        elif asset.state in IN_FLIGHT_ASSET_STATES:
            fx.add(CancelJob(asset.track_ref.bridge_id, asset.job_id))
            asset.state = AssetState.FAILED
            asset.error = AssetFailureCode.CANCELLED
            changed = True
    if changed:
        s.touched = True
    return changed


def stored(s: SessionState, asset_id: str | None) -> AssetRecord | None:
    asset = s.assets.get(asset_id) if asset_id else None
    return asset if asset is not None and asset.state is AssetState.STORED else None


def track_of_slot(slot: Slot) -> TrackRef | None:
    return slot.track_ref
