"""History is host-private, bounded, versioned and deleted from both recovery copies."""

import copy
import json
import random

import pytest
from conftest import ORIGIN, Harness, settings_for_test
from fastapi.testclient import TestClient

from openblindysir_protocol.enums import GamePhase, HostMode
from openblindysir_protocol.views import GameRecord
from openblindysir_server import history as history_routes
from openblindysir_server.game import FakeClock, SequentialIds
from openblindysir_server.game import history as history_rules
from openblindysir_server.game.history import HistoryVersionError, migrate_record, retained
from openblindysir_server.main import create_app, sweep_once
from openblindysir_server.persistence import SnapshotVersionError


def record(now, identity="g_example1"):
    return GameRecord.model_validate(
        {
            "game_id": identity,
            "finished_at": now,
            "players": [],
            "results": {"standings": [], "podium": [], "rounds_played": 0, "final_adjustments": []},
        }
    ).model_dump(mode="json")


def operator(harness):
    pid, token = harness.join("Synthetic operator")
    harness.elevate(token)
    return pid, token, {"origin": ORIGIN, **harness.cookie(token)}


def test_history_authentication_origin_strict_confirmation_and_phase(harness: Harness):
    pid, token, headers = operator(harness)
    _, player = harness.join("Synthetic player")
    harness.runtime.engine.state.archives = [record(harness.clock.now().wall_ms)]
    for path in ("/api/host/history", "/api/host/history/g_example1"):
        assert harness.client.get(path).status_code == 401
        assert harness.client.get(path, headers=harness.cookie(player)).status_code == 403
        response = harness.client.get(path, headers=harness.cookie(token))
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store, private"
        assert (
            harness.client.request(
                "DELETE", path, json={"confirm": True}, headers=harness.cookie(token)
            ).status_code
            == 403
        )
        for body in ({}, {"confirm": False}, {"confirm": "true"}, {"confirm": True, "extra": 1}):
            assert (
                harness.client.request("DELETE", path, json=body, headers=headers).status_code
                == 400
            )
    state = harness.runtime.engine.state
    state.game.phase = GamePhase.IN_GAME
    assert harness.client.get("/api/host/history", headers=headers).status_code == 409
    state.players[pid].host_mode = HostMode.MC
    assert harness.client.get("/api/host/history", headers=headers).status_code == 200
    assert (
        "history"
        not in harness.runtime.engine.view_for(
            harness.runtime.sessions.resolve(player, harness.clock.now().mono_ms)
        ).model_dump()
    )


def test_history_mutation_rechecks_revoked_session_after_stream(harness: Harness, monkeypatch):
    pid, _, headers = operator(harness)
    harness.runtime.engine.state.archives = [record(harness.clock.now().wall_ms)]
    read = history_routes.read_json_body

    async def revoke_during_body(request, limit):
        raw = await read(request, limit)
        harness.runtime.sessions.revoke([pid])
        return raw

    monkeypatch.setattr(history_routes, "read_json_body", revoke_during_body)
    response = harness.client.request(
        "DELETE", "/api/host/history", json={"confirm": True}, headers=headers
    )
    assert response.status_code == 401
    assert len(harness.runtime.engine.state.archives) == 1


def test_durable_deletion_removes_primary_backup_and_survives_restart(tmp_path):
    settings = settings_for_test(state_dir=tmp_path / "state")
    clock = FakeClock()
    app = create_app(
        settings, clock=clock, ids=SequentialIds(), rng=random.Random(1), background_tasks=False
    )
    with TestClient(app, base_url=ORIGIN) as client:
        harness = Harness(client, clock)
        _, token, headers = operator(harness)
        harness.runtime.engine.state.archives = [
            record(clock.now().wall_ms),
            record(clock.now().wall_ms, "g_example2"),
        ]
        harness.runtime.save_snapshot()
        response = client.request(
            "DELETE", "/api/host/history/g_example1", json={"confirm": True}, headers=headers
        )
        assert response.status_code == 200
        for path in settings.state_dir.glob("session*.json"):
            assert "g_example1" not in path.read_text()
            assert "g_example2" in path.read_text()
    restarted = create_app(settings, clock=clock, background_tasks=False)
    with TestClient(restarted, base_url=ORIGIN) as client:
        harness = Harness(client, clock)
        headers = {"origin": ORIGIN, **harness.cookie(token)}
        assert [
            row["game_id"]
            for row in client.get("/api/host/history", headers=headers).json()["items"]
        ] == ["g_example2"]
        assert (
            client.request(
                "DELETE", "/api/host/history", json={"confirm": True}, headers=headers
            ).status_code
            == 200
        )
        assert client.get("/api/host/history", headers=headers).json()["items"] == []
        for path in settings.state_dir.glob("session*.json"):
            assert "g_example2" not in path.read_text()


