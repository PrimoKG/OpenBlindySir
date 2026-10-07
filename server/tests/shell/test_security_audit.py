"""Security regressions: revocation during awaits, floods and private HTTP responses."""

import asyncio
import gzip
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from unittest.mock import AsyncMock, Mock

import pytest
from conftest import BRIDGE_ID, HOST, ORIGIN, SECRET, Harness, bridge_hello, catalog, put_catalog
from fastapi import Request
from starlette.responses import Response
from starlette.websockets import WebSocketDisconnect, WebSocketState
from test_library_v02 import private_library

from openblindysir_protocol.bridge import BridgePing
from openblindysir_protocol.enums import BrowserFamily, Role
from openblindysir_protocol.version import PROTOCOL_VERSION
from openblindysir_server import security
from openblindysir_server.auth import routes as auth
from openblindysir_server.library import management
from openblindysir_server.library import routes as library
from openblindysir_server.logging import RedactingFilter, _format_value
from openblindysir_server.ratelimit import ConnectionCounter, SlidingWindowLimiter, TokenBucket
from openblindysir_server.ws import bridge_endpoint
from openblindysir_server.ws.bridge_link import ActiveBridge, BridgeLink
from openblindysir_server.ws.hub import PlayerConnection


def drain(ws: object) -> None:
    while True:
        ws.receive_json()


def test_transient_redaction_registry_is_bounded_but_keeps_deployment_secrets() -> None:
    redaction = RedactingFilter(["synthetic-deployment-secret"])
    for i in range(10000):
        redaction.add_secret(f"synthetic-token-{i:05}")
    assert len(redaction._secrets) <= 4096
    assert redaction._clean("synthetic-deployment-secret synthetic-token-09999") == "*** ***"


@pytest.mark.parametrize("value", ["field\nforged", "field\x1b[2J", "field\u202eforged"])
def test_untrusted_error_locations_cannot_inject_lines_or_terminal_controls(value) -> None:
    rendered = _format_value(value)
    assert json.loads(rendered) == value
    assert not any(ch in rendered for ch in ("\n", "\x1b", "\u202e"))


