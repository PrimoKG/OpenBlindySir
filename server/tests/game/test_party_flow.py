"""Continuous rounds and semantic correction through public engine commands."""

import json
import random
from pathlib import Path

import pytest
from builders import Scenario

from openblindysir_protocol.enums import GamePhase, RoundState, ScoreKind
from openblindysir_protocol.errors import ErrorCode
from openblindysir_server.auth.sessions import SessionRegistry
from openblindysir_server.game import GameEngine, Instant, SecretIds, selection
from openblindysir_server.game import commands as c
from openblindysir_server.persistence import SnapshotStore


def test_auto_advance_runs_without_host_and_never_publishes_answers_or_points() -> None:
    sc = Scenario(rounds=2)
    first = sc.to_open()
    sc.submit(sc.player_ids[0], "private-answer")
    sc.on_round("close")
    assert first.auto_advance_at == sc.clock.now().mono_ms + 2000
    sc.d(c.Disconnected(sc.host_id))
    sc.advance(1999)
    assert sc.current().id == first.id
    sc.advance(1)
    assert sc.current().number == 2
    assert sc.current().id != first.id
    assert sc.s.journal.events() == ()
    view = sc.view(sc.player_ids[1])
    assert view.standings == []
    assert "private-answer" not in view.model_dump_json()


def test_pause_intermission_preserves_remaining_time_and_manual_mode_has_no_timer() -> None:
    sc = Scenario(rounds=2)
    first = sc.to_review()
    sc.advance(500)
    assert sc.on_round("pause").error is None
    sc.advance(10000)
    assert sc.current().id == first.id
    assert sc.on_round("resume").error is None
    sc.advance(1499)
    assert sc.current().id == first.id
    sc.advance(1)
    assert sc.current().number == 2
    other = Scenario(rounds=2)
    other.configure(auto_advance=False)
    other.to_review()
    other.advance(20000)
    assert other.current().number == 1
    assert other.current().auto_advance_at is None
    assert other.on_round("pause").error is None
    paused = other.host_view().paused
    assert paused is not None
    assert paused.remaining_ms == 0


def test_cancel_before_playback_consumes_but_prefetch_does_not() -> None:
    sc = Scenario(rounds=2)
    sc.start()
    original = sc.current().slot.track_ref
    prefetched = {slot.track_ref for slot in sc.s.game.pipeline}
    assert original not in sc.s.played
    assert not prefetched & sc.s.played
    assert sc.on_round("skip").error is None
    assert original in sc.s.played
    assert original in sc.s.consumed_cancelled
    assert original not in selection.build_queue(sc.s, include_played=False)
    assert not prefetched & sc.s.played


@pytest.mark.parametrize("reset", [False, True])
def test_new_game_reset_preserves_metadata_players_teams_history_and_settings(reset: bool) -> None:
    sc = Scenario(rounds=1)
    pid = sc.player_ids[0]
    sc.on_phase("participation", {"player_id": pid, "team": "Example team"})
    round_ = sc.to_review()
    sc.host("track_metadata", round_id=round_.id, args={"title": "Corrected title"})
    sc.finalize()
    consumed = set(sc.s.played)
    metadata = dict(sc.s.metadata)
    archives = list(sc.s.archives)
    settings = sc.s.game.settings.copy()
    assert sc.on_phase("new_game", {"reset_library": reset}).error is None
    assert sc.s.played == (set() if reset else consumed)
    assert sc.s.metadata == metadata
    assert sc.s.archives == archives
    assert sc.s.game.settings == settings
    assert sc.s.players[pid].team == "Example team"
    assert sc.s.game.phase is GamePhase.LOBBY


def judgement(sc: Scenario, **args: object):
    return sc.host(
        "score_draft", round_id=sc.current().id, args={"player_id": sc.player_ids[0], **args}
    )


def test_partial_criteria_are_unreviewed_and_stale_second_host_cannot_overwrite() -> None:
    sc = Scenario(rounds=1)
    assert sc.configure(title_points=2, artist_points=3).error is None
    sc.to_review()
    assert (
        judgement(sc, points=2, judgement="criteria", title_correct=True, expected_revision=0).error
        is None
    )
    row = next(
        row
        for row in sc.host_view().host.review_rounds[0].answers
        if row.player_id == sc.player_ids[0]
    )
    assert not row.reviewed
    assert row.title_correct is True
    assert row.artist_correct is None
    assert row.score_revision == 1
    assert judgement(sc, points=0, expected_revision=0).error is ErrorCode.STALE_COMMAND
    assert (
        judgement(
            sc,
            points=5,
            judgement="criteria",
            title_correct=True,
            artist_correct=True,
            expected_revision=1,
        ).error
        is None
    )
    assert sc.current().score_draft[sc.player_ids[0]] == 5
    assert judgement(sc, points=2, expected_revision=2).error is None
    assert sc.player_ids[0] not in sc.current().judgements
    assert sc.s.journal.events() == ()


