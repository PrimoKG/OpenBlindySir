"""Adverse cases found by the 2026-10-05 audit, independent of the happy paths."""

import json
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock

import pytest
from conftest import BLIND, ORIGIN, Harness, settings_for_test
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_library_v02 import private_library
from test_session_access import access, request_join

from openblindysir_protocol.enums import GamePhase, HostMode, Role
from openblindysir_protocol.metadata import MetadataDocument
from openblindysir_protocol.version import PROTOCOL_VERSION
from openblindysir_server.auth import access_routes
from openblindysir_server.game import FakeClock, SequentialIds, selection
from openblindysir_server.game.state import Metadata, TrackRef, is_participant
from openblindysir_server.library import management
from openblindysir_server.main import create_app
from openblindysir_server.ratelimit import ConnectionCounter


@pytest.mark.parametrize("field", ["code", "invitation"])
@pytest.mark.parametrize(
    "value", ["é", "\x00", "\uff21\uff22\uff23\uff24\uff25\uff26", "🚀", "a" * 257]
)
def test_untrusted_access_formats_never_raise(harness: Harness, field: str, value: str):
    _, host = harness.join("Host")
    harness.elevate(host)
    access(harness, host)
    response = request_join(harness, "Player", **{field: value})
    assert response.status_code in {400, 401}
    assert "set-cookie" not in response.headers
    assert len(harness.runtime.engine.state.players) == 1


def approve(h: Harness, host: str, claim: dict) -> None:
    assert (
        h.client.post(
            "/api/host/session/access/decide",
            json={"request_id": claim["request_id"], "approve": True},
            headers={"origin": ORIGIN, **h.cookie(host)},
        ).status_code
        == 200
    )


@pytest.mark.parametrize("failure", [OSError, ValueError])
@pytest.mark.parametrize("action", ["rotate", "transfer", "legacy"])
def test_failed_credential_commit_preserves_cookie_claim_and_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: type[Exception], action: str
):
    settings = settings_for_test(state_dir=tmp_path / "state")
    clock = FakeClock()
    app = create_app(
        settings, clock=clock, ids=SequentialIds(), rng=random.Random(1), background_tasks=False
    )
    with TestClient(app, base_url=ORIGIN) as client:
        h = Harness(client, clock)
        _, host = h.join("Host")
        h.elevate(host)
        pid, old = h.join("Alice")
        details = access(h, host)
        claim = request_join(h, "Alice", code=details["code"]).json()
        approve(h, host, claim)
        recovery = client.post(
            "/api/session/recovery-code", json={}, headers={"origin": ORIGIN, **h.cookie(old)}
        ).json()["code"]
        client.cookies.clear()
        snapshot = (settings.state_dir / "session.json").read_bytes()
        with h.player_ws(old) as ws:
            ws.send_json({"t": "HELLO", "protocol": PROTOCOL_VERSION, "client_version": "example"})
            assert ws.receive_json()["t"] == "STATE"
            before = h.runtime.engine.state.players[pid].role
            store = h.runtime.snapshots
            assert store is not None
            original = store.save
            with monkeypatch.context() as patcher:
                patcher.setattr(
                    store, "save", Mock(side_effect=failure("synthetic storage failure"))
                )
                if action == "rotate":
                    response = client.post(
                        "/api/host/session/access",
                        json={"code": "EXAMPLE2"},
                        headers={"origin": ORIGIN, **h.cookie(host)},
                    )
                elif action == "transfer":
                    response = client.post(
                        "/api/session/access/poll",
                        json={key: claim[key] for key in ("request_id", "token")},
                        headers={"origin": ORIGIN},
                    )
                else:
                    response = client.post(
                        "/api/session/recover",
                        json={"password": BLIND, "code": recovery},
                        headers={"origin": ORIGIN},
                    )
                client.cookies.clear()
                assert response.status_code == 503
                assert response.json() == {"error": "persistence_failed"}
                assert "set-cookie" not in response.headers
                assert h.runtime.engine.state.persistence_status == "failed"
                assert h.runtime.hub.current(pid) is not None
                assert h.runtime.engine.state.players[pid].role is before
                assert access(h, host)["code"] == details["code"]
                assert claim["request_id"] in h.runtime.sessions.access.claims
                assert (settings.state_dir / "session.json").read_bytes() != b""
                disk = json.loads((settings.state_dir / "session.json").read_text(encoding="utf-8"))
                assert store.decode_access(disk["access"])["code"] == details["code"]
                restarted = create_app(settings, clock=clock, background_tasks=False)
                with TestClient(restarted, base_url=ORIGIN) as other:
                    assert other.get("/api/session", headers=h.cookie(old)).status_code == 200
            assert store.save == original
            assert snapshot  # Actual persisted state existed before the injected failure.
            # Approval/code remains usable: retry after storage is repaired.
            resumed = client.post(
                "/api/session/access/poll",
                json={key: claim[key] for key in ("request_id", "token")},
                headers={"origin": ORIGIN},
            )
            assert resumed.status_code == 200
            new = resumed.cookies["openblindysir_dev"]
            client.cookies.clear()
            assert client.get("/api/session", headers=h.cookie(old)).status_code == 401
            restarted = create_app(settings, clock=clock, background_tasks=False)
            with TestClient(restarted, base_url=ORIGIN) as other:
                assert other.get("/api/session", headers=h.cookie(old)).status_code == 401
                assert other.get("/api/session", headers=h.cookie(new)).status_code == 200


