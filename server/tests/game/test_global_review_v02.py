"""Global review, early endings and durable drafts through public engine commands."""

import json
import random
from pathlib import Path

import pytest
from builders import BRIDGE_ID, CATALOG_HASH, Scenario, make_catalog

from openblindysir_protocol.enums import GamePhase, RoundState, ScoreKind
from openblindysir_protocol.errors import ErrorCode
from openblindysir_server.auth.sessions import SessionRegistry
from openblindysir_server.game import GameEngine, Instant, SecretIds, selection
from openblindysir_server.game import commands as c
from openblindysir_server.game.state import Metadata, TrackRef
from openblindysir_server.persistence import SnapshotStore


def test_all_rounds_answers_and_signed_points_stay_private_until_validation() -> None:
    sc = Scenario(rounds=2)
    a, b, spectator = sc.player_ids
    sc.on_phase("participation", {"player_id": spectator, "spectator": True})
    first = sc.to_open()
    sc.advance(1234)
    sc.submit(a, "locked-first")
    sc.draft(b, "captured-first")
    first_answer_wall_ms = sc.clock.now().wall_ms
    sc.on_round("close")
    assert (
        sc.on_round("score_draft", {"player_id": a, "points": 10}).error is ErrorCode.INVALID_STATE
    )
    assert sc.host_view().host.review_rounds == []
    sc.to_open()
    sc.submit(a, "locked-second")
    sc.on_round("close")
    assert sc.s.game.phase is GamePhase.FINAL_SCORE_REVIEW
    assert len(sc.host_view().host.review_rounds) == 2
    reviewed = sc.host_view().host.review_rounds[0]
    locked = next(row for row in reviewed.answers if row.player_id == a)
    captured = next(row for row in reviewed.answers if row.player_id == b)
    assert (locked.status.value, locked.elapsed_ms, locked.order) == ("LOCKED", 1234, 1)
    assert locked.received_at_wall_ms == captured.received_at_wall_ms == first_answer_wall_ms
    assert captured.status.value == "CAPTURED"
    assert captured.order is None
    assert spectator not in [row.player_id for row in reviewed.answers]
    assert (
        sc.host("score_draft", round_id=first.id, args={"player_id": a, "points": -2}).error is None
    )
    sc.score({a: 5, b: 0})
    assert sc.s.journal.events() == ()
    totals = {row.player_id: row.score_after for row in sc.host_view().host.final_review}
    assert totals[a] == 3
    for pid in (a, b, spectator):
        view = sc.view(pid)
        assert view.standings == []
        assert view.team_standings == []
        assert "locked-first" not in view.model_dump_json()
    sc.finalize()
    assert sc.s.journal.score(sc.s.game.game_id, a) == 3
    assert len(sc.s.journal.events()) == 2
    assert sc.s.journal.is_frozen(sc.s.game.game_id)


@pytest.mark.parametrize(
    "stage",
    [
        "LOBBY",
        "QUEUED",
        "PREPARING",
        "LOADING",
        "COUNTDOWN",
        "OPEN",
        "PAUSED",
        "REVIEW",
        "FINAL_SCORE_REVIEW",
        "FINAL_RESULTS",
    ],
)
def test_end_game_in_every_phase_is_safe_and_preserves_data(stage: str) -> None:
    sc = Scenario(rounds=3, tracks=1 if stage == "QUEUED" else 12)
    if stage == "PREPARING":
        sc.auto_serve = False
        sc.start()
    elif stage in {"LOADING", "COUNTDOWN"}:
        sc.start()
        if stage == "COUNTDOWN":
            sc.ready()
    elif stage != "LOBBY":
        sc.to_open()
        sc.submit(sc.player_ids[0], "kept")
        sc.draft(sc.player_ids[1], "unfinished")
        if stage == "PAUSED":
            sc.on_round("pause")
        if stage in {"QUEUED", "REVIEW", "FINAL_SCORE_REVIEW", "FINAL_RESULTS"}:
            sc.on_round("close")
        if stage == "QUEUED":
            sc.on_round("next")
            assert sc.current().state is RoundState.QUEUED
        if stage in {"FINAL_SCORE_REVIEW", "FINAL_RESULTS"}:
            sc.on_phase("end_game", {"current_round": "score"})
            sc.score({sc.player_ids[0]: -4})
        if stage == "FINAL_RESULTS":
            sc.finalize()
    assert sc.on_phase("end_game", {"current_round": "score"}).error is None
    expected = GamePhase.FINAL_RESULTS if stage == "FINAL_RESULTS" else GamePhase.FINAL_SCORE_REVIEW
    assert sc.s.game.phase is expected
    assert sc.host_view().play is None
    assert not sc.s.game.pipeline
    before = sc.host_view().model_dump_json()
    assert sc.on_phase("end_game", {"current_round": "abandon"}).error is None
    assert sc.host_view().model_dump_json() == before
    played = [r for r in sc.s.game.rounds if r.official_start_at is not None]
    if stage in {"LOBBY", "PREPARING", "LOADING", "COUNTDOWN"}:
        assert played == []
    else:
        assert any(
            r.answers.get(sc.player_ids[0]) and r.answers[sc.player_ids[0]].text == "kept"
            for r in played
        )