def test_slow_catalog_upload_cannot_allocate_a_second_body_and_preserves_retry_token(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    started, release = threading.Event(), threading.Event()
    body = catalog()
    original = library._read_gzip
    calls = 0

    async def slow(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await asyncio.to_thread(release.wait, 3)
        return await original(request)

    monkeypatch.setattr(library, "_read_gzip", slow)
    with harness.bridge_ws() as bridge:
        bridge.send_text(bridge_hello(body["catalog_hash"], 6))
        first_token = bridge.receive_json()["catalog_upload_token"]
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(put_catalog, harness, body, first_token)
            try:
                assert started.wait(2)
                second_token = harness.runtime.bridge.issue_catalog_token(
                    BRIDGE_ID, harness.clock.now().mono_ms
                )
                assert put_catalog(harness, body, second_token).status_code == 429
                assert calls == 1
            finally:
                release.set()
            assert pending.result(timeout=3).status_code == 204
        assert put_catalog(harness, body, second_token).status_code == 204
        assert not harness.runtime.bridge._catalog_uploads


def test_catalog_slots_are_global_and_released_even_when_the_body_fails() -> None:
    link = BridgeLink()

    def overloaded():
        with ExitStack() as stack:
            for i in range(8):
                assert stack.enter_context(link.catalog_upload(str(i)))
            assert not stack.enter_context(link.catalog_upload("new"))
            assert not stack.enter_context(link.catalog_upload("0"))
            raise ValueError("synthetic body failure")

    with pytest.raises(ValueError, match="synthetic"):
        overloaded()
    assert not link._catalog_uploads


def test_rate_limits_do_not_retain_rejected_or_expired_addresses() -> None:
    limiter = SlidingWindowLimiter(2, 4)
    for i in range(4):
        assert limiter.allow(str(i), 0)
    for i in range(10000):
        assert limiter.blocked(f"blocked-{i}", 1)
    assert len(limiter._per_key) == 4
    assert limiter.allow("fresh", 60000)
    assert set(limiter._per_key) == {"fresh"}


def test_connection_counter_does_not_retain_closed_or_refused_addresses() -> None:
    counter = ConnectionCounter(1)
    for i in range(10000):
        assert counter.acquire(str(i))
        assert not counter.acquire(str(i))
        counter.release(str(i))
        counter.release(str(i))
    assert not counter._open
    refused = ConnectionCounter(0)
    assert not refused.acquire("refused")
    assert not refused._open


@pytest.mark.parametrize("path", ["/api/session", "/api/host/library/search", "/api/host/metadata"])
def test_private_api_responses_are_never_cached(harness: Harness, path: str) -> None:
    _, token, _ = private_library(harness)
    for headers in (harness.cookie(token), {}):
        response = harness.client.get(path, headers=headers)
        assert response.headers.get("cache-control") == "no-store, private"
        harness.client.cookies.clear()


def test_recovery_code_rotation_is_bounded_and_keeps_last_code(harness: Harness) -> None:
    pid, token = harness.join("Player")
    headers = {"origin": ORIGIN, **harness.cookie(token)}
    codes = []
    for _ in range(5):
        response = harness.client.post("/api/session/recovery-code", headers=headers)
        assert response.status_code == 200
        codes.append(response.json()["code"])
    assert harness.client.post("/api/session/recovery-code", headers=headers).status_code == 429
    assert harness.runtime.sessions.recover(codes[-1]) == pid
    harness.clock.advance(60000)
    assert harness.client.post("/api/session/recovery-code", headers=headers).status_code == 200


@pytest.mark.parametrize("action", ["host", "leave"])
def test_revoked_session_cannot_mutate_after_body_read(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    pid, token = harness.join("Player")
    original = auth.read_json_body

    async def revoke(request: Request) -> object:
        body = await original(request)
        harness.runtime.sessions.revoke((pid,))
        return body

    monkeypatch.setattr(auth, "read_json_body", revoke)
    response = harness.client.post(
        f"/api/session/{action}",
        json={"host_password": HOST} if action == "host" else {},
        headers={"origin": ORIGIN, **harness.cookie(token)},
    )
    assert response.status_code == 401
    assert harness.runtime.engine.player_exists(pid)
    assert harness.runtime.engine.state.players[pid].role is Role.PLAYER


@pytest.mark.parametrize("action", ["sources", "import", "edit"])
def test_library_mutation_rechecks_host_after_body_read(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    pid, token, body = private_library(harness)
    original = management.read_json_body

    async def demote(request: Request, **kwargs: object) -> object:
        raw = await original(request, **kwargs)
        harness.runtime.engine.state.players[pid].role = Role.PLAYER
        return raw

    monkeypatch.setattr(management, "read_json_body", demote)
    requests = {
        "sources": ("POST", "/api/host/library/sources", {"bridge_id": BRIDGE_ID, "folders": [""]}),
        "import": ("POST", "/api/host/metadata/import", {"version": 1, "rows": []}),
        "edit": (
            "PUT",
            "/api/host/metadata",
            {"bridge_id": BRIDGE_ID, "track_id": body["entries"][0]["track_id"], "metadata": {}},
        ),
    }
    method, path, payload = requests[action]
    response = harness.client.request(
        method, path, json=payload, headers={"origin": ORIGIN, **harness.cookie(token)}
    )
    assert response.status_code == 403
    assert not harness.runtime.engine.state.metadata


@pytest.mark.parametrize("suffix", ["truncated", "trailing", "member"])
def test_catalog_requires_one_complete_gzip_stream(suffix: str) -> None:
    data = gzip.compress(b"{}")
    data = (
        data[:-8]
        if suffix == "truncated"
        else data + (b"unexpected" if suffix == "trailing" else gzip.compress(b"{}"))
    )

    async def receive() -> dict:
        return {"type": "http.request", "body": data, "more_body": False}

    async def run() -> None:
        request = Request({"type": "http"}, receive)
        with pytest.raises(ValueError, match="gzip"):
            await library._read_gzip(request)

    asyncio.run(run())


def test_slow_json_body_has_a_wall_time_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "BODY_TIMEOUT_S", 0.01, raising=False)

    async def receive() -> dict:
        await asyncio.Event().wait()
        return {}

    async def run() -> None:
        request = Request(
            {"type": "http", "headers": [(b"content-type", b"application/json")]}, receive
        )
        response = await asyncio.wait_for(security.read_json_body(request), 0.5)
        assert response.status_code == 408

    asyncio.run(run())


def test_bridge_outbound_flood_closes_without_sending_stale_messages() -> None:
    async def run() -> None:
        ws = Mock(application_state=WebSocketState.CONNECTED)
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()
        bridge = ActiveBridge(BRIDGE_ID, "PC", ws, 0)
        for i in range(10000):
            bridge.push(BridgePing(t="PING", c=i))
        assert bridge.close_code == 1013
        assert not bridge.outbox
        await bridge.writer()
        ws.send_text.assert_not_called()
        ws.close.assert_awaited_once()

    asyncio.run(run())


def test_slow_player_cannot_grow_critical_messages_indefinitely() -> None:
    async def run() -> None:
        ws = Mock(application_state=WebSocketState.CONNECTED)
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()
        conn = PlayerConnection(
            1, "p_synthetic", ws, "example", BrowserFamily.OTHER, 0, TokenBucket(40, 20, 0)
        )
        conn.push_state("synthetic old state")
        for _ in range(10000):
            conn.push_critical("synthetic acknowledgement")
        assert conn.close_code == 1013
        assert not conn.critical
        assert conn.pending_state is None
        await conn.writer()
        ws.send_text.assert_not_called()
        ws.close.assert_awaited_once()

    asyncio.run(run())


def test_bridge_inbound_flood_is_stopped_before_more_messages_are_parsed(harness: Harness) -> None:
    async def run() -> None:
        ws = Mock()
        ws.receive_text = AsyncMock(return_value="invalid-synthetic-json")
        bridge = ActiveBridge(BRIDGE_ID, "PC", ws, 0)
        from openblindysir_server.auth.bridges import secret_hash  # noqa: PLC0415

        harness.runtime.credentials.authorize(BRIDGE_ID, SECRET, bind=True)
        bridge.credential_hash = secret_hash(SECRET)
        harness.runtime.bridge.activate(bridge)
        await asyncio.wait_for(bridge_endpoint._read_loop(harness.app.state.obs, bridge), 0.5)
        assert bridge.close_code == 1008
        assert ws.receive_text.await_count == 41

    asyncio.run(run())


@pytest.mark.parametrize("action", ["join", "host"])
def test_pending_login_rechecks_limit_after_other_requests_finish(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    pid, token = harness.join("Player")
    limiter = (
        harness.app.state.obs.join_limiter
        if action == "join"
        else harness.app.state.obs.host_limiter
    )
    original = auth.read_json_body

    async def fill(request: Request):
        body = await original(request)
        for _ in range(limiter.limit):
            limiter.record(auth.client_ip(request), harness.clock.now().mono_ms)
        return body

    monkeypatch.setattr(auth, "read_json_body", fill)
    headers = {"origin": ORIGIN}
    if action == "host":
        headers.update(harness.cookie(token))
    payload = (
        {"password": "example-wrong", "nickname": "Second"}
        if action == "join"
        else {"host_password": "example-wrong"}
    )
    response = harness.client.post(f"/api/session/{action}", json=payload, headers=headers)
    assert response.status_code == 429
    assert len(limiter._global) == limiter.limit
    assert harness.runtime.engine.state.players[pid].role is Role.PLAYER


def test_revoked_cookie_cannot_register_after_delayed_hello(harness: Harness) -> None:
    pid, token = harness.join("Player")
    with harness.player_ws(token) as ws:
        harness.runtime.sessions.revoke((pid,))
        ws.send_text(
            json.dumps({"t": "HELLO", "client_version": "0.3.0", "protocol": PROTOCOL_VERSION})
        )
        with pytest.raises(WebSocketDisconnect):
            drain(ws)
    assert harness.runtime.hub.current(pid) is None


@pytest.mark.parametrize("channel", ["player", "bridge"])
def test_binary_hello_is_rejected_cleanly(harness: Harness, channel: str) -> None:
    _, token = harness.join("Player")
    connection = harness.player_ws(token) if channel == "player" else harness.bridge_ws()
    with connection as ws:
        ws.send_bytes(b"untrusted")
        with pytest.raises(WebSocketDisconnect):
            drain(ws)


@pytest.mark.parametrize(
    ("declared", "status"),
    [("\xb2", 400), ("", 400), ("-1", 400), ("2.0", 400), ("9" * 5000, 413), ("129", 413)],
)
def test_untrusted_body_length_is_rejected_without_integer_conversion_or_receiving(
    declared, status
):
    receive = AsyncMock()
    request = Request(
        {
            "type": "http",
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", declared.encode("latin-1")),
            ],
        },
        receive,
    )
    result = asyncio.run(security.read_json_body(request, limit=128))
    assert isinstance(result, Response)
    assert result.status_code == status
    receive.assert_not_awaited()


def test_long_zero_padded_body_length_still_accepts_a_small_bounded_body():
    receive = AsyncMock(return_value={"type": "http.request", "body": b"{}", "more_body": False})
    request = Request(
        {"type": "http", "headers": [(b"content-length", b"0" * 5000 + b"2")]}, receive
    )
    assert asyncio.run(security.read_bounded_body(request, 128, timeout_s=1)) == b"{}"


def test_successful_join_leave_churn_is_limited_before_more_bodies_are_read(harness: Harness):
    for _ in range(60):
        _, token = harness.join("Synthetic churn")
        response = harness.client.post(
            "/api/session/leave", json={}, headers={"origin": ORIGIN, **harness.cookie(token)}
        )
        assert response.status_code == 200
        harness.client.cookies.clear()
    response = harness.client.post(
        "/api/session/join", content=b"invalid", headers={"origin": ORIGIN}
    )
    assert response.status_code == 429
    assert len(harness.runtime.engine.state.players) == 60
    harness.clock.advance(60000)
    harness.join("Synthetic after window")


def test_finish_game_rejects_deep_json_without_server_error(harness: Harness):
    _, token, _ = private_library(harness)
    before = harness.runtime.engine.state.game.game_id
    response = harness.client.post(
        "/api/host/game/finish",
        content="[" * 1200 + "0" + "]" * 1200,
        headers={"origin": ORIGIN, "content-type": "application/json", **harness.cookie(token)},
    )
    assert response.status_code == 400
    assert harness.runtime.engine.state.game.game_id == before
    assert harness.runtime.engine.state.game.phase.value == "LOBBY"


@pytest.mark.parametrize("origin", [ORIGIN, "https://untrusted.example"])
def test_finish_game_does_not_read_unauthorized_body(harness: Harness, monkeypatch, origin):
    async def forbidden(*args, **kwargs):
        raise AssertionError("unauthorized body must not be read")

    monkeypatch.setattr(management, "read_json_body", forbidden)
    response = harness.client.post(
        "/api/host/game/finish",
        content="{}",
        headers={"origin": origin, "content-type": "application/json"},
    )
    assert response.status_code == 401
