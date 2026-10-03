"""Published history is independent of live names, catalogues and subsequent games."""

import copy
import json

from builders import BRIDGE_ID, CATALOG_HASH, Scenario, make_catalog

from openblindysir_protocol.enums import BridgeState, RoundState
from openblindysir_protocol.errors import ErrorCode
from openblindysir_server.game import commands as c
from openblindysir_server.game import selection
from openblindysir_server.game.assets import BRIDGE_WAIT_MS
from openblindysir_server.game.state import TrackRef

SECOND = "12345678-1234-1234-1234-123456789abd"


def test_bridge_names_and_selected_folders_are_hidden_from_playing_host():
    sc = Scenario(rounds=1)
    sc.d(c.BridgeConnected(BRIDGE_ID, "Private canary bridge", "0.5.0.dev0", CATALOG_HASH, 12))
    sc.configure(sources=[{"bridge_id": BRIDGE_ID, "folder_prefix": "CanaryFolder"}])
    sc.to_open()
    for pid in [sc.host_id, *sc.player_ids]:
        text = sc.view(pid).model_dump_json()
        assert "Private canary bridge" not in text
        assert "CanaryFolder" not in text


def test_final_history_keeps_names_answers_settings_source_and_scores_without_audio():
    sc = Scenario(rounds=1)
    r = sc.to_open()
    pid = sc.player_ids[0]
    sc.advance(1234)
    sc.submit(pid, "Synthetic locked answer")
    sc.on_round("close")
    sc.score({pid: 7})
    sc.finalize()
    saved = copy.deepcopy(sc.s.archives[0])
    assert saved["started_at"] is not None
    assert saved["settings"]["rounds"] == 1
    assert saved["sources"] == [{"bridge_id": BRIDGE_ID, "name": "PC"}]
    assert (
        next(row for row in saved["results"]["recap"] if row["player_id"] == pid)["history"][0][
            "elapsed_ms"
        ]
        == 1234
    )
    assert any(row["score"] == 7 for row in saved["results"]["standings"])
    assert sc.host_view().host.history == []
    assert sc.host_view().host.history_count == 1
    assert (
        sc.host(
            "final_validate", expected_phase="FINAL_SCORE_REVIEW", args={"confirm_unreviewed": True}
        ).error
        is ErrorCode.STALE_COMMAND
    )
    assert len(sc.s.archives) == 1
    sc.on_phase("new_game")
    sc.s.players[pid].nickname = "Changed later"
    sc.s.catalogs.clear()
    sc.s.bridges.clear()
    assert sc.s.archives == [saved]
    assert not sc.s.journal.events()
    assert not sc.s.assets
    serialized = json.dumps(saved)
    assert "Synthetic locked answer" in serialized
    assert r.slot.asset_id not in serialized
    assert "upload_token" not in serialized


def test_same_local_track_ids_are_distinct_and_offline_sources_are_not_new_choices():
    sc = Scenario(auto_serve=False)
    entries = make_catalog(12)
    sc.d(c.BridgeConnected(SECOND, "Other device", "0.5.0.dev0", CATALOG_HASH, 12))
    sc.d(c.CatalogLoaded(SECOND, "Other device", CATALOG_HASH, entries))
    sc.configure(
        sources=[
            {"bridge_id": BRIDGE_ID, "folder_prefix": ""},
            {"bridge_id": SECOND, "folder_prefix": ""},
        ]
    )
    assert len(selection.pool(sc.s)) == 24
    local = next(iter(entries))
    assert TrackRef(BRIDGE_ID, local) != TrackRef(SECOND, local)
    sc.d(c.BridgeDisconnected(BRIDGE_ID))
    assert sc.s.bridges[BRIDGE_ID].state is BridgeState.OFFLINE
    sc.start()
    assert sc.current().slot.track_ref.bridge_id == SECOND
    assert all(job.bridge_id == SECOND for job in sc.pending_jobs)


def test_unprepared_source_waits_briefly_then_uses_another_owner():
    sc = Scenario(rounds=1, auto_serve=False)
    sc.d(c.BridgeConnected(SECOND, "Other device", "0.5.0.dev0", CATALOG_HASH, 12))
    sc.d(c.CatalogLoaded(SECOND, "Other device", CATALOG_HASH, make_catalog(12)))
    sc.configure(
        sources=[
            {"bridge_id": BRIDGE_ID, "folder_prefix": ""},
            {"bridge_id": SECOND, "folder_prefix": ""},
        ]
    )
    sc.start()
    lost = sc.current().slot.track_ref.bridge_id
    survivor = SECOND if lost == BRIDGE_ID else BRIDGE_ID
    sc.d(c.BridgeDisconnected(lost))
    assert sc.current().slot.waiting_bridge
    sc.advance(BRIDGE_WAIT_MS - 1)
    assert sc.current().slot.track_ref.bridge_id == lost
    sc.advance(1)
    assert sc.current().slot.track_ref.bridge_id == survivor
    sc.serve(sc.pending_jobs[-1])
    assert sc.current().state is RoundState.LOADING


def test_all_sources_lost_leaves_actionable_round_then_reconnects_without_new_catalogue():
    sc = Scenario(rounds=1, auto_serve=False)
    sc.start()
    sc.d(c.BridgeDisconnected(BRIDGE_ID))
    sc.advance(BRIDGE_WAIT_MS)
    assert sc.current().slot.track_ref is None
    assert sc.host_view().round.wait_reason == "pool_exhausted"
    sc.d(c.BridgeConnected(BRIDGE_ID, "PC", "0.5.0.dev0", CATALOG_HASH, 12))
    assert sc.current().slot.track_ref.bridge_id == BRIDGE_ID
    sc.serve(sc.pending_jobs[-1])
    assert sc.current().state is RoundState.LOADING


def test_already_prepared_and_open_round_continue_after_owner_disconnects():
    sc = Scenario(rounds=1)
    r = sc.to_open()
    asset = r.slot.asset_id
    sc.d(c.BridgeDisconnected(BRIDGE_ID))
    assert r.state is RoundState.OPEN
    assert r.slot.asset_id == asset
    sc.submit(sc.player_ids[0], "kept after disconnect")
    sc.on_round("close")
    sc.finalize()
    assert sc.s.archives[0]["sources"][0]["name"] == "PC"