def test_abandoned_played_round_keeps_answers_but_cannot_receive_points() -> None:
    sc = Scenario()
    r = sc.to_open()
    sc.submit(sc.player_ids[0], "kept")
    sc.draft(sc.player_ids[1], "captured")
    sc.on_phase("end_game", {"current_round": "abandon"})
    reviewed = sc.host_view().host.review_rounds[0]
    assert reviewed.round_id == r.id
    assert not reviewed.included
    assert reviewed.answers[0].status.value in {"LOCKED", "CAPTURED", "NONE"}
    assert (
        sc.on_round("score_draft", {"player_id": sc.player_ids[0], "points": 1}).error
        is ErrorCode.INVALID_STATE
    )
    sc.finalize()
    history = sc.view(sc.player_ids[0]).final_results.recap
    assert (
        next(row for row in history if row.player_id == sc.player_ids[0]).history[0].included
        is False
    )
    assert sc.s.journal.events() == ()


def test_removed_player_and_rescanned_track_retain_their_review_identity() -> None:
    sc = Scenario(rounds=1)
    r = sc.to_open()
    pid = sc.player_ids[0]
    sc.submit(pid, "kept")
    sc.on_phase("kick", {"player_id": pid})
    sc.d(c.CatalogLoaded(BRIDGE_ID, "Renamed", CATALOG_HASH, {}))
    sc.on_round("close")
    assert next(p for p in sc.host_view().players if p.id == pid).nickname == "Ayoub"
    assert sc.host_view().host.review_rounds[0].track.folder.startswith("PC/")
    sc.score({pid: 3})
    sc.finalize()
    assert sc.s.journal.score(sc.s.game.game_id, pid) == 3
    assert r.track_entry is not None


def test_join_lock_blocks_new_names_but_keeps_existing_reconnection() -> None:
    sc = Scenario()
    assert sc.on_phase("join_lock", {"locked": True}).error is None
    assert sc.d(c.Join("new")).error is ErrorCode.JOIN_LOCKED
    assert sc.d(c.Disconnected(sc.player_ids[0])).error is None
    assert sc.d(c.Connected(sc.player_ids[0], "example")).error is None
    sc.on_phase("end_session")
    assert not sc.s.joins_locked
    assert sc.d(c.Join("new")).error is None


def test_balancing_rotates_folders_and_overlaps_never_duplicate_tracks() -> None:
    sc = Scenario()
    entries = make_catalog(20, "Large") | make_catalog(3, "Small")
    sc.d(c.CatalogLoaded(BRIDGE_ID, "PC", CATALOG_HASH, entries))
    sc.configure(
        balance_folders=True,
        sources=[
            {"bridge_id": BRIDGE_ID, "folder_prefix": ""},
            {"bridge_id": BRIDGE_ID, "folder_prefix": "Small"},
        ],
    )
    queue = list(selection.build_queue(sc.s, include_played=False))
    assert len(queue) == len(set(queue)) == 23
    folders = [entries[ref.track_id].folder for ref in queue[:6]]
    assert folders.count("Small") == folders.count("Large") == 3


