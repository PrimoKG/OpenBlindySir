"""Shared invitations preserve identity only after host approval; cookies resume directly."""

import random
from pathlib import Path

import pytest
from conftest import ORIGIN, Harness, settings_for_test
from fastapi.testclient import TestClient

from openblindysir_protocol.enums import Role
from openblindysir_server.auth import access_routes
from openblindysir_server.game import FakeClock, SequentialIds
from openblindysir_server.main import create_app


def access(h: Harness, token: str) -> dict:
    result = h.client.get("/api/host/session/access", headers=h.cookie(token))
    assert result.status_code == 200
    return result.json()


def request_join(h: Harness, nickname: str, **credentials: str):
    h.client.cookies.clear()
    result = h.client.post(
        "/api/session/access",
        json={"nickname": nickname, **credentials},
        headers={"origin": ORIGIN},
    )
    h.client.cookies.clear()
    return result


def test_qr_needs_no_password_and_rotation_preserves_existing_cookies(harness: Harness):
    host, host_token = harness.join("Host")
    harness.elevate(host_token)
    invitation = access(harness, host_token)
    assert harness.client.get("/api/host/session/access").status_code == 401
    joined = request_join(harness, "New Player", invitation=invitation["invitation"])
    assert joined.status_code == 200
    token = joined.cookies["openblindysir_dev"]
    pid = joined.json()["player_id"]
    assert joined.json()["role"] == "player"
    assert (
        harness.client.get("/api/host/session/access", headers=harness.cookie(token)).status_code
        == 403
    )
    shared = harness.client.get("/api/session/access-code", headers=harness.cookie(token)).json()
    assert shared["code"] == invitation["code"]
    rotated = harness.client.post(
        "/api/host/session/access",
        json={"code": "NEWCODE2"},
        headers={"origin": ORIGIN, **harness.cookie(host_token)},
    )
    assert rotated.status_code == 200
    for credentials in ({"code": invitation["code"]}, {"invitation": invitation["invitation"]}):
        assert request_join(harness, "Someone else", **credentials).status_code == 401
    resumed = harness.client.get("/api/session", headers=harness.cookie(token))
    assert resumed.status_code == 200
    assert resumed.json()["player_id"] == pid
    assert request_join(harness, "Another Player", code="NEWCODE2").status_code == 200
    assert harness.runtime.engine.state.players[host].role.value == "host"


def test_existing_nickname_requires_approval_and_revokes_old_browser(harness: Harness):
    _, host_token = harness.join("Host")
    harness.elevate(host_token)
    pid, old_token = harness.join("Alice")
    code = access(harness, host_token)["code"]
    waiting = request_join(harness, "alice", code=code)
    assert waiting.status_code == 202
    claim = waiting.json()
    poll = {"request_id": claim["request_id"], "token": claim["token"]}
    assert (
        harness.client.post(
            "/api/session/access/poll", json=poll, headers={"origin": ORIGIN}
        ).status_code
        == 202
    )
    assert (
        harness.client.post(
            "/api/session/access/poll", json={**poll, "token": "wrong"}, headers={"origin": ORIGIN}
        ).status_code
        == 401
    )
    decision = {"request_id": claim["request_id"], "approve": True}
    assert (
        harness.client.post(
            "/api/host/session/access/decide",
            json=decision,
            headers={"origin": ORIGIN, **harness.cookie(old_token)},
        ).status_code
        == 403
    )
    assert (
        harness.client.post(
            "/api/host/session/access/decide",
            json=decision,
            headers={"origin": ORIGIN, **harness.cookie(host_token)},
        ).status_code
        == 200
    )
    response = harness.client.post(
        "/api/session/access/poll", json=poll, headers={"origin": ORIGIN}
    )
    harness.client.cookies.clear()
    assert response.status_code == 200
    assert response.json()["player_id"] == pid
    assert response.json()["role"] == "player"
    assert harness.client.get("/api/session", headers=harness.cookie(old_token)).status_code == 401
    assert (
        harness.client.post(
            "/api/session/access/poll", json=poll, headers={"origin": ORIGIN}
        ).status_code
        == 401
    )
    assert len(harness.runtime.engine.state.players) == 2


