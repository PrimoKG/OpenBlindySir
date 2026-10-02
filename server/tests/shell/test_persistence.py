"""Restart the actual application shell with its saved session and cookies."""

import random
from pathlib import Path

import pytest
from conftest import ORIGIN, Harness, settings_for_test
from fastapi.testclient import TestClient

from openblindysir_server.game import FakeClock, SequentialIds
from openblindysir_server.main import create_app


def test_restart_preserves_host_cookie_and_configuration(tmp_path: Path) -> None:
    settings = settings_for_test(state_dir=tmp_path / "state")
    clock = FakeClock()
    app = create_app(
        settings, clock=clock, ids=SequentialIds(), rng=random.Random(1), background_tasks=False
    )
    with TestClient(app, base_url=ORIGIN) as client:
        harness = Harness(client, clock)
        player_id, token = harness.join("ExampleHost")
        harness.elevate(token)
        epoch = harness.runtime.engine.state.epoch
        with harness.player_ws(token) as ws:
            ws.send_json({"t": "HELLO", "protocol": 2, "client_version": "example"})
            ws.receive_json()
            ws.send_json(
                {
                    "t": "HOST",
                    "cmd": "configure",
                    "expected_phase": "LOBBY",
                    "args": {"instructions": "Example saved instructions", "rounds": 7},
                }
            )
            while harness.runtime.engine.state.game.settings.rounds != 7:
                ws.receive_json()
    restarted = create_app(settings, clock=clock, background_tasks=False)
    with TestClient(restarted, base_url=ORIGIN) as client:
        response = client.get("/api/session", headers={"cookie": f"openblindysir_dev={token}"})
        assert response.status_code == 200
        assert response.json()["player_id"] == player_id
        assert response.json()["role"] == "host"
        assert response.json()["epoch"] == epoch
        runtime = restarted.state.obs.runtime
        assert runtime.engine.state.recovered
        assert runtime.engine.state.game.settings.rounds == 7
        assert runtime.engine.state.game.settings.instructions == "Example saved instructions"
        assert runtime.engine.view_for(player_id).session.persistence_status == "ready"


def test_unwritable_snapshot_does_not_abort_game_and_warns_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(settings_for_test(state_dir=tmp_path / "state"), background_tasks=False)
    with TestClient(app, base_url=ORIGIN) as client:
        harness = Harness(client, app.state.obs.runtime.clock)
        player_id, token = harness.join("ExampleHost")
        harness.elevate(token)

        def fail(*_: object) -> None:
            raise OSError("example disk full")

        monkeypatch.setattr(harness.runtime.snapshots, "save", fail)
        harness.runtime.save_snapshot()
        assert harness.runtime.engine.view_for(player_id).session.persistence_status == "failed"
        assert client.get("/healthz").status_code == 200