def test_global_drafts_metadata_sources_and_recovery_hashes_survive_snapshot(
    tmp_path: Path,
) -> None:
    sc = Scenario(rounds=1)
    r = sc.to_review()
    sc.score({sc.player_ids[0]: -3})
    sc.on_phase("final_set", {"player_id": sc.player_ids[0], "delta": 2})
    sc.s.imported_metadata[r.slot.track_ref] = Metadata(title="Imported", album="Album", year=2026)
    sc.s.metadata[r.slot.track_ref] = Metadata(artist="Manual")
    sessions = SessionRegistry(3600000)
    code = sessions.recovery_code(sc.player_ids[0])
    store = SnapshotStore(tmp_path, ("example",))
    store.save(sc.engine, sessions, sc.clock.now())
    assert code not in (tmp_path / "session.json").read_text(encoding="utf-8")
    now = Instant(10, sc.clock.now().wall_ms + 100)
    engine = GameEngine(sc.s.config, ids=SecretIds(), rng=random.Random(2), started_at=now)
    restored = SessionRegistry(3600000)
    assert store.restore(engine, restored, now)
    view = engine.view_for(sc.host_id)
    assert view.host.final_review[1].score_after == -1
    assert view.host.review_rounds[0].track.album == "Album"
    assert view.host.review_rounds[0].track.artist == "Manual"
    assert restored.recover(code) == sc.player_ids[0]


def test_v1_snapshot_moves_publications_to_drafts_without_double_count(tmp_path: Path) -> None:
    sc = Scenario(rounds=2)
    r = sc.to_review()
    pid = sc.player_ids[0]
    sc.s.journal.append(
        game_id=sc.s.game.game_id,
        player_id=pid,
        delta=3,
        kind=ScoreKind.ROUND,
        round_id=r.id,
        by=sc.host_id,
        at_wall_ms=sc.clock.now().wall_ms,
    )
    r.state = RoundState.REVEALED
    ref = r.slot.track_ref
    sc.s.metadata[ref] = ("Legacy", "Artist")
    store = SnapshotStore(tmp_path, ("example",))
    store.save(sc.engine, SessionRegistry(10000), sc.clock.now())
    path = tmp_path / "session.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["format"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    now = Instant(10, sc.clock.now().wall_ms)
    engine = GameEngine(sc.s.config, ids=SecretIds(), rng=random.Random(1), started_at=now)
    assert store.restore(engine, SessionRegistry(10000), now)
    assert engine.state.journal.score(sc.s.game.game_id, pid) == 0
    assert engine.state.game.rounds[0].score_draft[pid] == 3
    assert engine.state.metadata[TrackRef(ref.bridge_id, ref.track_id)].title == "Legacy"


def test_metadata_correction_updates_repeated_rounds_and_acknowledges_empty_fallback() -> None:
    sc = Scenario(rounds=2, tracks=1)
    sc.configure(allow_repeats=True)
    first = sc.to_review()
    second = sc.to_open()
    sc.on_round("close")
    assert first.slot.track_ref == second.slot.track_ref
    assert sc.on_round("track_metadata", {"title": "Corrected", "album": "Album"}).error is None
    assert all(r.reveal.title == "Corrected" for r in (first, second))
    assert all(r.metadata_revision == 1 for r in (first, second))
    assert sc.on_round("track_metadata", {"title": None, "album": None}).error is None
    assert all(r.metadata_revision == 2 for r in (first, second))
    assert all(r.reveal.title != "Corrected" for r in (first, second))


def test_imported_title_is_preserved_and_clearing_manual_fields_restores_clean_tags() -> None:
    sc = Scenario(rounds=1)
    r = sc.to_review()
    sc.s.imported_metadata[r.slot.track_ref] = Metadata(title="A Title (Audio)")
    assert sc.host_view().host.review_rounds[0].track.title == "A Title (Audio)"
    sc.s.imported_metadata.clear()
    sc.s.assets[r.slot.asset_id].title = "Tag title (Official Video)"
    assert sc.on_round("track_metadata", {"title": None, "artist": None}).error is None
    assert sc.host_view().host.review_rounds[0].track.title == "Tag title"
