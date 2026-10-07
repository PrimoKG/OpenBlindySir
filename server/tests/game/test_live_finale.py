"""The host reveals only selected rounds, while confirmed scores remain reversible."""

import random

from builders import Scenario

from openblindysir_protocol.enums import GamePhase
from openblindysir_protocol.errors import ErrorCode
from openblindysir_server.auth.sessions import SessionRegistry
from openblindysir_server.game import GameEngine, Instant, SecretIds, timers
from openblindysir_server.game import commands as c
from openblindysir_server.persistence import SnapshotStore


def two_rounds():
    sc = Scenario(rounds=2)
    first = sc.to_open()
    sc.submit(sc.player_ids[0], "First closed answer")
    sc.to_review()
    second = sc.to_open()
    sc.submit(sc.player_ids[0], "Second closed answer")
    sc.to_review()
    assert sc.s.game.phase is GamePhase.FINAL_SCORE_REVIEW
    return sc, first, second


def score_at(sc, r, pid, points):
    assert (
        sc.host("score_draft", round_id=r.id, args={"player_id": pid, "points": points}).error
        is None
    )


def test_private_preparation_cannot_reveal_other_rounds_or_scores():
    sc, first, second = two_rounds()
    pid = sc.player_ids[0]
    score_at(sc, first, pid, 2)
    score_at(sc, second, pid, 9)
    waiting = sc.view(pid).finale
    assert waiting.round is None
    assert all(row.score == 0 for row in waiting.standings)
    assert sc.on_phase("finale_reveal", {"round_id": first.id}).error is None
    shown = sc.view(pid).finale
    assert shown.round.round_id == first.id
    assert "First closed answer" in shown.model_dump_json()
    assert "Second closed answer" not in shown.model_dump_json()
    assert next(row.score for row in shown.standings if row.player_id == pid) == 2
    assert not {"elapsed_ms", "late_start_ms", "received_at_wall_ms", "score_before"} & set(
        shown.round.answers[0].model_dump()
    )
    assert sc.s.journal.events() == ()


def test_partial_criteria_and_zero_are_distinguished_from_pending():
    sc = Scenario(rounds=1)
    sc.to_review()
    r, pid = sc.current(), sc.player_ids[0]
    sc.on_phase("finale_reveal", {"round_id": r.id})
    assert (
        sc.host(
            "score_draft",
            round_id=r.id,
            args={
                "player_id": pid,
                "points": 1,
                "judgement": "criteria",
                "title_correct": True,
                "artist_correct": None,
                "expected_revision": 0,
            },
        ).error
        is None
    )
    row = next(a for a in sc.view(pid).finale.round.answers if a.player_id == pid)
    assert (row.points, row.revision, row.reviewed) == (1, 1, False)
    assert sc.on_phase("final_validate").error is ErrorCode.UNREVIEWED_SCORES
    score_at(sc, r, pid, 0)
    row = next(a for a in sc.view(pid).finale.round.answers if a.player_id == pid)
    assert (row.points, row.revision, row.reviewed) == (0, 2, True)


def test_revisiting_rounds_cannot_duplicate_points_and_final_totals_match():
    sc, first, second = two_rounds()
    a, b = sc.player_ids[:2]
    score_at(sc, first, a, 2)
    score_at(sc, second, a, 1)
    score_at(sc, second, b, 4)
    for r in (first, second, first, first):
        assert sc.on_phase("finale_reveal", {"round_id": r.id}).error is None
    assert sc.s.game.finale_revealed == [first.id, second.id]
    sc.on_phase("final_set", {"player_id": b, "delta": -1})
    public = sc.view(a).finale
    assert [(row.score, row.rank) for row in public.standings[:2]] == [(3, 1), (3, 1)]
    score_at(sc, first, a, -2)
    preview = sc.view(a).finale.standings
    sc.finalize()
    assert sc.view(a).final_results.standings == preview
    assert sc.view(a).final_results.podium_started_at == sc.clock.now().mono_ms + 800
    assert sc.view(a).finale is None
    assert (
        sc.host(
            "finale_reveal", expected_phase="FINAL_SCORE_REVIEW", args={"round_id": first.id}
        ).error
        is ErrorCode.STALE_COMMAND
    )


