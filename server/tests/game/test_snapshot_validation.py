"""Reject malformed recovery candidates before they can replace valid state and cookies."""

import copy
import json

import pytest
from builders import Scenario

from openblindysir_protocol.enums import Role, RoundState, ScoreKind
from openblindysir_server.auth.sessions import SessionRegistry
from openblindysir_server.game.state import Metadata, ThemeFilterData, TrackRef
from openblindysir_server.persistence import SnapshotStore


def damage(payload, kind):
    state = payload["state"]
    game = state["game"]["fields"]
    if kind == "index":
        game["current_index"] = 999
    elif kind == "negative_index":
        game["current_index"] = -1
    elif kind == "bool_index":
        game["current_index"] = True
    elif kind == "phase":
        game["phase"] = "IN_GAME"
    elif kind == "rounds":
        game["rounds"] = ["invalid"]
    elif kind == "settings":
        game["settings"]["fields"]["clip_seconds"] = "20"
    elif kind == "theme_bounds":
        game["settings"]["fields"]["selection_filter"]["fields"]["year_min"] = 99999
    elif kind == "theme_control":
        game["settings"]["fields"]["selection_filter"]["fields"]["query"] = "bad\u0000query"
    elif kind == "queue":
        game["queue"] = []
    elif kind == "role":
        state["players"]["map"][0][1]["fields"]["role"] = "host"
    elif kind == "surrogate":
        state["players"]["map"][0][1]["fields"]["nickname"] = "\ud800"
    elif kind == "players":
        state["players"] = []
    elif kind == "missing_players":
        del state["players"]
    elif kind == "clock":
        payload["at"]["mono_ms"] = "0"
    elif kind == "session":
        payload["sessions"][0]["idle_ms"] = "0"
    elif kind == "recovery":
        payload["recovery"] = []
    elif kind == "journal":
        payload["events"]["items"][0]["fields"]["id"] = 999
    elif kind == "frozen":
        payload["frozen"] = "invalid"
    elif kind == "envelope":
        payload["unrecognized"] = "invalid"
    elif kind == "legacy_metadata":
        payload["format"] = 1
        state["metadata"] = {
            "map": [
                [
                    game["rounds"][0]["fields"]["slot"]["fields"]["track_ref"],
                    {"container": "tuple", "items": []},
                ]
            ]
        }
    else:
        pytest.fail(f"unknown synthetic case: {kind}")


@pytest.mark.parametrize(
    "kind",
    [
        "index",
        "negative_index",
        "bool_index",
        "phase",
        "rounds",
        "settings",
        "theme_bounds",
        "theme_control",
        "queue",
        "role",
        "surrogate",
        "players",
        "missing_players",
        "clock",
        "session",
        "recovery",
        "journal",
        "frozen",
        "envelope",
        "legacy_metadata",
    ],
)
def test_corrupt_primary_uses_valid_backup_with_scores_and_cookie(tmp_path, kind):
    scenario = Scenario()
    scenario.to_open()
    player = scenario.player_ids[0]
    scenario.s.journal.append(
        game_id=scenario.s.game.game_id,
        player_id=player,
        delta=2,
        kind=ScoreKind.FINAL_ADJUSTMENT,
        by=scenario.host_id,
        at_wall_ms=scenario.clock.now().wall_ms,
    )
    sessions = SessionRegistry(60000)
    token = sessions.issue(player, scenario.clock.now().mono_ms)
    store = SnapshotStore(tmp_path, ("synthetic",))
    for _ in range(2):
        store.save(scenario.engine, sessions, scenario.clock.now())
    target = tmp_path / "session.json"
    payload = json.loads(target.read_bytes())
    damage(payload, kind)
    target.write_text(json.dumps(payload), encoding="utf-8")
    restored = Scenario(players=(), host=None)
    restored_sessions = SessionRegistry(60000)
    assert store.restore(restored.engine, restored_sessions, scenario.clock.now())
    assert restored_sessions.resolve(token, scenario.clock.now().mono_ms) == player
    assert restored.s.journal.score(restored.s.game.game_id, player) == 2
    assert restored.s.game.rounds[0].state is RoundState.REVIEW
    assert restored.s.game.rounds[0].recovery_interrupted


