"""Private replay uses isolated, bounded transfers and leaves shared playback untouched."""

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from typing import Any

import pytest
from conftest import BRIDGE_ID, FAKE_M4A, Harness, bridge_hello, catalog, put_asset, put_catalog
from pydantic import TypeAdapter

from openblindysir_protocol.client import ClientMessage
from openblindysir_protocol.enums import GamePhase
from openblindysir_server.game import commands as c
from openblindysir_server.game.state import current_round

CLIENT = TypeAdapter(ClientMessage)
DIGEST = hashlib.sha256(FAKE_M4A).hexdigest()


def receive(ws: Any, kind: str) -> dict[str, Any]:
    for _ in range(30):
        message = ws.receive_json()
        if message["t"] == kind:
            return message
    raise AssertionError(kind)


def host(
    h: Harness, pid: str, command: str, args: dict | None = None, rid: str | None = None
) -> None:
    key = {"round_id": rid} if rid else {"expected_phase": h.runtime.engine.state.game.phase.value}
    message = CLIENT.validate_json(
        json.dumps({"t": "HOST", "cmd": command, **key, "args": args or {}})
    )
    assert h.runtime.dispatch(c.HostIn(pid, message)).error is None


def done(ws: Any, preparation: dict, *, digest: str = DIGEST) -> None:
    ws.send_json(
        {
            "t": "JOB_DONE",
            "job_id": preparation["job_id"],
            "actual_start": 30.0,
            "clip_duration": 20.0,
            "track_duration": 200.0,
            "input_duration": 20.0,
            "source_revision": "b" * 64,
            "bytes": len(FAKE_M4A),
            "sha256": digest,
        }
    )


def enter_review(h: Harness, ws: Any) -> tuple[str, str, str, str]:
    pid, token = h.join("Host")
    h.elevate(token)
    player, player_token = h.join("Player")
    body = catalog()
    ws.send_text(bridge_hello(body["catalog_hash"], 6))
    grant = receive(ws, "WELCOME")["catalog_upload_token"]
    assert put_catalog(h, body, grant).status_code == 204
    host(
        h,
        pid,
        "configure",
        {"rounds": 1, "sources": [{"bridge_id": BRIDGE_ID, "folder_prefix": ""}]},
    )
    for p in (pid, player):
        h.runtime.dispatch(c.Connected(p, "example"))
    host(h, pid, "start_game")
    preparation = receive(ws, "PREPARE")
    assert put_asset(h, preparation["upload_url"], preparation["upload_token"]).status_code == 204
    done(ws, preparation)
    deadline = time.monotonic() + 5
    while (
        h.runtime.engine.asset_info(preparation["upload_url"].rsplit("/", 1)[-1]).actual_start_s
        is None
    ):
        assert time.monotonic() < deadline
        time.sleep(0.01)
    r = current_round(h.runtime.engine.state.game)
    for p in (pid, player):
        audio = CLIENT.validate_json(
            json.dumps(
                {
                    "t": "AUDIO_STATUS",
                    "state": "READY",
                    "asset_id": r.slot.asset_id,
                    "clock": {"offset": 0.0, "rtt_min": 1.0},
                }
            )
        )
        h.runtime.dispatch(c.AudioStatusIn(p, audio))
    h.clock.set(r.official_start_at)
    h.runtime.dispatch(c.Tick())
    host(h, pid, "close", rid=r.id)
    assert h.runtime.engine.state.game.phase is GamePhase.FINAL_SCORE_REVIEW
    return pid, token, player_token, r.id


@pytest.mark.parametrize(
    ("mode", "offset", "duration"), [("excerpt", 0, 20), ("full", 60, 30), ("full", 195, 5)]
)
def test_host_replay_recipe_is_private_bounded_and_does_not_enter_shared_cache(
    harness: Harness, mode: str, offset: int, duration: int
) -> None:
    with harness.bridge_ws() as ws, ThreadPoolExecutor(max_workers=1) as executor:
        pid, token, player_token, rid = enter_review(harness, ws)
        url = f"/api/host/review/{rid}/audio?mode={mode}&offset={offset}"
        assert harness.client.get(url).status_code == 401
        assert harness.client.get(url, headers=harness.cookie(player_token)).status_code == 403
        cache = harness.runtime.cache.items()
        shared = harness.runtime.engine.view_for(pid).play
        future = executor.submit(harness.client.get, url, headers=harness.cookie(token))
        preparation = receive(ws, "PREPARE")
        assert preparation["duration"] == duration
        assert preparation["review_mode"] == mode
        assert preparation["exact_start"] == (30 if mode == "excerpt" else offset)
        assert preparation["expected_source_revision"] == "b" * 64
        assert preparation["replay_sha256"] == (DIGEST if mode == "excerpt" else None)
        assert (
            harness.client.get(
                preparation["upload_url"].replace("/api/bridge/assets/", "/api/audio/"),
                headers=harness.cookie(player_token),
            ).status_code
            == 404
        )
        assert (
            put_asset(harness, preparation["upload_url"], preparation["upload_token"]).status_code
            == 204
        )
        done(ws, preparation)
        response = future.result(5)
        assert response.status_code == 200
        assert response.content == FAKE_M4A
        assert response.headers["cache-control"] == "no-store, private"
        assert response.headers["content-type"].startswith("audio/mp4")
        assert harness.runtime.cache.items() == cache
        assert harness.runtime.engine.view_for(pid).play == shared
        assert not harness.runtime.reviews.jobs


