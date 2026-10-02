"""Session routes, Origin checks, rate limits and security headers (spec §8.1, §12)."""

import random

from conftest import BLIND, ORIGIN, Harness, settings_for_test
from fastapi.testclient import TestClient

from openblindysir_server.game import FakeClock, SequentialIds
from openblindysir_server.main import create_app


def test_join_sets_httponly_strict_cookie(harness: Harness) -> None:
    response = harness.client.post(
        "/api/session/join",
        json={"password": BLIND, "nickname": "Ayoub"},
        headers={"origin": ORIGIN},
    )
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert response.json()["nickname"] == "Ayoub"


def test_wrong_password(harness: Harness) -> None:
    response = harness.client.post(
        "/api/session/join", json={"password": "nope", "nickname": "A"}, headers={"origin": ORIGIN}
    )
    assert response.status_code == 401
    assert response.json() == {"error": "bad_password"}


def test_origin_required(harness: Harness) -> None:
    body = {"password": BLIND, "nickname": "A"}
    assert harness.client.post("/api/session/join", json=body).status_code == 403
    evil = {"origin": "https://evil.example"}
    assert harness.client.post("/api/session/join", json=body, headers=evil).status_code == 403


def test_json_required_and_body_bounded(harness: Harness) -> None:
    headers = {"origin": ORIGIN, "content-type": "text/plain"}
    response = harness.client.post("/api/session/join", content=b"{}", headers=headers)
    assert response.status_code == 415
    big = {"origin": ORIGIN, "content-type": "application/json"}
    assert (
        harness.client.post("/api/session/join", content=b"x" * 5000, headers=big).status_code
        == 413
    )


def test_invalid_body_never_echoed(harness: Harness) -> None:
    response = harness.client.post(
        "/api/session/join",
        json={"password": "secret-value-xyz", "nickname": "A", "extra": 1},
        headers={"origin": ORIGIN},
    )
    assert response.status_code == 400
    assert "secret-value-xyz" not in response.text


def test_join_rate_limited(harness: Harness) -> None:
    body = {"password": "wrong", "nickname": "A"}
    codes = [
        harness.client.post("/api/session/join", json=body, headers={"origin": ORIGIN}).status_code
        for _ in range(6)
    ]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429


def test_successful_joins_from_one_ip_are_not_limited(harness: Harness) -> None:
    for index in range(12):  # friends behind the same home router
        harness.join(f"Ami{index}")


def test_nickname_taken_and_invalid(harness: Harness) -> None:
    harness.join("Ayoub")
    body = {"password": BLIND, "nickname": "AYOUB"}
    response = harness.client.post("/api/session/join", json=body, headers={"origin": ORIGIN})
    assert response.status_code == 409
    assert response.json() == {"error": "nickname_taken"}
    harness.client.cookies.clear()
    body = {"password": BLIND, "nickname": "\u200b"}
    response = harness.client.post("/api/session/join", json=body, headers={"origin": ORIGIN})
    assert response.status_code == 422


def test_whoami_and_host_elevation(harness: Harness) -> None:
    pid, token = harness.join("Yo")
    me = harness.client.get("/api/session", headers=harness.cookie(token))
    assert me.status_code == 200
    assert me.json()["role"] == "player"
    bad = harness.client.post(
        "/api/session/host",
        json={"host_password": BLIND},
        headers={"origin": ORIGIN, **harness.cookie(token)},
    )
    assert bad.status_code == 401
    harness.elevate(token)
    me = harness.client.get("/api/session", headers=harness.cookie(token))
    assert me.json()["role"] == "host"
    assert me.json()["host_mode"] == "player"
    assert pid == me.json()["player_id"]


def test_already_joined(harness: Harness) -> None:
    _, token = harness.join("A")
    response = harness.client.post(
        "/api/session/join",
        json={"password": BLIND, "nickname": "B"},
        headers={"origin": ORIGIN, **harness.cookie(token)},
    )
    assert response.status_code == 409
    assert response.json() == {"error": "already_joined"}


def test_leave_revokes_session(harness: Harness) -> None:
    _, token = harness.join("A")
    response = harness.client.post(
        "/api/session/leave", json={}, headers={"origin": ORIGIN, **harness.cookie(token)}
    )
    assert response.status_code == 200
    assert harness.client.get("/api/session", headers=harness.cookie(token)).status_code == 401


def test_security_headers_on_every_response(harness: Harness) -> None:
    for response in (harness.client.get("/healthz"), harness.client.get("/api/session")):
        csp = response.headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
    assert "access-control-allow-origin" not in harness.client.get("/healthz").headers


def test_healthz(harness: Harness) -> None:
    assert harness.client.get("/healthz").json() == {"status": "ok", "bridge": "OFFLINE"}


def test_production_cookie_is_host_prefixed_and_secure() -> None:
    settings = settings_for_test(dev_mode=False, domain="testserver")
    app = create_app(
        settings,
        clock=FakeClock(),
        ids=SequentialIds(),
        rng=random.Random(0),
        background_tasks=False,
    )
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(
            "/api/session/join",
            json={"password": BLIND, "nickname": "A"},
            headers={"origin": "https://testserver"},
        )
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert cookie.startswith("__Host-openblindysir=")
        assert "Secure" in cookie
        assert "strict-transport-security" in response.headers


def test_audio_not_servable_is_uniform_404(harness: Harness) -> None:
    _, token = harness.join("A")
    response = harness.client.get("/api/audio/a_" + "x" * 22, headers=harness.cookie(token))
    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}
    assert harness.client.get("/api/audio/a_" + "x" * 22).status_code == 401


def test_library_and_diagnostics_host_only(harness: Harness) -> None:
    _, token = harness.join("A")
    assert harness.client.get("/api/host/library", headers=harness.cookie(token)).status_code == 403
    harness.elevate(token)
    assert harness.client.get("/api/host/library", headers=harness.cookie(token)).status_code == 200
    diag = harness.client.get("/api/host/diagnostics", headers=harness.cookie(token))
    assert diag.status_code == 200
    assert diag.json()["protocol"] == 2
