"""Answers (spec §6.2, §20.1 item 2)."""

from builders import Scenario

from openblindysir_protocol.enums import AnswerAckStatus, AnswerStatus, RoundState
from openblindysir_protocol.errors import AnswerRejectReason
from openblindysir_server.game import commands as c


def test_draft_then_submit() -> None:
    sc = Scenario()
    a = sc.player_ids[0]
    r = sc.to_open()
    sc.draft(a, "Poké")
    assert r.answers[a].status is AnswerStatus.DRAFT
    ack = sc.submit(a, "Pokémon")
    assert ack.status is AnswerAckStatus.ACCEPTED
    assert ack.reason is None
    assert r.answers[a].status is AnswerStatus.LOCKED
    assert r.answers[a].text == "Pokémon"


def test_second_submit_ignored() -> None:
    sc = Scenario()
    a = sc.player_ids[0]
    r = sc.to_open()
    sc.submit(a, "first")
    ack = sc.submit(a, "second")
    assert ack.status is AnswerAckStatus.REJECTED
    assert ack.reason is AnswerRejectReason.ALREADY_LOCKED
    assert r.answers[a].text == "first"


def test_submit_after_close_rejected_and_draft_captured() -> None:
    sc = Scenario()
    a = sc.player_ids[0]
    r = sc.to_open()
    sc.draft(a, "j'avais la réponse")
    sc.on_round("close")
    ack = sc.submit(a, "j'avais la réponse", round_id=r.id)
    assert ack.reason is AnswerRejectReason.CLOSED
    answer = r.answers[a]
    assert answer.status is AnswerStatus.CAPTURED
    assert answer.order is None
    assert answer.elapsed_ms is None


def test_submit_after_deadline_before_timer_fired_is_rejected() -> None:
    sc = Scenario()
    a = sc.player_ids[0]
    r = sc.to_open()
    assert r.deadline is not None
    sc.clock.set(r.deadline + 1)  # no tick: the deadline timer has not fired yet
    ack = sc.submit(a, "trop tard")
    assert ack.reason is AnswerRejectReason.CLOSED
    assert r.state is RoundState.REVIEW


def test_draft_restored_on_reconnection() -> None:
    sc = Scenario()
    a = sc.player_ids[0]
    sc.to_open()
    sc.draft(a, "brouillon")
    sc.d(c.Disconnected(a))
    sc.d(c.Connected(a, "0.1.0"))
    view = sc.view(a)
    assert view.round is not None
    assert view.round.state == "OPEN"
    assert view.round.my_answer.draft_text == "brouillon"  # type: ignore[union-attr]


def test_draft_never_bumps_version() -> None:
    sc = Scenario()
    a = sc.player_ids[0]
    sc.to_open()
    before = sc.engine.version
    outcome = sc.draft(a, "x")
    assert not outcome.changed
    assert sc.engine.version == before


def test_submit_before_open_is_not_open() -> None:
    sc = Scenario()
    sc.start()
    ack = sc.submit(sc.player_ids[0], "x")
    assert ack.reason is AnswerRejectReason.NOT_OPEN


def test_mc_host_is_not_a_participant() -> None:
    sc = Scenario()
    sc.set_mode("mc")
    sc.to_open()
    assert sc.host_id is not None
    ack = sc.submit(sc.host_id, "x")
    assert ack.reason is AnswerRejectReason.NOT_PARTICIPANT


def test_empty_answer_rejected() -> None:
    sc = Scenario()
    sc.to_open()
    assert sc.submit(sc.player_ids[0], "   ").reason is AnswerRejectReason.EMPTY


def test_too_long_answer_rejected_by_configured_limit() -> None:
    from openblindysir_server.game import CoreConfig  # noqa: PLC0415

    sc = Scenario(config=CoreConfig(answer_max_chars=10))
    sc.to_open()
    assert sc.submit(sc.player_ids[0], "x" * 11).reason is AnswerRejectReason.TOO_LONG


def test_wrong_round_and_earlier_round() -> None:
    sc = Scenario()
    first = sc.to_open()
    a = sc.player_ids[0]
    assert sc.submit(a, "x", round_id="r_999999").reason is AnswerRejectReason.WRONG_ROUND
    sc.on_round("close")
    sc.to_open()
    assert sc.submit(a, "x", round_id=first.id).reason is AnswerRejectReason.CLOSED


def test_late_joiner_can_answer_round_in_progress() -> None:
    sc = Scenario()
    sc.to_open()
    late = sc.join("Tardif")
    assert sc.submit(late, "réponse").status is AnswerAckStatus.ACCEPTED