def test_failed_lazy_access_creation_does_not_expose_an_unpersisted_code(tmp_path, monkeypatch):
    app = create_app(settings_for_test(state_dir=tmp_path / "state"), background_tasks=False)
    with TestClient(app, base_url=ORIGIN) as client:
        h = Harness(client, app.state.obs.runtime.clock)
        _, host = h.join("Host")
        h.elevate(host)
        with monkeypatch.context() as patcher:
            patcher.setattr(
                h.runtime.snapshots, "save", Mock(side_effect=OSError("synthetic failure"))
            )
            for route in ("/api/host/session/access", "/api/session/access-code"):
                assert client.get(route, headers=h.cookie(host)).status_code == 503
                assert h.runtime.sessions.access.code == ""
        assert access(h, host)["code"]


def test_shared_code_reads_are_read_only_and_limited(harness, monkeypatch):
    _, host = harness.join("Host")
    harness.elevate(host)
    details = access(harness, host)
    _, player = harness.join("Player")
    save = Mock()
    monkeypatch.setattr(harness.runtime, "save_snapshot", save)
    for _ in range(30):
        result = harness.client.get("/api/session/access-code", headers=harness.cookie(player))
        assert result.json() == {"code": details["code"]}
    assert save.call_count == 0
    assert (
        harness.client.get("/api/session/access-code", headers=harness.cookie(player)).status_code
        == 429
    )
    harness.clock.advance(60000)
    assert (
        harness.client.get("/api/session/access-code", headers=harness.cookie(player)).status_code
        == 200
    )


def test_claim_spam_cannot_replace_pending_requests_or_block_other_identity(harness):
    _, host = harness.join("Host")
    harness.elevate(host)
    _, alice = harness.join("Alice")
    harness.join("Bob")
    code = access(harness, host)["code"]
    claims = [request_join(harness, "Alice", code=code).json() for _ in range(2)]
    for _ in range(30):
        assert request_join(harness, "Alice", code=code).status_code == 429
    assert request_join(harness, "Bob", code=code).status_code == 202
    visible = access(harness, host)["requests"]
    for claim in claims:
        row = next(row for row in visible if row["request_id"] == claim["request_id"])
        assert row["reference"] == claim["reference"]
        assert re.fullmatch(r"[0-9A-F]{8}", row["reference"])
    assert claims[0]["reference"] != claims[1]["reference"]
    approve(harness, host, claims[1])
    assert (
        harness.client.post(
            "/api/session/access/poll",
            json={key: claims[1][key] for key in ("request_id", "token")},
            headers={"origin": ORIGIN},
        ).status_code
        == 200
    )
    harness.client.cookies.clear()
    assert (
        harness.client.post(
            "/api/session/access/poll",
            json={key: claims[0][key] for key in ("request_id", "token")},
            headers={"origin": ORIGIN},
        ).status_code
        == 401
    )
    assert harness.client.get("/api/session", headers=harness.cookie(alice)).status_code == 401


