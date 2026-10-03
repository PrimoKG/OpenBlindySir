"""Track selection (spec §6.9)."""

from builders import BRIDGE_ID, CATALOG_HASH, Scenario

from openblindysir_protocol.catalog_rules import compute_track_id
from openblindysir_protocol.enums import RoundState
from openblindysir_server.game import commands as c
from openblindysir_server.game.selection import matches
from openblindysir_server.game.state import CatalogEntryData


def test_prefix_matches_whole_segments() -> None:
    assert matches("Anime/OST/a.flac", "Anime")
    assert matches("Anime/OST/a.flac", "Anime/OST")
    assert not matches("Animes/a.flac", "Anime")
    assert matches("anything.flac", "")


def test_no_repeat_within_a_session() -> None:
    sc = Scenario(rounds=4, tracks=4)
    tracks = []
    for _ in range(4):
        r = sc.to_open()
        tracks.append(r.slot.track_ref)
        sc.on_round("close")
    assert len(set(tracks)) == 4


def test_pool_exhausted_keeps_round_queued_and_warns() -> None:
    sc = Scenario(rounds=3, tracks=1)
    sc.to_open()
    sc.on_round("close")
    sc.on_round("next")
    r = sc.current()
    assert r.state is RoundState.QUEUED
    assert "pool_exhausted" in sc.host_view().host.warnings  # type: ignore[union-attr]
    sc.on_phase("configure", {"allow_repeats": True})
    assert r.state in (RoundState.PREPARING, RoundState.LOADING)


def test_selected_folders_restrict_the_pool() -> None:
    sc = Scenario(rounds=2)
    entries = dict(sc.s.catalogs[BRIDGE_ID].entries)
    rel = "Jeux/zelda.flac"
    entries[compute_track_id(rel)] = CatalogEntryData(rel, "Jeux", ".flac", 1)
    sc.d(c.CatalogLoaded(BRIDGE_ID, "PC", CATALOG_HASH, entries))
    sc.configure(sources=[{"bridge_id": BRIDGE_ID, "folder_prefix": "Jeux"}])
    r = sc.to_open()
    assert r.slot.track_ref is not None
    assert r.slot.track_ref.track_id == compute_track_id(rel)


def test_skipped_track_stays_eligible_for_later_games() -> None:
    sc = Scenario(rounds=1, tracks=2)
    sc.start()
    skipped = sc.current().slot.track_ref
    sc.on_round("skip")
    assert skipped not in sc.s.played


def test_library_tree_has_folders_only() -> None:
    sc = Scenario()
    response = sc.engine.library()
    text = response.model_dump_json()
    assert "track-" not in text
    root = response.bridges[0].root
    assert root.track_count == 12
    assert root.children[0].prefix == "CanaryFolder"