def test_failed_delete_rolls_back_memory_and_reports_failed_persistence(tmp_path, monkeypatch):
    app = create_app(settings_for_test(state_dir=tmp_path / "state"), background_tasks=False)
    with TestClient(app, base_url=ORIGIN) as client:
        harness = Harness(client, app.state.obs.runtime.clock)
        _, _, headers = operator(harness)
        harness.runtime.engine.state.archives = [record(harness.clock.now().wall_ms)]
        harness.runtime.save_snapshot()
        previous = (tmp_path / "state" / "session.json").read_bytes()

        def disk_full(*args, **kwargs):
            raise OSError("synthetic disk full")

        monkeypatch.setattr(harness.runtime.snapshots, "save", disk_full)
        assert (
            client.request(
                "DELETE", "/api/host/history", json={"confirm": True}, headers=headers
            ).status_code
            == 503
        )
        assert len(harness.runtime.engine.state.archives) == 1
        assert harness.runtime.engine.state.persistence_status == "failed"
        assert (tmp_path / "state" / "session.json").read_bytes() == previous


def test_retention_bounds_count_age_bytes_and_idle_backups(harness: Harness, monkeypatch):
    now = harness.clock.now().wall_ms
    records = [record(now, f"g_example{i:03}") for i in range(55)]
    assert len(retained(records, now)) == 50
    assert retained(records, now)[0]["game_id"] == "g_example005"
    old = record(now - 91 * 86_400_000, "g_expired1")
    assert retained([old, records[-1]], now) == [records[-1]]
    monkeypatch.setattr(history_rules, "MAX_BYTES", history_rules.record_bytes(records[-1]) + 1)
    assert retained(records, now) == [records[-1]]
    harness.runtime.engine.state.archives = [old, records[-1]]
    sweep_once(harness.runtime)
    assert harness.runtime.engine.state.archives == [records[-1]]


def test_history_migration_rejects_extra_fields_unknown_versions_and_duplicates(harness: Harness):
    row = record(harness.clock.now().wall_ms)
    old = {
        key: value
        for key, value in row.items()
        if key not in {"version", "settings", "started_at", "sources"}
    }
    assert migrate_record(old)["version"] == 3
    assert migrate_record({**old, "version": 1})["sources"] == []
    with pytest.raises(HistoryVersionError):
        migrate_record({**old, "version": 500})
    with pytest.raises(ValueError, match="extra_forbidden"):
        migrate_record({**row, "audio": "forbidden"})
    with pytest.raises(ValueError, match="duplicate"):
        retained([row, copy.deepcopy(row)], harness.clock.now().wall_ms)


@pytest.mark.parametrize("legacy_format", [1, 2, 3, 9])
def test_old_snapshot_history_and_cookie_migrate(tmp_path, legacy_format):
    settings = settings_for_test(state_dir=tmp_path / "state")
    clock = FakeClock()
    app = create_app(settings, clock=clock, ids=SequentialIds(), background_tasks=False)
    with TestClient(app, base_url=ORIGIN) as client:
        harness = Harness(client, clock)
        _, token, _ = operator(harness)
        row = record(clock.now().wall_ms)
        if legacy_format == 9:
            row["version"] = 2
            row["results"].pop("unreviewed_answers", None)
        else:
            row.pop("version")
        harness.runtime.engine.state.archives = [row]
        harness.runtime.save_snapshot()
    path = settings.state_dir / "session.json"
    payload = json.loads(path.read_text())
    payload["format"] = legacy_format
    if legacy_format < 4:
        payload["auth"] = harness.runtime.snapshots.legacy_fingerprint
    path.write_text(json.dumps(payload), encoding="utf-8")
    restored = create_app(settings, clock=clock, background_tasks=False)
    with TestClient(restored, base_url=ORIGIN) as client:
        response = client.get("/api/host/history", headers=harness.cookie(token))
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1
        assert restored.state.obs.runtime.engine.state.archives[0]["version"] == 3
        if legacy_format == 9:
            detail = client.get("/api/host/history/g_example1", headers=harness.cookie(token))
            assert detail.status_code == 200
            assert detail.json()["results"]["unreviewed_answers"] is None


@pytest.mark.parametrize("unknown_history", [False, True])
def test_unknown_versions_never_silently_restore_previous_published_state(
    tmp_path, unknown_history
):
    settings = settings_for_test(state_dir=tmp_path / "state")
    app = create_app(settings, background_tasks=False)
    with TestClient(app, base_url=ORIGIN):
        runtime = app.state.obs.runtime
        runtime.engine.state.archives = [record(runtime.clock.now().wall_ms)]
        runtime.save_snapshot()
        runtime.save_snapshot()
    path = settings.state_dir / "session.json"
    payload = json.loads(path.read_text())
    if unknown_history:
        payload["state"]["archives"][0]["map"].append(["version", 99])
    else:
        payload["format"] = 99
    path.write_text(json.dumps(payload), encoding="utf-8")
    expected = HistoryVersionError if unknown_history else SnapshotVersionError
    with pytest.raises(expected):
        create_app(settings, background_tasks=False)


def test_corrupt_primary_uses_valid_backup_but_does_not_invent_an_empty_history(tmp_path):
    settings = settings_for_test(state_dir=tmp_path / "state")
    app = create_app(settings, background_tasks=False)
    with TestClient(app, base_url=ORIGIN):
        runtime = app.state.obs.runtime
        runtime.engine.state.archives = [record(runtime.clock.now().wall_ms)]
        runtime.save_snapshot()
        runtime.save_snapshot()
    (settings.state_dir / "session.json").write_text("{broken", encoding="utf-8")
    restored = create_app(settings, background_tasks=False)
    assert len(restored.state.obs.runtime.engine.state.archives) == 1
    (settings.state_dir / "session.previous.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="no valid"):
        create_app(settings, background_tasks=False)