def test_access_rechecks_failures_after_delayed_body(harness, monkeypatch):
    _, host = harness.join("Host")
    harness.elevate(host)
    code = access(harness, host)["code"]
    original = access_routes.read_json_body

    async def delayed(request):
        body = await original(request)
        harness.clock.advance(1000)
        limiter = harness.app.state.obs.join_limiter
        for _ in range(limiter.limit):
            limiter.record("testclient", harness.clock.now().mono_ms)
        return body

    monkeypatch.setattr(access_routes, "read_json_body", delayed)
    assert request_join(harness, "Late", code=code).status_code == 429
    assert len(harness.runtime.engine.state.players) == 1
    assert not harness.runtime.sessions.access.claims


@pytest.mark.parametrize("phase", list(GamePhase))
@pytest.mark.parametrize(
    ("mode", "spectator"),
    [(None, False), (None, True), (HostMode.PLAYER, False), (HostMode.MC, False)],
)
@pytest.mark.parametrize("method", ["shared", "legacy"])
def test_identity_transfer_preserves_participation_without_host_privileges(
    harness, phase, mode, spectator, method
):
    _, host = harness.join("Host")
    harness.elevate(host)
    pid, _old = harness.join("Subject")
    player = harness.runtime.engine.state.players[pid]
    player.role = Role.HOST if mode is not None else Role.PLAYER
    player.host_mode = mode or HostMode.PLAYER
    player.spectator = spectator
    harness.runtime.engine.state.game.phase = phase
    before = is_participant(player)
    if method == "shared":
        claim = request_join(harness, "Subject", code=access(harness, host)["code"]).json()
        approve(harness, host, claim)
        response = harness.client.post(
            "/api/session/access/poll",
            json={key: claim[key] for key in ("request_id", "token")},
            headers={"origin": ORIGIN},
        )
    else:
        code = harness.runtime.sessions.recovery_code(pid)
        response = harness.client.post(
            "/api/session/recover",
            json={"code": code, "password": BLIND},
            headers={"origin": ORIGIN},
        )
    assert response.status_code == 200
    restored = harness.runtime.engine.state.players[pid]
    assert restored.role is Role.PLAYER
    assert is_participant(restored) is before


def test_configured_venue_capacity_and_browser_replacement_behind_one_nat():
    clock = FakeClock()
    app = create_app(
        settings_for_test(max_players=32), clock=clock, ids=SequentialIds(), background_tasks=False
    )
    with TestClient(app, base_url=ORIGIN) as client, ExitStack() as stack:
        h = Harness(client, clock)
        tokens = [h.join(f"Player {i}")[1] for i in range(32)]
        for token in tokens:
            ws = stack.enter_context(h.player_ws(token))
            ws.send_json({"t": "HELLO", "protocol": PROTOCOL_VERSION, "client_version": "example"})
            assert ws.receive_json()["t"] == "STATE"
        with h.player_ws(tokens[0]) as replacement:
            replacement.send_json(
                {"t": "HELLO", "protocol": PROTOCOL_VERSION, "client_version": "example"}
            )
            assert replacement.receive_json()["t"] == "STATE"


def test_websocket_floods_remain_bounded_per_identity_and_globally(harness):
    _, token = harness.join("Player")
    with harness.player_ws(token), harness.player_ws(token):
        with pytest.raises(WebSocketDisconnect) as caught, harness.player_ws(token):
            pass
        assert caught.value.code == 1008
    assert not harness.app.state.obs.ws_counter._open
    assert not harness.app.state.obs.player_ws_counter._open
    counter = ConnectionCounter(10, global_limit=2)
    assert counter.acquire("a")
    assert counter.acquire("b")
    assert not counter.acquire("c")
    counter.release("a")
    counter.release("a")
    assert counter.acquire("c")


