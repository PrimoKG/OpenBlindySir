"""Mandatory final review (spec §6.6–6.7, §20.1 item 5)."""

from builders import Scenario

from openblindysir_protocol.enums import GamePhase, ScoreKind
from openblindysir_protocol.errors import ErrorCode
from openblindysir_server.game import commands as c


def at_final_review(points: dict[int, int] | None = None) -> Scenario:
    sc = Scenario(rounds=1)
    sc.to_review()
    sc.publish({sc.player_ids[i]: pts for i, pts in (points or {}).items()})
    sc.on_round("to_final_review")
    assert sc.s.game.phase is GamePhase.FINAL_SCORE_REVIEW
    return sc


def test_final_set_is_a_draft_value_not_an_event() -> None:
    sc = at_final_review({0: 3})
    a = sc.player_ids[0]
    sc.on_phase("final_set", {"player_id": a, "delta": 2})
    sc.on_phase("final_set", {"player_id": a, "delta": 2})
    assert sc.s.game.final_draft == {a: 2}
    assert len(sc.s.journal.events()) == 1
    row = next(r for r in sc.host_view().host.final_review if r.player_id == a)  # type: ignore[union-attr]
    assert (row.score_before, row.draft_delta, row.score_after) == (3, 2, 5)


def test_final_validate_creates_one_event_per_non_zero_delta_including_host() -> None:
    sc = at_final_review()
    a, b = sc.player_ids[:2]
    assert sc.host_id is not None
    sc.on_phase("final_set", {"player_id": a, "delta": 2})
    sc.on_phase("final_set", {"player_id": b, "delta": -1})
    sc.on_phase("final_set", {"player_id": sc.host_id, "delta": 1})
    sc.on_phase("final_set", {"player_id": b, "delta": 0})
    assert sc.on_phase("final_validate").error is None
    finals = [ev for ev in sc.s.journal.events() if ev.kind is ScoreKind.FINAL_ADJUSTMENT]
    assert {(ev.player_id, ev.delta) for ev in finals} == {(a, 2), (sc.host_id, 1)}
    assert all(ev.round_id is None for ev in finals)
    assert sc.s.game.phase is GamePhase.FINAL_RESULTS


def test_final_validate_is_idempotent() -> None:
    sc = at_final_review()
    sc.on_phase("final_set", {"player_id": sc.player_ids[0], "delta": 2})
    first = sc.host("final_validate", expected_phase="FINAL_SCORE_REVIEW", args={})
    second = sc.host("final_validate", expected_phase="FINAL_SCORE_REVIEW", args={})
    assert first.error is None
    assert second.error is ErrorCode.STALE_COMMAND
    assert len([ev for ev in sc.s.journal.events() if ev.kind is ScoreKind.FINAL_ADJUSTMENT]) == 1


def test_final_reset_empties_draft() -> None:
    sc = at_final_review()
    sc.on_phase("final_set", {"player_id": sc.player_ids[0], "delta": 2})
    sc.on_phase("final_reset")
    assert sc.s.game.final_draft == {}


def test_draft_survives_host_reconnection() -> None:
    sc = at_final_review()
    assert sc.host_id is not None
    sc.on_phase("final_set", {"player_id": sc.player_ids[0], "delta": 4})
    sc.d(c.Disconnected(sc.host_id))
    sc.d(c.Connected(sc.host_id, "0.1.0"))
    rows = sc.host_view().host.final_review  # type: ignore[union-attr]
    assert rows is not None
    assert any(r.draft_delta == 4 for r in rows)


def test_scores_frozen_after_final_results() -> None:
    sc = at_final_review()
    sc.on_phase("final_validate")
    game_id = sc.s.game.game_id
    assert sc.s.journal.is_frozen(game_id)
    adjust = {"player_id": sc.player_ids[0], "delta": 1, "op_id": "op-0000009"}
    assert sc.host("adjust", expected_phase="IN_GAME", args=adjust).error is ErrorCode.STALE_COMMAND


def test_final_results_show_adjustments_and_shared_ranks() -> None:
    sc = at_final_review({0: 2, 1: 2})
    sc.on_phase("final_set", {"player_id": sc.player_ids[2], "delta": 2})
    sc.on_phase("final_validate")
    results = sc.view(sc.player_ids[0]).final_results
    assert results is not None
    assert [row.rank for row in results.standings][:3] == [1, 1, 1]
    assert results.rounds_played == 1
    assert [(x.player_id, x.delta) for x in results.final_adjustments] == [(sc.player_ids[2], 2)]


def test_players_see_frozen_standings_and_no_draft() -> None:
    sc = at_final_review({0: 3})
    sc.on_phase("final_set", {"player_id": sc.player_ids[0], "delta": 5})
    player_json = sc.view(sc.player_ids[1]).model_dump_json()
    assert "draft_delta" not in player_json
    assert "score_after" not in player_json
    assert sc.view(sc.player_ids[1]).standings[0].score == 3
