"""Round machine (spec §7.2, §20.1 item 1): deadline, add_time, auto close, replay, stop,
skip, failures with replacement, idempotency of host commands, undo window."""

from builders import Scenario

from openblindysir_protocol.enums import AnswerStatus, CloseReason, JobFailureCode, RoundState
from openblindysir_protocol.errors import ErrorCode
from openblindysir_protocol.views import RoundOpen
from openblindysir_server.game import commands as c
from openblindysir_server.game import effects as e


def test_deadline_closes_at_exact_instant_even_if_timer_late() -> None:
    sc = Scenario()
    r = sc.to_open()
    assert r.deadline is not None
    sc.advance_to(r.deadline + 750)  # the timer fires late
    assert r.state is RoundState.REVIEW
    assert r.closed_at == r.deadline
    assert r.close_reason is CloseReason.DEADLINE


def test_deadline_is_start_plus_clip_plus_grace() -> None:
    sc = Scenario(clip_s=20.0)
    r = sc.to_open()
    assert r.official_start_at is not None
    assert r.deadline == r.official_start_at + 20_000 + 15_000


def test_add_time_and_its_idempotency_key() -> None:
    sc = Scenario()
    r = sc.to_open()
    before = r.deadline
    assert before is not None
    assert sc.on_round("add_time", {"expected_deadline": before}).error is None
    assert r.deadline == before + 15_000
    assert sc.on_round("add_time", {"expected_deadline": before}).error is ErrorCode.STALE_COMMAND
    assert r.deadline == before + 15_000


def test_auto_close_when_every_online_participant_validated() -> None:
    sc = Scenario()
    r = sc.to_open()
    offline = sc.player_ids[0]
    sc.d(c.Disconnected(offline))
    for pid in [*sc.player_ids[1:], sc.host_id]:
        assert pid is not None
        sc.submit(pid, "x")
    assert r.state is RoundState.REVIEW
    assert r.close_reason is CloseReason.ALL_LOCKED


def test_host_close() -> None:
    sc = Scenario()
    r = sc.to_open()
    assert sc.on_round("close").error is None
    assert r.close_reason is CloseReason.HOST


def test_replay_keeps_official_start_and_deadline() -> None:
    sc = Scenario()
    r = sc.to_open()
    official, deadline = r.official_start_at, r.deadline
    first = r.plays[-1].play_id
    sc.advance(2_000)
    outcome = sc.on_round("replay", {"play_id": first})
    assert outcome.error is None
    assert r.official_start_at == official
    assert r.deadline == deadline
    assert len(r.plays) == 2
    assert e.SendStop(first) in outcome.effects
    plays = [x for x in outcome.effects if isinstance(x, e.SendPlay)]
    assert plays[0].play.play_id != first
    assert sc.on_round("replay", {"play_id": first}).error is ErrorCode.STALE_COMMAND


def test_stop_then_play_is_gone() -> None:
    sc = Scenario()
    r = sc.to_open()
    play_id = r.plays[-1].play_id
    assert sc.on_round("stop", {"play_id": play_id}).error is None
    assert sc.view(sc.player_ids[0]).play is None
    assert sc.on_round("stop", {"play_id": play_id}).error is ErrorCode.STALE_COMMAND


def test_play_disappears_from_view_at_end_of_clip() -> None:
    sc = Scenario(clip_s=20.0)
    r = sc.to_open()
    assert sc.view(sc.player_ids[0]).play is not None
    sc.advance(20_001)
    assert sc.view(sc.player_ids[0]).play is None
    assert r.state is RoundState.OPEN


def test_skip_cancels_and_keeps_number_and_track_unplayed() -> None:
    sc = Scenario()
    sc.start()
    r = sc.current()
    track = r.slot.track_ref
    assert sc.on_round("skip").error is None
    assert r.state is RoundState.CANCELLED
    assert sc.current().number == 1
    assert track not in sc.s.played


