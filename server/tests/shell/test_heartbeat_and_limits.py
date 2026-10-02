"""Heartbeat with a controllable clock (spec §7.4) and login rate limits (spec §12)."""

import json

from conftest import BLIND, HOST, ORIGIN, Harness
from starlette.websockets import WebSocketDisconnect

from openblindysir_server.main import OFFLINE_AFTER_MS, sweep_once

HELLO = json.dumps({"t": "HELLO", "client_version": "0.1.0", "protocol": 2})


def receive_until(ws: object, t: str) -> dict[str, object]:
    for _ in range(20):
        msg = ws.receive_json()  # type: ignore[attr-defined]
        if msg["t"] == t:
            return msg
    raise AssertionError(f"no {t} message")


def sweep(h: Harness) -> list[str]:
    """Run the sweeper inside the app's event loop, as the background task does."""
    return h.client.portal.call(sweep_once, h.runtime)  # type: ignore[union-attr]


def close_code(ws: object) -> int:
    try:
        for _ in range(20):
            ws.receive_text()  # type: ignore[attr-defined]
    except WebSocketDisconnect as exc:
        return exc.code
    raise AssertionError("socket not closed")


def wait_online(ws: object, pid: str, *, online: bool) -> None:
    for _ in range(10):
        view = receive_until(ws, "STATE")["view"]
        assert isinstance(view, dict)
        if next(p for p in view["players"] if p["id"] == pid)["online"] is online:
            return
    raise AssertionError("presence never broadcast")


def connection(h: Harness, pid: str) -> str:
    return h.runtime.engine.state.players[pid].connection.value


# --- heartbeat -----------------------------------------------------------------------------


def test_regular_pings_keep_the_player_online(harness: Harness) -> None:
    pid, token = harness.join("Fidele")
    with harness.player_ws(token) as ws:
        ws.send_text(HELLO)
        receive_until(ws, "STATE")
        for _ in range(6):  # 60 s of play with a PING every 10 s
            harness.clock.advance(10_000)
            ws.send_text(json.dumps({"t": "PING", "c": 1.0}))
            receive_until(ws, "PONG")
            assert sweep(harness) == []
        assert connection(harness, pid) == "ONLINE"


def test_missing_heartbeat_goes_offline_then_reconnects_online(harness: Harness) -> None:
    pid, token = harness.join("Tunnel")
    _, other_token = harness.join("Temoin")
    with harness.player_ws(other_token) as witness:
        witness.send_text(HELLO)
        receive_until(witness, "STATE")
        with harness.player_ws(token) as ws:
            ws.send_text(HELLO)
            receive_until(ws, "STATE")
            wait_online(witness, pid, online=True)
            harness.clock.advance(OFFLINE_AFTER_MS - 1_000)
            witness.send_text(json.dumps({"t": "PING", "c": 1.0}))
            receive_until(witness, "PONG")
            assert sweep(harness) == []  # not yet silent long enough
            harness.clock.advance(2_000)
            witness.send_text(json.dumps({"t": "PING", "c": 1.0}))
            receive_until(witness, "PONG")
            assert sweep(harness) == [pid]  # only the silent one
            assert close_code(ws) == 1001
        assert connection(harness, pid) == "OFFLINE"
        wait_online(witness, pid, online=False)  # the others see it OFFLINE
        with harness.player_ws(token) as again:  # same session cookie, same identity
            again.send_text(HELLO)
            view = receive_until(again, "STATE")["view"]
            assert isinstance(view, dict)
            assert view["me"]["player_id"] == pid
            assert connection(harness, pid) == "ONLINE"


# --- login rate limits ---------------------------------------------------------------------


def _join(h: Harness, password: str, nickname: str) -> int:
    body = {"password": password, "nickname": nickname}
    return h.client.post("/api/session/join", json=body, headers={"origin": ORIGIN}).status_code


def _elevate(h: Harness, token: str, password: str) -> int:
    response = h.client.post(
        "/api/session/host",
        json={"host_password": password},
        headers={"origin": ORIGIN, **h.cookie(token)},
    )
    h.client.cookies.clear()
    return response.status_code


def test_failed_joins_are_limited_then_a_success_passes_after_the_window(
    harness: Harness,
) -> None:
    assert [_join(harness, "example-wrong", "X") for _ in range(5)] == [401] * 5
    assert _join(harness, "example-wrong", "X") == 429
    assert _join(harness, BLIND, "Ami") == 429  # the whole IP waits while limited
    harness.clock.advance(60_001)
    assert _join(harness, BLIND, "Ami") == 200
    harness.client.cookies.clear()


def test_successes_do_not_count_towards_the_limit(harness: Harness) -> None:
    for index in range(4):
        assert _join(harness, "example-wrong", "X") == 401
        harness.join(f"Ami{index}")  # interleaved successes never trigger a block
    assert _join(harness, "example-wrong", "X") == 401  # 5th failure still answered
    assert _join(harness, "example-wrong", "X") == 429


def test_host_password_limit_is_separate(harness: Harness) -> None:
    _, token = harness.join("Yo")
    assert [_elevate(harness, token, "example-wrong") for _ in range(3)] == [401] * 3
    assert _elevate(harness, token, HOST) == 429
    assert _join(harness, BLIND, "Invite") == 200  # joining is not affected
    harness.client.cookies.clear()
    harness.clock.advance(60_001)
    assert _elevate(harness, token, HOST) == 200
