"""Product regressions from the recorded game and new shared game-night controls."""

import random
from pathlib import Path

import pytest
from builders import BRIDGE_ID, CANARY_TITLE, Scenario

from openblindysir_protocol.enums import AnswerAckStatus, RoundState
from openblindysir_protocol.errors import AnswerRejectReason, ErrorCode
from openblindysir_server.auth.sessions import SessionRegistry
from openblindysir_server.game import GameEngine, Instant, SecretIds
from openblindysir_server.game.metadata import clean_metadata
from openblindysir_server.game.state import current_round
from openblindysir_server.persistence import SnapshotStore


def test_exhausted_new_game_is_blocked_and_repeats_recover() -> None:
    sc = Scenario(rounds=1, tracks=1)
    sc.to_review()
    sc.finalize()
    sc.on_phase("new_game")
    assert sc.on_phase("start_game").error is ErrorCode.POOL_EXHAUSTED
    assert "start_game" not in sc.host_view().host.commands
    sc.configure(allow_repeats=True, rounds=3)
    for _ in range(3):
        sc.to_open()
        sc.on_round("close")
        assert len({r.slot.track_ref for r in sc.s.game.rounds}) == 1


def test_atomic_configuration_starts_with_new_sources_and_rolls_back_on_failure() -> None:
    sc = Scenario()
    sc.configure(sources=[])
    before = sc.s.game.settings.copy()
    outcome = sc.host("configure", expected_phase="LOBBY", start_game=True, args={"rounds": 2})
    assert outcome.error is ErrorCode.NO_SOURCES
    assert sc.s.game.settings == before
    outcome = sc.host(
        "configure",
        expected_phase="LOBBY",
        start_game=True,
        args={"rounds": 2, "sources": [{"bridge_id": BRIDGE_ID, "folder_prefix": ""}]},
    )
    assert outcome.error is None
    assert sc.current().number == 1
    assert sc.s.game.settings.rounds == 2


def test_current_title_is_private_until_global_review_and_zero_is_explicit() -> None:
    sc = Scenario(rounds=1)
    sc.to_open()
    assert CANARY_TITLE not in sc.host_view().model_dump_json()
    sc.on_round("close")
    reviewed = sc.host_view().host.review_rounds[0]
    assert reviewed.track.title == CANARY_TITLE
    assert CANARY_TITLE not in sc.view(sc.player_ids[0]).model_dump_json()
    assert not any(row.reviewed for row in reviewed.answers)
    assert sc.on_phase("final_validate").error is ErrorCode.UNREVIEWED_SCORES
    for row in reviewed.answers:
        assert sc.on_round("score_draft", {"player_id": row.player_id, "points": 0}).error is None
    assert all(row.reviewed for row in sc.host_view().host.review_rounds[0].answers)
    assert sc.on_phase("final_validate").error is None
    assert not sc.s.journal.events()


def test_pause_freezes_deadline_audio_offset_and_answer_time_across_resume() -> None:
    sc = Scenario()
    r = sc.to_open()
    sc.advance(1000)
    original_deadline = r.deadline
    assert sc.on_round("pause").error is None
    assert sc.on_round("pause").error is ErrorCode.INVALID_STATE
    sc.advance(300)
    frozen = sc.view(sc.player_ids[0]).paused
    assert frozen is not None
    assert frozen.clip_offset_s == pytest.approx(1.3)
    assert sc.submit(sc.player_ids[0], "paused").reason is AnswerRejectReason.NOT_OPEN
    sc.advance(60000)
    assert r.state is RoundState.OPEN
    assert sc.view(sc.player_ids[0]).paused == frozen
    assert sc.on_round("resume").error is None
    assert r.resume_at is not None
    assert sc.on_round("resume").error is ErrorCode.INVALID_STATE
    assert r.plays[-1].clip_offset_s == pytest.approx(1.3)
    sc.advance_to(r.resume_at)
    sc.advance(1000)
    assert sc.submit(sc.player_ids[0], "resumed").status is AnswerAckStatus.ACCEPTED
    assert r.answers[sc.player_ids[0]].elapsed_ms == 2300
    assert r.deadline == original_deadline + r.paused_total_ms
    sc.advance_to(r.deadline)
    assert r.state is RoundState.REVIEW