def test_skip_open_round_stops_play() -> None:
    sc = Scenario()
    r = sc.to_open()
    outcome = sc.on_round("skip")
    assert e.SendStop(r.plays[-1].play_id) in outcome.effects


def test_track_failure_is_replaced_then_round_fails_after_three() -> None:
    sc = Scenario(auto_serve=False)
    sc.start()
    r = sc.current()
    tried = set()
    for _ in range(3):
        job = sc.pending_jobs.pop(0)
        tried.add(job.track_id)
        sc.d(c.JobFailedIn(job.job_id, JobFailureCode.NOT_FOUND))
    assert len(tried) == 3
    assert r.state is RoundState.FAILED
    assert sc.current().number == 1
    assert sc.current() is not r


def test_replacement_warns_host_only() -> None:
    sc = Scenario(auto_serve=False)
    sc.start()
    job = sc.pending_jobs.pop(0)
    sc.d(c.JobFailedIn(job.job_id, JobFailureCode.DECODE_ERROR))
    host = sc.host_view()
    assert host.kind != "player"
    assert "track_replaced" in host.host.warnings  # type: ignore[union-attr]


def test_next_is_idempotent() -> None:
    sc = Scenario()
    sc.to_review()
    sc.publish()
    r1 = sc.current()
    assert sc.host("next", round_id=r1.id, args={}).error is None
    assert sc.host("next", round_id=r1.id, args={}).error is ErrorCode.STALE_COMMAND
    assert sc.current().number == 2


def test_publish_twice_is_stale_or_invalid() -> None:
    sc = Scenario()
    r = sc.to_review()
    assert sc.on_round("publish", {"confirm_unreviewed": True}).error is None
    assert sc.host("publish", round_id=r.id, args={}).error is ErrorCode.INVALID_STATE
    assert len(sc.s.journal.events()) == 0


def test_undo_publish_restores_review_and_draft() -> None:
    sc = Scenario()
    a = sc.player_ids[0]
    r = sc.to_review()
    sc.publish({a: 3})
    assert sc.host("undo_publish", round_id=r.id, args={}).error is None
    assert r.state is RoundState.REVIEW
    assert r.score_draft == {a: 3}
    assert r.reveal is None
    assert sc.view(a).standings[0].score == 0


def test_undo_allowed_while_next_round_not_in_countdown() -> None:
    sc = Scenario()
    r = sc.to_review()
    sc.publish()
    sc.on_round("next")
    nxt = sc.current()
    assert nxt.state is RoundState.LOADING
    assert sc.host("undo_publish", round_id=r.id, args={}).error is None
    assert sc.current() is r
    assert nxt.state is RoundState.CANCELLED


def test_undo_refused_once_next_round_reached_countdown() -> None:
    sc = Scenario()
    r = sc.to_review()
    sc.publish()
    sc.on_round("next")
    sc.ready()
    assert sc.current().state is RoundState.COUNTDOWN
    assert sc.host("undo_publish", round_id=r.id, args={}).error is ErrorCode.STALE_COMMAND


def test_undo_after_skipped_next_round() -> None:
    sc = Scenario()
    r = sc.to_review()
    sc.publish()
    sc.on_round("next")
    sc.on_round("skip")
    assert sc.host("undo_publish", round_id=r.id, args={}).error is None
    assert sc.current() is r
    assert r.state is RoundState.REVIEW


def test_close_captures_drafts() -> None:
    sc = Scenario()
    a = sc.player_ids[0]
    r = sc.to_open()
    sc.draft(a, "Pikach")
    sc.on_round("close")
    assert r.answers[a].status is AnswerStatus.CAPTURED
    assert r.answers[a].order is None


def test_round_open_view_is_shared_by_player_and_host_player_mode() -> None:
    sc = Scenario()
    sc.to_open()
    assert isinstance(sc.view(sc.player_ids[0]).round, RoundOpen)
    assert isinstance(sc.host_view().round, RoundOpen)
