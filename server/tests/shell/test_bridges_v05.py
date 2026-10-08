"""Distinct credentials, revocation and compatibility at actual network boundaries."""

import gzip
import json

import pytest
from conftest import BRIDGE_ID, ORIGIN, SECRET, Harness, bridge_hello, catalog
from starlette.websockets import WebSocketDisconnect

from openblindysir_protocol.version import PROTOCOL_VERSION
from openblindysir_server.auth.bridges import BridgeCredentials
from openblindysir_server.library import routes as catalog_routes

SECOND = "12345678-1234-1234-1234-123456789abd"
SECOND_SECRET = "synthetic-second-bridge-private-0123456789abcdef"


def hello(identity=BRIDGE_ID, protocol=PROTOCOL_VERSION):
    message = json.loads(bridge_hello(catalog()["catalog_hash"], 6))
    return {**message, "bridge_id": identity, "protocol": protocol}


def test_legacy_secret_binds_once_and_cannot_impersonate_another_bridge(harness: Harness):
    with harness.bridge_ws() as first:
        first.send_json(hello())
        assert first.receive_json()["t"] == "WELCOME"
        with harness.bridge_ws() as intruder:
            intruder.send_json(hello(SECOND))
            with pytest.raises(WebSocketDisconnect) as rejected:
                intruder.receive_json()
            assert rejected.value.code == 1008
        assert set(harness.runtime.bridge.connections) == {BRIDGE_ID}
        assert harness.runtime.credentials.active_hash(SECOND) is None


def test_distinct_secret_cannot_spoof_a_connected_bridge_or_upload_its_catalogue(harness: Harness):
    harness.runtime.credentials.replace(SECOND, "Second", SECOND_SECRET)
    with harness.bridge_ws() as first, harness.bridge_ws(SECOND_SECRET) as second:
        first.send_json(hello())
        token = first.receive_json()["catalog_upload_token"]
        second.send_json(hello(SECOND))
        second.receive_json()
        with harness.bridge_ws(SECOND_SECRET) as intruder:
            intruder.send_json(hello())
            with pytest.raises(WebSocketDisconnect):
                intruder.receive_json()
        assert set(harness.runtime.bridge.connections) == {BRIDGE_ID, SECOND}
        response = harness.client.put(
            "/api/bridge/catalog",
            content=gzip.compress(json.dumps(catalog()).encode()),
            headers={
                "authorization": f"Bearer {SECOND_SECRET}",
                "x-bridge-id": BRIDGE_ID,
                "x-catalog-token": token,
                "content-encoding": "gzip",
            },
        )
        assert response.status_code == 401
        assert BRIDGE_ID in harness.runtime.bridge.catalog_grants


