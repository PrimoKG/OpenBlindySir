"""Assets (spec §7.3, §5.3, §7.6): prefetch, client download window, retention, failures."""

from builders import BRIDGE_ID, UPLOAD_SHA, Scenario

from openblindysir_protocol.enums import AssetFailureCode, AssetState, JobFailureCode, RoundState
from openblindysir_server.game import commands as c
from openblindysir_server.game import effects as e


def test_next_asset_requested_when_round_enters_loading() -> None:
    sc = Scenario(auto_serve=False)
    sc.start()
    assert len(sc.pending_jobs) == 1  # only the current round, the round is PREPARING
    sc.serve(sc.pending_jobs.pop(0))
    assert sc.current().state is RoundState.LOADING
    assert len(sc.pending_jobs) == 1  # N+1 requested as N enters LOADING
    assert len(sc.s.game.pipeline) == 1


def test_next_clip_published_only_in_review_and_revealed() -> None:
    sc = Scenario()
    sc.to_open()
    view = sc.view(sc.player_ids[0])
    assert view.audio.current is not None
    assert view.audio.next is None
    assert len(sc.engine.audio_servable()) == 1
    sc.on_round("close")
    assert sc.view(sc.player_ids[0]).audio.next is not None
    assert len(sc.engine.audio_servable()) == 2


def test_no_prefetch_beyond_last_round() -> None:
    sc = Scenario(rounds=1)
    sc.to_open()
    assert not sc.s.game.pipeline


def test_retention_keeps_previous_current_next_and_evicts_the_rest() -> None:
    sc = Scenario(rounds=5)
    first = sc.to_open()
    sc.on_round("close")
    sc.publish()
    second = sc.to_open()
    sc.on_round("close")
    sc.publish()
    sc.to_open()
    assert sc.s.assets[first.slot.asset_id].state is AssetState.EVICTED  # type: ignore[index]
    roles = sc.engine.retained_assets()
    assert second.slot.asset_id in roles
    assert len(roles) == 3


def test_bridge_offline_waits_then_requests_again() -> None:
    sc = Scenario(auto_serve=False)
    sc.start()
    job = sc.pending_jobs.pop(0)
    sc.d(c.BridgeDisconnected(BRIDGE_ID))
    assert sc.s.assets[job.asset_id].error is AssetFailureCode.BRIDGE_OFFLINE
    assert sc.current().slot.waiting_bridge
    assert not sc.pending_jobs
    sc.d(c.BridgeConnected(BRIDGE_ID, "PC", "0.1.0", sc.s.catalogs[BRIDGE_ID].catalog_hash, 12))
    assert len(sc.pending_jobs) == 1
    assert sc.pending_jobs[0].track_id == job.track_id  # same track, no attempt counted
    assert sc.current().slot.attempts == 1


def test_invalid_upload_retried_once_then_replaced() -> None:
    sc = Scenario(auto_serve=False)
    sc.start()
    first = sc.pending_jobs.pop(0)
    sc.d(c.UploadRejected(first.asset_id))
    retry = sc.pending_jobs.pop(0)
    assert retry.track_id == first.track_id
    sc.d(c.UploadRejected(retry.asset_id))
    replacement = sc.pending_jobs.pop(0)
    assert replacement.track_id != first.track_id


def test_job_done_without_matching_upload_is_invalid() -> None:
    sc = Scenario(auto_serve=False)
    sc.start()
    job = sc.pending_jobs.pop(0)
    sc.d(c.UploadVerified(job.asset_id, 999, UPLOAD_SHA, "audio/mp4"))
    from builders import JobDone  # noqa: PLC0415

    done = JobDone.model_validate_json(
        f'{{"t":"JOB_DONE","job_id":"{job.job_id}","actual_start":1,"clip_duration":20,'
        f'"track_duration":200,"bytes":1000,"sha256":"{UPLOAD_SHA}"}}'
    )
    sc.d(c.JobDoneIn(done))
    assert sc.s.assets[job.asset_id].error is AssetFailureCode.INVALID_UPLOAD


def test_job_timeout_fails_and_cancels() -> None:
    sc = Scenario(auto_serve=False)
    sc.start()
    job = sc.pending_jobs.pop(0)
    outcome = sc.advance(120_000)
    assert sc.s.assets[job.asset_id].error is AssetFailureCode.TIMEOUT
    assert e.CancelJob(BRIDGE_ID, job.job_id) in outcome.effects


def test_queue_full_is_not_the_tracks_fault() -> None:
    sc = Scenario(auto_serve=False)
    sc.start()
    job = sc.pending_jobs.pop(0)
    sc.d(c.JobFailedIn(job.job_id, JobFailureCode.QUEUE_FULL))
    assert sc.current().slot.attempts == 1
    assert sc.current().slot.waiting_bridge


def test_majority_decode_failure_replaces_the_track() -> None:
    sc = Scenario()
    sc.start()
    for pid in sc.ids.values():
        sc.audio(pid, "IDLE")
    r = sc.current()
    asset = r.slot.asset_id
    track = r.slot.track_ref
    pids = list(sc.ids.values())
    for pid in pids[:3]:
        sc.audio(pid, "ERROR", error="DECODE_FAILED")
    assert sc.s.assets[asset].error is AssetFailureCode.DECODE_ERROR  # type: ignore[index]
    assert r.slot.track_ref != track
    assert r.state is RoundState.LOADING


def test_late_job_messages_are_ignored() -> None:
    sc = Scenario(auto_serve=False)
    sc.start()
    job = sc.pending_jobs.pop(0)
    sc.d(c.JobFailedIn(job.job_id, JobFailureCode.NOT_FOUND))
    outcome = sc.d(c.JobFailedIn(job.job_id, JobFailureCode.NOT_FOUND))
    assert any(isinstance(x, e.Log) and x.event == "job_late" for x in outcome.effects)