def test_captured_zero_policy_and_spectators_do_not_affect_ready_or_scores() -> None:
    sc = Scenario()
    spectator = sc.player_ids[2]
    sc.on_phase("participation", {"player_id": spectator, "spectator": True, "team": None})
    for pid in sc.player_ids[:2]:
        sc.on_phase("participation", {"player_id": pid, "team": "Example team"})
    sc.configure(captured_policy="zero", instructions="Example instructions", title_points=2)
    sc.to_open()
    assert not sc.view(spectator).me.participant
    assert sc.submit(spectator, "secret").reason is AnswerRejectReason.NOT_PARTICIPANT
    assert sc.view(spectator).rules.instructions == "Example instructions"
    sc.draft(sc.player_ids[0], "captured")
    sc.submit(sc.player_ids[1], "locked")
    sc.on_round("close")
    sc.on_phase("end_game", {"current_round": "score"})
    assert (
        sc.on_round("score_draft", {"player_id": sc.player_ids[0], "points": 1}).error
        is ErrorCode.INVALID_ARGS
    )
    sc.score({sc.player_ids[0]: 0, sc.player_ids[1]: 3})
    sc.finalize()
    teams = sc.host_view().team_standings
    assert teams[0].score == 3
    assert spectator not in [row.player_id for row in sc.host_view().standings]


def test_role_permission_matches_handler_and_metadata_edits_survive_reveal() -> None:
    sc = Scenario(rounds=1)
    sc.to_open()
    assert "set_mode" not in sc.host_view().host.commands
    assert sc.set_mode("mc").error is ErrorCode.INVALID_STATE
    sc.on_round("close")
    assert "set_mode" in sc.host_view().host.commands
    assert (
        sc.on_round(
            "track_metadata", {"title": "Example correction", "artist": "Example artist"}
        ).error
        is None
    )
    sc.finalize()
    results = sc.host_view().final_results
    assert results.recap[0].history[0].track.title == "Example correction"
    sc.on_phase("new_game")
    assert (
        sc.s.archives[0]["results"]["recap"][0]["history"][0]["track"]["title"]
        == "Example correction"
    )


def test_metadata_cleanup_separates_exported_filename_from_artist() -> None:
    assert clean_metadata("GIMS & DYSTINCT - SPIDER (Official Lyrics Video)", "GIMS", "") == (
        "SPIDER",
        "GIMS & DYSTINCT",
    )
    assert clean_metadata("Example title", "Example artist", "filename") == (
        "Example title",
        "Example artist",
    )


def test_snapshot_restores_auth_answers_and_journal_without_audio_or_plaintext_tokens(
    tmp_path: Path,
) -> None:
    sc = Scenario(rounds=2)
    sc.to_review()
    sc.to_open()
    sc.submit(sc.player_ids[0], "Example locked answer")
    sc.draft(sc.player_ids[1], "Example draft")
    sessions = SessionRegistry(3600000)
    token = sessions.issue(sc.player_ids[0], sc.clock.now().mono_ms)
    store = SnapshotStore(tmp_path, ("example-secret",))
    store.save(sc.engine, sessions, sc.clock.now())
    assert token not in (tmp_path / "session.json").read_text(encoding="utf-8")
    assert "example-secret" not in (tmp_path / "session.json").read_text(encoding="utf-8")
    now = Instant(123, sc.clock.now().wall_ms + 1000)
    restored = GameEngine(sc.s.config, ids=SecretIds(), rng=random.Random(1), started_at=now)
    registry = SessionRegistry(3600000)
    assert store.restore(restored, registry, now)
    assert registry.resolve(token, now.mono_ms) == sc.player_ids[0]
    r = current_round(restored.state.game)
    assert r is not None
    assert r.state is RoundState.REVIEW
    assert r.recovery_interrupted
    assert r.answers[sc.player_ids[0]].text == "Example locked answer"
    assert r.answers[sc.player_ids[1]].status.value == "CAPTURED"
    assert restored.state.journal.events() == ()
    assert len(restored.state.game.rounds) == 2
    restored.dispatch(
        __import__("openblindysir_server.game.commands", fromlist=["Tick"]).Tick(), now
    )
    assert len(restored.view_for(sc.host_id).host.review_rounds) == 2
    assert restored.view_for(sc.player_ids[0]).audio.current is None


def test_snapshot_backup_recovers_corruption_and_changed_password_invalidates_tokens(
    tmp_path: Path,
) -> None:
    sc = Scenario()
    sessions = SessionRegistry(3600000)
    token = sessions.issue(sc.host_id, 0)
    store = SnapshotStore(tmp_path, ("example-original",))
    store.save(sc.engine, sessions, sc.clock.now())
    store.save(sc.engine, sessions, sc.clock.now())
    (tmp_path / "session.json").write_text("truncated", encoding="utf-8")
    now = Instant(50, sc.clock.now().wall_ms + 100)
    restored = GameEngine(sc.s.config, ids=SecretIds(), rng=random.Random(1), started_at=now)
    registry = SessionRegistry(3600000)
    assert SnapshotStore(tmp_path, ("example-changed",)).restore(restored, registry, now)
    assert registry.resolve(token, now.mono_ms) is None
    assert restored.state.players[sc.host_id].nickname == "Yo"