def test_revoke_is_host_only_and_drops_only_its_owner(harness: Harness):
    _, host = harness.join("Operator")
    harness.elevate(host)
    _, player = harness.join("Player")
    harness.runtime.credentials.replace(SECOND, "Second", SECOND_SECRET)
    path = f"/api/host/bridges/{BRIDGE_ID}/revoke"
    with harness.bridge_ws() as first, harness.bridge_ws(SECOND_SECRET) as second:
        first.send_json(hello())
        first.receive_json()
        second.send_json(hello(SECOND))
        second.receive_json()
        assert (
            harness.client.post(
                path, json={"confirm": True}, headers={"origin": ORIGIN, **harness.cookie(player)}
            ).status_code
            == 403
        )
        assert (
            harness.client.post(
                path, json={"confirm": True}, headers=harness.cookie(host)
            ).status_code
            == 403
        )
        response = harness.client.post(
            path, json={"confirm": True}, headers={"origin": ORIGIN, **harness.cookie(host)}
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store, private"
        with pytest.raises(WebSocketDisconnect) as closed:
            first.receive_json()
        assert closed.value.code == 1008
        assert set(harness.runtime.bridge.connections) == {SECOND}
        assert not harness.runtime.credentials.recognizes(SECRET)


def test_rotation_is_durable_and_contains_no_raw_credentials(tmp_path):
    path = tmp_path / "bridge-credentials.json"
    first = BridgeCredentials(path, SECRET)
    assert first.authorize(BRIDGE_ID, SECRET, bind=True)
    restarted = BridgeCredentials(path, SECRET)
    assert not restarted.authorize(SECOND, SECRET, bind=True)
    restarted.replace(BRIDGE_ID, "Same device", SECOND_SECRET)
    again = BridgeCredentials(path, SECRET)
    assert again.authorize(BRIDGE_ID, SECOND_SECRET)
    assert not again.authorize(BRIDGE_ID, SECRET)
    assert SECRET not in path.read_text()
    assert SECOND_SECRET not in path.read_text()
    again.revoke(BRIDGE_ID)
    assert not BridgeCredentials(path, SECRET).recognizes(SECOND_SECRET)


@pytest.mark.parametrize("protocol", [0, 3, 4, 5, 10000])
def test_bridge_protocol_mismatch_reports_supported_range(harness: Harness, protocol):
    with harness.bridge_ws() as bridge:
        bridge.send_json(hello(protocol=protocol))
        with pytest.raises(WebSocketDisconnect) as closed:
            bridge.receive_json()
        assert closed.value.code == 1008
        assert closed.value.reason == "protocol_mismatch;required=12..12"
    assert not harness.runtime.bridge.connections
    info = harness.client.get("/api/compatibility").json()
    assert info["protocol_min"] == info["protocol_max"] == 12
    assert info["snapshot_format"] == 9


def test_player_protocol_mismatch_has_actionable_structured_range(harness: Harness):
    _, token = harness.join("Example")
    with harness.player_ws(token) as ws:
        ws.send_json({"t": "HELLO", "client_version": "0.3.0", "protocol": 4})
        error = ws.receive_json()
        assert error["code"] == "protocol_mismatch"
        assert error["compatibility"]["protocol_min"] == 12
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_distinct_credentials_cannot_be_reused_for_another_identity(tmp_path):
    registry = BridgeCredentials(tmp_path / "credentials.json")
    registry.replace(BRIDGE_ID, "First", SECRET)
    with pytest.raises(ValueError, match="distinct"):
        registry.replace(SECOND, "Second", SECRET)


def test_revoked_credential_is_rechecked_after_catalogue_body(harness: Harness, monkeypatch):
    read = catalog_routes._read_gzip

    async def revoke(request):
        data = await read(request)
        harness.runtime.credentials.revoke(BRIDGE_ID)
        return data

    monkeypatch.setattr(catalog_routes, "_read_gzip", revoke)
    with harness.bridge_ws() as bridge:
        bridge.send_json(hello())
        token = bridge.receive_json()["catalog_upload_token"]
        response = harness.client.put(
            "/api/bridge/catalog",
            content=gzip.compress(json.dumps(catalog()).encode()),
            headers={
                "authorization": f"Bearer {SECRET}",
                "x-bridge-id": BRIDGE_ID,
                "x-catalog-token": token,
                "content-encoding": "gzip",
            },
        )
        assert response.status_code == 409
        assert not harness.runtime.engine.state.catalogs


def test_catalogue_limit_covers_all_owners_not_only_each_upload(harness: Harness, monkeypatch):
    monkeypatch.setattr(catalog_routes, "MAX_TOTAL_LIBRARY_TRACKS", 10)
    harness.runtime.credentials.replace(SECOND, "Second", SECOND_SECRET)
    with harness.bridge_ws() as first, harness.bridge_ws(SECOND_SECRET) as second:
        first.send_json(hello())
        a = first.receive_json()["catalog_upload_token"]
        second.send_json(hello(SECOND))
        b = second.receive_json()["catalog_upload_token"]
        for identity, secret, token, expected in [
            (BRIDGE_ID, SECRET, a, 204),
            (SECOND, SECOND_SECRET, b, 413),
        ]:
            body = {**catalog(), "bridge_id": identity}
            response = harness.client.put(
                "/api/bridge/catalog",
                content=gzip.compress(json.dumps(body).encode()),
                headers={
                    "authorization": f"Bearer {secret}",
                    "x-bridge-id": identity,
                    "x-catalog-token": token,
                    "content-encoding": "gzip",
                },
            )
            assert response.status_code == expected
        assert set(harness.runtime.engine.state.catalogs) == {BRIDGE_ID}


def test_bridge_revoke_between_accept_and_hello_fails_closed(harness: Harness):
    harness.runtime.credentials.replace(SECOND, "Second", SECOND_SECRET)
    with harness.bridge_ws(SECOND_SECRET) as bridge:
        harness.runtime.credentials.revoke(SECOND)
        bridge.send_json(hello(SECOND))
        with pytest.raises(WebSocketDisconnect) as closed:
            bridge.receive_json()
        assert closed.value.code == 1008
    assert not harness.runtime.bridge.connections
