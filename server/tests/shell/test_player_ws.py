"""Player WebSocket (spec §8.2): HELLO, STATE, PONG, strict messages, supersede, permissions."""

import json

import pytest
from conftest import ORIGIN, Harness
from starlette.websockets import WebSocketDisconnect

from openblindysir_protocol.version import PROTOCOL_VERSION

HELLO = json.dumps({"t": "HELLO", "client_version": "0.1.0", "protocol": PROTOCOL_VERSION})


def receive_until(ws: object, t: str) -> dict[str, object]:
    for _ in range(20):
        msg = ws.receive_json()  # type: ignore[attr-defined]
        if msg["t"] == t:
            return msg
    raise AssertionError(f"no {t} message")


def close_code(ws: object) -> int:
    """Read until the server closes the socket; return the close code."""
    try:
        for _ in range(20):
            ws.receive_text()  # type: ignore[attr-defined]
    except WebSocketDisconnect as exc:
        return exc.code
    raise AssertionError("socket not closed")


def test_hello_then_full_state(harness: Harness) -> None:
    _, token = harness.join("Ayoub")
    with harness.player_ws(token) as ws:
        ws.send_text(HELLO)
        state = receive_until(ws, "STATE")
        assert state["v"] == 1
        view = state["view"]
        assert isinstance(view, dict)
        assert view["kind"] == "player"
        assert view["phase"] == "LOBBY"


def test_ping_pong_echoes_client_time(harness: Harness) -> None:
    _, token = harness.join("A")
    with harness.player_ws(token) as ws:
        ws.send_text(HELLO)
        receive_until(ws, "STATE")
        ws.send_text(json.dumps({"t": "PING", "c": 1234.5}))
        pong = receive_until(ws, "PONG")
        assert pong["c"] == 1234.5
        assert isinstance(pong["s"], float)


def test_answer_submit_with_timestamp_is_invalid(harness: Harness) -> None:
    _, token = harness.join("A")
    with harness.player_ws(token) as ws:
        ws.send_text(HELLO)
        receive_until(ws, "STATE")
        ws.send_text(
            json.dumps({"t": "ANSWER_SUBMIT", "round_id": "r_000001", "text": "x", "ts": 1})
        )
        assert receive_until(ws, "ERROR")["code"] == "invalid_message"


def test_host_command_from_player_refused(harness: Harness) -> None:
    _, token = harness.join("A")
    with harness.player_ws(token) as ws:
        ws.send_text(HELLO)
        receive_until(ws, "STATE")
        ws.send_text(
            json.dumps({"t": "HOST", "cmd": "start_game", "expected_phase": "LOBBY", "args": {}})
        )
        assert receive_until(ws, "ERROR")["code"] == "not_host"


def test_protocol_mismatch(harness: Harness) -> None:
    _, token = harness.join("A")
    with harness.player_ws(token) as ws:
        ws.send_text(json.dumps({"t": "HELLO", "client_version": "0.1.0", "protocol": 99}))
        assert receive_until(ws, "ERROR")["code"] == "protocol_mismatch"


def test_first_message_must_be_hello(harness: Harness) -> None:
    _, token = harness.join("A")
    with harness.player_ws(token) as ws:
        ws.send_text(json.dumps({"t": "PING", "c": 1}))
        assert receive_until(ws, "ERROR")["code"] == "hello_required"


def test_refused_without_cookie_or_origin(harness: Harness) -> None:
    _, token = harness.join("A")
    with (
        pytest.raises(WebSocketDisconnect),
        harness.client.websocket_connect("/api/ws", headers={"origin": ORIGIN}) as ws,
    ):
        ws.receive_text()
    with (
        pytest.raises(WebSocketDisconnect),
        harness.client.websocket_connect(
            "/api/ws", headers={"origin": "https://evil.example", **harness.cookie(token)}
        ) as ws,
    ):
        ws.receive_text()


def test_second_tab_supersedes_first(harness: Harness) -> None:
    _, token = harness.join("A")
    with harness.player_ws(token) as first:
        first.send_text(HELLO)
        receive_until(first, "STATE")
        with harness.player_ws(token) as second:
            second.send_text(HELLO)
            receive_until(second, "STATE")
            assert close_code(first) == 4001


def test_too_large_message_closes(harness: Harness) -> None:
    _, token = harness.join("A")
    with harness.player_ws(token) as ws:
        ws.send_text(HELLO)
        receive_until(ws, "STATE")
        ws.send_text("x" * 17_000)
        assert receive_until(ws, "ERROR")["code"] == "message_too_large"


def test_kick_closes_with_4003(harness: Harness) -> None:
    _, host_token = harness.join("Yo")
    harness.elevate(host_token)
    target, token = harness.join("Fantome")
    with harness.player_ws(token) as victim, harness.player_ws(host_token) as host:
        victim.send_text(HELLO)
        receive_until(victim, "STATE")
        host.send_text(HELLO)
        receive_until(host, "STATE")
        host.send_text(
            json.dumps(
                {
                    "t": "HOST",
                    "cmd": "kick",
                    "expected_phase": "LOBBY",
                    "args": {"player_id": target},
                }
            )
        )
        assert close_code(victim) == 4003
    assert harness.client.get("/api/session", headers=harness.cookie(token)).status_code == 401


def test_silent_connection_is_swept_offline(harness: Harness) -> None:
    from openblindysir_server.main import sweep_once  # noqa: PLC0415

    pid, token = harness.join("Silencieux")
    with harness.player_ws(token) as ws:
        ws.send_text(HELLO)
        receive_until(ws, "STATE")
        harness.clock.advance(21_000)
        assert sweep_once(harness.runtime) == [pid]
        assert close_code(ws) == 1001
    state = harness.runtime.engine.state.players[pid].connection.value
    assert state == "OFFLINE"