def test_no_valid_candidate_does_not_partially_apply_the_game(tmp_path):
    scenario = Scenario()
    scenario.to_open()
    store = SnapshotStore(tmp_path, ("synthetic",))
    store.save(scenario.engine, SessionRegistry(60000), scenario.clock.now())
    target = tmp_path / "session.json"
    payload = json.loads(target.read_bytes())
    damage(payload, "clock")
    target.write_text(json.dumps(payload), encoding="utf-8")
    restored = Scenario(players=(), host=None)
    previous = copy.deepcopy(restored.s.game)
    with pytest.raises(ValueError, match="no valid"):
        store.restore(restored.engine, SessionRegistry(60000), scenario.clock.now())
    assert restored.s.game == previous
    assert not restored.s.players
    assert not restored.s.journal.events()


def test_duplicate_snapshot_field_falls_back_instead_of_changing_a_role(tmp_path):
    scenario = Scenario()
    store = SnapshotStore(tmp_path, ("synthetic",))
    for _ in range(2):
        store.save(scenario.engine, SessionRegistry(60000), scenario.clock.now())
    target = tmp_path / "session.json"
    original = target.read_text(encoding="utf-8")
    target.write_text(
        original.replace(
            '"role":{"enum":"Role","value":"player"}',
            '"role":{"enum":"Role","value":"player"},"role":{"enum":"Role","value":"host"}',
            1,
        ),
        encoding="utf-8",
    )
    assert target.read_text(encoding="utf-8") != original
    restored = Scenario(players=(), host=None)
    assert store.restore(restored.engine, SessionRegistry(60000), scenario.clock.now())
    assert restored.s.players[scenario.player_ids[0]].role is Role.PLAYER


def test_format_8_migrates_with_an_empty_theme_and_preserves_cookie(tmp_path):
    scenario = Scenario()
    sessions = SessionRegistry(60000)
    player = scenario.player_ids[0]
    token = sessions.issue(player, scenario.clock.now().mono_ms)
    store = SnapshotStore(tmp_path, ("synthetic",))
    store.save(scenario.engine, sessions, scenario.clock.now())
    target = tmp_path / "session.json"
    payload = json.loads(target.read_bytes())
    payload["format"] = 8
    del payload["state"]["game"]["fields"]["settings"]["fields"]["selection_filter"]
    target.write_text(json.dumps(payload), encoding="utf-8")
    restored = Scenario(players=(), host=None)
    restored_sessions = SessionRegistry(60000)
    assert store.restore(restored.engine, restored_sessions, scenario.clock.now())
    assert restored_sessions.resolve(token, scenario.clock.now().mono_ms) == player
    assert restored.s.game.settings.selection_filter == ThemeFilterData()
    assert restored.s.players.keys() == scenario.s.players.keys()


def test_theme_and_structured_metadata_survive_a_snapshot(tmp_path):
    scenario = Scenario()
    ref = next(
        TrackRef(bid, tid) for bid, cat in scenario.s.catalogs.items() for tid in cat.entries
    )
    scenario.s.game.settings.selection_filter = ThemeFilterData(
        query="Wakfu", genres=["Rap"], languages=["fr"], year_min=2012, year_max=2012
    )
    scenario.s.imported_metadata[ref] = Metadata(
        title="Wakfu", genres=["Rap"], languages=["fr"], year=2012
    )
    store = SnapshotStore(tmp_path, ("synthetic",))
    store.save(scenario.engine, SessionRegistry(60000), scenario.clock.now())
    restored = Scenario(players=(), host=None)
    assert store.restore(restored.engine, SessionRegistry(60000), scenario.clock.now())
    assert restored.s.game.settings.selection_filter == scenario.s.game.settings.selection_filter
    assert restored.s.imported_metadata == scenario.s.imported_metadata