def test_search_worker_does_not_block_network_and_uses_detached_metadata(harness, monkeypatch):
    _, host, body = private_library(harness)
    ref = TrackRef(body["bridge_id"], body["entries"][0]["track_id"])
    harness.runtime.engine.state.metadata[ref] = Metadata(title="Old title")
    started, resume = threading.Event(), threading.Event()
    original = management.search_response

    def paused(*args, **kwargs):
        started.set()
        assert resume.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(management, "search_response", paused)
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(
            harness.client.get, "/api/host/library/search?q=Old", headers=harness.cookie(host)
        )
        assert started.wait(5)
        try:
            assert harness.client.get("/healthz").status_code == 200
            assert (
                harness.client.get(
                    "/api/host/library/search", headers=harness.cookie(host)
                ).status_code
                == 429
            )
            assert (
                harness.client.put(
                    "/api/host/metadata",
                    json={
                        "bridge_id": ref.bridge_id,
                        "track_id": ref.track_id,
                        "metadata": {"title": "New title"},
                    },
                    headers={"origin": ORIGIN, **harness.cookie(host)},
                ).status_code
                == 200
            )
        finally:
            resume.set()
        assert pending.result(5).json()["tracks"][0]["title"] == "Old title"
    assert not harness.app.state.obs.library_search_busy
    assert (
        harness.client.get("/api/host/library/search?q=New", headers=harness.cookie(host)).json()[
            "total"
        ]
        == 1
    )


def test_search_rechecks_revoked_cookie_after_worker(harness, monkeypatch):
    pid, host, _ = private_library(harness)
    original = management.search_response

    def revoke(*args, **kwargs):
        response = original(*args, **kwargs)
        harness.runtime.sessions.revoke((pid,))
        return response

    monkeypatch.setattr(management, "search_response", revoke)
    response = harness.client.get("/api/host/library/search", headers=harness.cookie(host))
    assert response.status_code == 401
    assert "tracks" not in response.json()


def test_published_metadata_example_validates_and_disables_future_pool(harness):
    path = Path(__file__).resolve().parents[3] / "docs/media-and-metadata.md"
    example = re.search(r"```json\n(.*?)\n```", path.read_text(encoding="utf-8"), re.S)
    assert example is not None
    doc = MetadataDocument.model_validate_json(example[1])
    assert doc.rows[0].enabled is False
    _, host, body = private_library(harness)
    harness.runtime.engine.state.game.settings.sources = [(body["bridge_id"], "")]
    ref = TrackRef(body["bridge_id"], body["entries"][0]["track_id"])
    assert ref in selection.pool(harness.runtime.engine.state)
    row = doc.rows[0].model_dump()
    row.update(bridge_id=body["bridge_id"], relpath=body["entries"][0]["relpath"])
    response = harness.client.post(
        "/api/host/metadata/import",
        json={"version": 2, "rows": [row]},
        headers={"origin": ORIGIN, **harness.cookie(host)},
    )
    assert response.json() == {"accepted": 1, "issues": []}
    result = harness.client.get(
        "/api/host/library/search?activation=disabled", headers=harness.cookie(host)
    ).json()
    assert result["total"] == 1
    assert result["tracks"][0]["enabled"] is False
    assert ref not in selection.pool(harness.runtime.engine.state)


def test_search_constructs_models_only_for_the_requested_page(harness, monkeypatch):
    _, host, _ = private_library(harness)
    build = Mock(wraps=management.LibraryTrack)
    monkeypatch.setattr(management, "LibraryTrack", build)
    result = harness.client.get(
        "/api/host/library/search?limit=2&offset=2", headers=harness.cookie(host)
    ).json()
    assert result["total"] == 6
    assert len(result["tracks"]) == 2
    assert build.call_count == 2