def test_team_scores_follow_revealed_rounds_and_exclude_cancelled_points():
    sc = Scenario(rounds=1)
    a, b = sc.player_ids[:2]
    for pid in (a, b):
        sc.on_phase("participation", {"player_id": pid, "team": "One team"})
    r = sc.to_open()
    sc.on_round("skip")
    sc.on_phase("end_game", {"current_round": "abandon"})
    assert sc.s.game.phase is GamePhase.FINAL_SCORE_REVIEW
    sc.on_phase("finale_reveal", {"round_id": r.id})
    finale = sc.view(a).finale
    assert not finale.round.included
    assert all(row.score == 0 for row in finale.standings)
    assert finale.teams[0].score == 0


def test_reveal_is_host_only_and_rejects_unknown_or_unplayed_rounds():
    sc = Scenario(rounds=1)
    sc.to_review()
    before = sc.s.game.finale_revealed.copy()
    assert (
        sc.host(
            "finale_reveal",
            expected_phase="FINAL_SCORE_REVIEW",
            by=sc.player_ids[0],
            args={"round_id": sc.current().id},
        ).error
        is ErrorCode.NOT_HOST
    )
    assert sc.on_phase("finale_reveal", {"round_id": "r_missing"}).error is ErrorCode.INVALID_ARGS
    assert sc.s.game.finale_revealed == before
    unplayed = Scenario(rounds=1)
    unplayed.start()
    r = unplayed.current()
    unplayed.on_phase("end_game", {"current_round": "abandon"})
    assert unplayed.on_phase("finale_reveal", {"round_id": r.id}).error is ErrorCode.INVALID_ARGS


def test_reconnection_and_restart_keep_public_scene_without_replaying_audio(tmp_path):
    sc = Scenario(rounds=1)
    sc.to_review()
    pid, rid = sc.player_ids[0], sc.current().id
    sc.on_phase("finale_reveal", {"round_id": rid})
    score_at(sc, sc.current(), pid, 2)
    assert (
        sc.d(
            c.FinaleReplayReady(sc.host_id, sc.s.game.game_id, rid, sc.s.game.finale_audio_revision)
        ).error
        is None
    )
    assert sc.view(pid).play is not None
    sessions = SessionRegistry(3600000)
    store = SnapshotStore(tmp_path, ("example",))
    store.save(sc.engine, sessions, sc.clock.now())
    now = Instant(100, sc.clock.now().wall_ms + 1000)
    restored = GameEngine(sc.s.config, ids=SecretIds(), rng=random.Random(1), started_at=now)
    assert store.restore(restored, SessionRegistry(3600000), now)
    view = restored.view_for(pid)
    assert view.finale.round.round_id == rid
    assert next(row.score for row in view.finale.standings if row.player_id == pid) == 2
    assert view.play is None
    assert view.audio.current is None
    sc.finalize()
    store.save(sc.engine, sessions, sc.clock.now())
    assert store.restore(restored, SessionRegistry(3600000), now)
    assert restored.view_for(pid).final_results.podium_started_at is None


def start_finale_audio(sc):
    rid = sc.current().id
    sc.on_phase("finale_reveal", {"round_id": rid})
    assert (
        sc.d(
            c.FinaleReplayReady(sc.host_id, sc.s.game.game_id, rid, sc.s.game.finale_audio_revision)
        ).error
        is None
    )
    return sc.s.game.finale_play


def test_finale_audio_end_wakes_runtime_and_publishes_idle_state():
    sc = Scenario(rounds=1)
    sc.to_review()
    play = start_finale_audio(sc)
    assert timers.next_wakeup(sc.s) == play.ends_at
    sc.advance_to(play.ends_at - 1)
    version = sc.s.version
    assert sc.view(sc.host_id).play is not None
    outcome = sc.advance(1)
    assert outcome.changed
    assert sc.s.version > version
    assert sc.s.game.finale_play is None
    for pid in [sc.host_id, *sc.player_ids]:
        view = sc.view(pid)
        assert view.play is None
        assert view.audio.current is None
    assert timers.next_wakeup(sc.s) is None


def test_old_finale_audio_deadline_cannot_stop_replacement_or_stopped_play():
    sc = Scenario(rounds=1)
    sc.to_review()
    first = start_finale_audio(sc)
    sc.advance(1000)
    second = start_finale_audio(sc)
    assert second.play_id != first.play_id
    assert sc.advance_to(first.ends_at).changed is False
    assert sc.s.game.finale_play == second
    assert sc.advance_to(second.ends_at).changed
    third = start_finale_audio(sc)
    assert sc.on_phase("finale_stop").error is None
    assert sc.advance_to(third.ends_at).changed is False
    assert sc.s.game.finale_play is None