def test_refused_expired_and_rotated_claims_cannot_resume(harness: Harness):
    _, token = harness.join("Host")
    harness.elevate(token)
    harness.join("Alice")
    for action in ("refuse", "expire", "rotate"):
        code = access(harness, token)["code"]
        waiting = request_join(harness, "Alice", code=code).json()
        payload = {"request_id": waiting["request_id"], "token": waiting["token"]}
        if action == "refuse":
            assert (
                harness.client.post(
                    "/api/host/session/access/decide",
                    json={"request_id": payload["request_id"], "approve": False},
                    headers={"origin": ORIGIN, **harness.cookie(token)},
                ).status_code
                == 200
            )
        elif action == "expire":
            harness.clock.advance(120001)
        else:
            assert (
                harness.client.post(
                    "/api/host/session/access",
                    json={},
                    headers={"origin": ORIGIN, **harness.cookie(token)},
                ).status_code
                == 200
            )
        assert (
            harness.client.post(
                "/api/session/access/poll", json=payload, headers={"origin": ORIGIN}
            ).status_code
            == 401
        )


def test_shared_access_persists_encrypted_and_old_cookie_resumes(tmp_path: Path):
    settings = settings_for_test(state_dir=tmp_path / "state")
    clock = FakeClock()
    app = create_app(
        settings, clock=clock, ids=SequentialIds(), rng=random.Random(1), background_tasks=False
    )
    with TestClient(app, base_url=ORIGIN) as client:
        h = Harness(client, clock)
        _, token = h.join("Host")
        h.elevate(token)
        details = access(h, token)
    snapshot = (settings.state_dir / "session.json").read_text()
    assert details["code"] not in snapshot
    assert details["invitation"] not in snapshot
    with TestClient(
        create_app(settings, clock=clock, background_tasks=False), base_url=ORIGIN
    ) as client:
        h = Harness(client, clock)
        assert access(h, token) == details
        assert request_join(h, "Alice", invitation=details["invitation"]).status_code == 200


@pytest.mark.parametrize("path", ["/api/host/session/access", "/api/host/session/access/decide"])
@pytest.mark.parametrize("caller", ["anonymous", "player", "host_wrong_origin"])
def test_access_mutations_reject_before_reading_body(harness: Harness, monkeypatch, path, caller):
    _, host_token = harness.join("Host")
    harness.elevate(host_token)
    _, player_token = harness.join("Alice")
    headers = {"origin": ORIGIN}
    if caller == "player":
        headers.update(harness.cookie(player_token))
    elif caller == "host_wrong_origin":
        headers.update(harness.cookie(host_token))
        headers["origin"] = "https://untrusted.example"

    async def forbidden_read(request):
        raise AssertionError("Unauthorized caller reached the request body")

    monkeypatch.setattr(access_routes, "read_json_body", forbidden_read)
    response = harness.client.post(path, json={}, headers=headers)
    assert response.status_code == (401 if caller == "anonymous" else 403)


@pytest.mark.parametrize("path", ["/api/host/session/access", "/api/host/session/access/decide"])
def test_access_mutations_recheck_host_after_await(harness: Harness, monkeypatch, path):
    pid, token = harness.join("Host")
    harness.elevate(token)
    target, _ = harness.join("Alice")
    details = access(harness, token)
    sessions = harness.runtime.sessions.access
    claim_id, _ = sessions.claim(target, harness.clock.now().mono_ms, "synthetic-requester")
    reader = access_routes.read_json_body

    async def revoke_during_read(request):
        result = await reader(request)
        harness.runtime.engine.state.players[pid].role = Role.PLAYER
        return result

    monkeypatch.setattr(access_routes, "read_json_body", revoke_during_read)
    response = harness.client.post(
        path,
        json={"code": "NEWCODE2"}
        if path.endswith("access")
        else {"request_id": claim_id, "approve": True},
        headers={"origin": ORIGIN, **harness.cookie(token)},
    )
    assert response.status_code == 403
    assert harness.runtime.sessions.access.code == details["code"]
    assert not sessions.claims[claim_id].approved