def test_replay_rejects_wrong_excerpt_hash_and_releases_jobs(harness: Harness) -> None:
    with harness.bridge_ws() as ws, ThreadPoolExecutor(max_workers=1) as executor:
        _, token, _, rid = enter_review(harness, ws)
        future = executor.submit(
            harness.client.get, f"/api/host/review/{rid}/audio", headers=harness.cookie(token)
        )
        preparation = receive(ws, "PREPARE")
        other = FAKE_M4A + b"different"
        assert (
            put_asset(
                harness, preparation["upload_url"], preparation["upload_token"], other
            ).status_code
            == 204
        )
        done(ws, preparation, digest=hashlib.sha256(other).hexdigest())
        assert future.result(5).status_code == 503
        assert not harness.runtime.reviews.jobs


def test_phase_change_cancels_pending_replay_without_waiting_for_bridge(harness: Harness) -> None:
    with harness.bridge_ws() as ws, ThreadPoolExecutor(max_workers=1) as executor:
        pid, token, _, rid = enter_review(harness, ws)
        future = executor.submit(
            harness.client.get, f"/api/host/review/{rid}/audio", headers=harness.cookie(token)
        )
        preparation = receive(ws, "PREPARE")
        host(harness, pid, "final_validate", {"confirm_unreviewed": True})
        host(harness, pid, "new_game")
        assert future.result(3).status_code == 409
        assert receive(ws, "CANCEL")["job_id"] == preparation["job_id"]
        assert not harness.runtime.reviews.jobs


def test_replay_requires_final_phase_and_safe_finite_offsets(harness: Harness) -> None:
    with harness.bridge_ws() as ws:
        pid, token, _, rid = enter_review(harness, ws)
        for query in ("offset=-1", "offset=nan", "offset=inf", "offset=200"):
            assert (
                harness.client.get(
                    f"/api/host/review/{rid}/audio?{query}", headers=harness.cookie(token)
                ).status_code
                == 400
            )
        host(harness, pid, "final_validate", {"confirm_unreviewed": True})
        host(harness, pid, "new_game")
        assert (
            harness.client.get(
                f"/api/host/review/{rid}/audio", headers=harness.cookie(token)
            ).status_code
            == 409
        )


def test_old_recipe_without_source_revision_cannot_request_full_listening(harness: Harness) -> None:
    with harness.bridge_ws() as ws:
        _, token, _, rid = enter_review(harness, ws)
        r = harness.runtime.engine.state.game.rounds[0]
        harness.runtime.engine.state.assets[r.slot.asset_id].source_revision = None
        response = harness.client.get(
            f"/api/host/review/{rid}/audio?mode=full", headers=harness.cookie(token)
        )
        assert response.status_code == 404
        assert not harness.runtime.reviews.jobs


def test_private_upload_keeps_two_mib_cap_when_game_cache_limit_is_higher(harness: Harness) -> None:
    with harness.bridge_ws() as ws, ThreadPoolExecutor(max_workers=1) as executor:
        _, token, _, rid = enter_review(harness, ws)
        harness.runtime.cache.max_item_bytes = 4 * 1024 * 1024
        future = executor.submit(
            harness.client.get, f"/api/host/review/{rid}/audio", headers=harness.cookie(token)
        )
        preparation = receive(ws, "PREPARE")
        rejected = harness.client.put(
            preparation["upload_url"],
            content=FAKE_M4A,
            headers={
                "Authorization": f"Bearer {preparation['upload_token']}",
                "X-Content-SHA256": DIGEST,
                "Content-Length": str(2 * 1024 * 1024 + 1),
            },
        )
        assert rejected.status_code == 413
        ws.send_json({"t": "JOB_FAILED", "job_id": preparation["job_id"], "code": "INVALID_UPLOAD"})
        assert future.result(3).status_code == 503
        assert not harness.runtime.reviews.jobs


@pytest.mark.parametrize("replace", [False, True])
def test_bridge_loss_finishes_pending_replay_promptly(harness: Harness, replace: bool) -> None:
    with ThreadPoolExecutor(max_workers=1) as executor, ExitStack() as stack:
        ws = stack.enter_context(harness.bridge_ws())
        _, token, _, rid = enter_review(harness, ws)
        future = executor.submit(
            harness.client.get, f"/api/host/review/{rid}/audio", headers=harness.cookie(token)
        )
        preparation = receive(ws, "PREPARE")
        if replace:
            replacement = stack.enter_context(harness.bridge_ws())
            replacement.send_text(bridge_hello(catalog()["catalog_hash"], 6))
            receive(replacement, "WELCOME")
        else:
            ws.close()
        try:
            assert future.result(3).status_code == 503
        finally:
            # Keep a regression failure bounded instead of waiting for the 75 s timeout.
            assert harness.client.portal is not None
            harness.client.portal.call(harness.runtime.reviews.clear)
        assert not harness.runtime.reviews.jobs
        assert preparation["job_id"] not in harness.runtime.bridge.job_owner
        assert (
            preparation["upload_url"].rsplit("/", 1)[-1] not in harness.runtime.bridge.upload_grants
        )


def test_rejected_private_upload_finishes_replay_without_a_bridge_failure_report(
    harness: Harness,
) -> None:
    with harness.bridge_ws() as ws, ThreadPoolExecutor(max_workers=1) as executor:
        _, token, _, rid = enter_review(harness, ws)
        future = executor.submit(
            harness.client.get, f"/api/host/review/{rid}/audio", headers=harness.cookie(token)
        )
        preparation = receive(ws, "PREPARE")
        assert (
            put_asset(
                harness, preparation["upload_url"], preparation["upload_token"], b"invalid"
            ).status_code
            == 400
        )
        try:
            assert future.result(3).status_code == 503
        finally:
            assert harness.client.portal is not None
            harness.client.portal.call(harness.runtime.reviews.clear)
        assert not harness.runtime.reviews.jobs