@pytest.mark.parametrize(
    ("mode", "field", "points"),
    [
        ("title", "title_correct", 2),
        ("artist", "artist_correct", 3),
        ("custom", "custom_correct", 7),
    ],
)
def test_semantic_scores_use_only_enabled_criteria(mode: str, field: str, points: int) -> None:
    sc = Scenario(rounds=1)
    sc.configure(answer_mode=mode, title_points=2, artist_points=3, custom_points=7)
    sc.to_review()
    assert judgement(sc, points=points, judgement="criteria", **{field: True}).error is None
    assert sc.player_ids[0] in sc.current().score_reviewed
    assert (
        judgement(sc, points=points + 1, judgement="criteria", **{field: True}).error
        is ErrorCode.INVALID_ARGS
    )
    sc.finalize()
    archived = next(
        row for row in sc.s.archives[0]["results"]["recap"] if row["player_id"] == sc.player_ids[0]
    )
    assert archived["history"][0][field] is True


def test_invalid_combined_scale_is_atomic() -> None:
    sc = Scenario()
    before = sc.s.game.settings.copy()
    assert sc.configure(title_points=700, artist_points=400).error is ErrorCode.INVALID_ARGS
    assert sc.s.game.settings == before


def test_final_reason_is_private_published_once_and_reset_with_amount() -> None:
    sc = Scenario(rounds=1)
    sc.to_review()
    pid = sc.player_ids[0]
    sc.on_phase("final_set", {"player_id": pid, "delta": 2, "note": "Example correction"})
    assert "Example correction" not in sc.view(pid).model_dump_json()
    assert sc.s.journal.events() == ()
    sc.on_phase("final_reset")
    assert sc.s.game.final_notes == {}
    sc.on_phase("final_set", {"player_id": pid, "delta": 2, "note": "Example correction"})
    sc.finalize()
    finals = [event for event in sc.s.journal.events() if event.kind is ScoreKind.FINAL_ADJUSTMENT]
    assert len(finals) == 1
    assert finals[0].note == "Example correction"
    assert "Example correction" in sc.view(pid).model_dump_json()
    assert (
        sc.host(
            "final_set", expected_phase="FINAL_SCORE_REVIEW", args={"player_id": pid, "delta": 0}
        ).error
        is not None
    )
    assert sc.current().state is RoundState.REVEALED


def test_stale_final_correction_cannot_overwrite_another_hosts_reason() -> None:
    sc = Scenario(rounds=1)
    sc.to_review()
    pid = sc.player_ids[0]
    first = {"player_id": pid, "delta": 2, "note": "Example first", "expected_delta": 0}
    assert sc.on_phase("final_set", first).error is None
    assert (
        sc.on_phase("final_set", {**first, "delta": 3, "note": "Example second"}).error
        is ErrorCode.STALE_COMMAND
    )
    assert sc.s.game.final_draft == {pid: 2}
    assert sc.s.game.final_notes == {pid: "Example first"}


def test_format_four_migrates_missing_fields_without_revoking_sessions(tmp_path: Path) -> None:
    sc = Scenario(rounds=1)
    sc.to_review()
    sessions = SessionRegistry(3600000)
    recovery = sessions.recovery_code(sc.player_ids[0])
    store = SnapshotStore(tmp_path, ("example-game", "example-host", "example-bridge"))
    store.save(sc.engine, sessions, sc.clock.now())
    path = tmp_path / "session.json"
    payload = json.loads(path.read_text(encoding="utf8"))
    payload["format"] = 4
    for name in ("consumed_cancelled",):
        payload["state"].pop(name, None)

    def legacy(value):
        if isinstance(value, dict):
            fields = value.get("fields", {})
            for name in (
                "auto_advance",
                "intermission_s",
                "custom_points",
                "final_notes",
                "auto_advance_at",
                "judgements",
                "score_revisions",
            ):
                fields.pop(name, None)
            for child in value.values():
                legacy(child)
        elif isinstance(value, list):
            for child in value:
                legacy(child)

    legacy(payload)
    path.write_text(json.dumps(payload), encoding="utf8")
    at = Instant(10, sc.clock.now().wall_ms + 100)
    engine = GameEngine(sc.s.config, ids=SecretIds(), rng=random.Random(1), started_at=at)
    restored = SessionRegistry(3600000)
    assert store.restore(engine, restored, at)
    assert restored.recover(recovery) == sc.player_ids[0]
    assert engine.state.game.settings.auto_advance
    assert engine.state.game.rounds[0].auto_advance_at is None
    store.save(engine, restored, at)
    assert json.loads(path.read_text(encoding="utf8"))["format"] == 10
