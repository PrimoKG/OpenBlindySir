"""Bridge link (spec §8.3, §5.3): authentication, WELCOME, catalogue, PREPARE, uploads."""

import gzip
import hashlib
import json

import pytest
from conftest import FAKE_M4A, SECRET, Harness, bridge_hello, catalog, put_asset, put_catalog
from starlette.websockets import WebSocketDisconnect

HELLO = json.dumps({"t": "HELLO", "client_version": "0.1.0", "protocol": 1})


def receive(ws: object, t: str) -> dict[str, object]:
    for _ in range(30):
        msg = ws.receive_json()  # type: ignore[attr-defined]
        if msg["t"] == t:
            return msg
    raise AssertionError(f"no {t}")


def test_wrong_secret_refused(harness: Harness) -> None:
    with pytest.raises(WebSocketDisconnect), harness.bridge_ws("wrong-secret") as ws:
        ws.receive_text()


def test_welcome_asks_catalog_then_accepts_it(harness: Harness) -> None:
    body = catalog()
    with harness.bridge_ws() as ws:
        ws.send_text(bridge_hello(body["catalog_hash"], len(body["entries"])))
        welcome = receive(ws, "WELCOME")
        assert welcome["catalog_needed"] is True
        token = welcome["catalog_upload_token"]
        assert isinstance(token, str)
        assert put_catalog(harness, body, "wrong-token").status_code == 403
        assert put_catalog(harness, body, token).status_code == 204
        assert put_catalog(harness, body, token).status_code == 403  # one-shot
    library = harness.runtime.engine.library()
    assert library.bridges[0].track_count == 6


def test_catalog_with_forged_track_id_rejected(harness: Harness) -> None:
    body = catalog()
    body["entries"][0]["track_id"] = "t_0000000000000000"
    with harness.bridge_ws() as ws:
        ws.send_text(bridge_hello(body["catalog_hash"], 6))
        token = receive(ws, "WELCOME")["catalog_upload_token"]
        assert put_catalog(harness, body, str(token)).status_code == 400


def test_gzip_bomb_refused(harness: Harness) -> None:
    body = catalog()
    with harness.bridge_ws() as ws:
        ws.send_text(bridge_hello(body["catalog_hash"], 6))
        token = str(receive(ws, "WELCOME")["catalog_upload_token"])
        bomb = gzip.compress(b"[" + b" " * (40 * 1024 * 1024) + b"]")
        response = harness.client.put(
            "/api/bridge/catalog",
            content=bomb,
            headers={
                "authorization": f"Bearer {SECRET}",
                "x-catalog-token": token,
                "content-encoding": "gzip",
                "content-type": "application/json",
            },
        )
        assert response.status_code == 413


def _host_and_players(harness: Harness) -> tuple[str, list[str]]:
    _, host_token = harness.join("Yo")
    harness.elevate(host_token)
    tokens = [harness.join(name)[1] for name in ("Ayoub", "Mehdi")]
    return host_token, tokens


def test_full_round_through_bridge_upload_and_audio(harness: Harness) -> None:
    body = catalog()
    host_token, tokens = _host_and_players(harness)
    with harness.bridge_ws() as bridge:
        bridge.send_text(bridge_hello(body["catalog_hash"], 6))
        token = str(receive(bridge, "WELCOME")["catalog_upload_token"])
        assert put_catalog(harness, body, token).status_code == 204
        with harness.player_ws(host_token) as host:
            host.send_text(HELLO)
            receive(host, "STATE")
            host.send_text(
                json.dumps(
                    {
                        "t": "HOST",
                        "cmd": "configure",
                        "expected_phase": "LOBBY",
                        "args": {
                            "rounds": 2,
                            "sources": [{"bridge_id": body["bridge_id"], "folder_prefix": ""}],
                        },
                    }
                )
            )
            host.send_text(
                json.dumps(
                    {"t": "HOST", "cmd": "start_game", "expected_phase": "LOBBY", "args": {}}
                )
            )
            prepare = receive(bridge, "PREPARE")
            assert "path" not in prepare
            upload_url = str(prepare["upload_url"])
            upload_token = str(prepare["upload_token"])
            assert put_asset(harness, upload_url, "bad-token").status_code == 403
            # The bad token consumed nothing; the real one still works once.
            assert (
                put_asset(harness, upload_url, upload_token, data=b"not audio").status_code == 400
            )
            prepare = receive(bridge, "PREPARE")  # same track retried once (invalid upload)
            upload_url, upload_token = str(prepare["upload_url"]), str(prepare["upload_token"])
            assert put_asset(harness, upload_url, upload_token).status_code == 204
            asset_id = upload_url.rsplit("/", 1)[-1]
            player_cookie = harness.cookie(tokens[0])
            assert (
                harness.client.get(f"/api/audio/{asset_id}", headers=player_cookie).status_code
                == 404
            )
            bridge.send_text(
                json.dumps(
                    {
                        "t": "JOB_DONE",
                        "job_id": prepare["job_id"],
                        "actual_start": 30.0,
                        "clip_duration": 20.0,
                        "track_duration": 200.0,
                        "bytes": len(FAKE_M4A),
                        "sha256": hashlib.sha256(FAKE_M4A).hexdigest(),
                    }
                )
            )
            for _ in range(50):
                response = harness.client.get(f"/api/audio/{asset_id}", headers=player_cookie)
                if response.status_code == 200:
                    break
            assert response.status_code == 200
            assert response.content == FAKE_M4A
            assert response.headers["cache-control"] == "no-store, private"
            assert "content-disposition" not in response.headers
            state = receive(host, "STATE")
            assert state["view"]["phase"] == "IN_GAME"  # type: ignore[index]
    assert harness.runtime.engine.state.bridges[body["bridge_id"]].state.value == "OFFLINE"
