"""Game machine (spec §7.1, §20.1 item 1): LOBBY → IN_GAME → FINAL_SCORE_REVIEW → FINAL_RESULTS.

Rows: G1 start, G2 to_final_review, G3–G8 early ends, G9 final_validate, G10 new_game,
G11 end_session, G12 no IN_GAME → FINAL_RESULTS path.
"""

import pytest
from builders import BRIDGE_ID, Scenario

from openblindysir_protocol.enums import CancelReason, GamePhase, RoundState
from openblindysir_protocol.errors import CloseCode, ErrorCode
from openblindysir_server.game import commands as c
from openblindysir_server.game import effects as e


def test_start_game_creates_round_one() -> None:
    sc = Scenario()
    sc.start()
    assert sc.s.game.phase is GamePhase.IN_GAME
    r = sc.current()
    assert r.number == 1
    assert r.state is RoundState.LOADING


def test_start_blocked_without_sources() -> None:
    sc = Scenario()
    sc.configure(sources=[])
    assert sc.on_phase("start_game").error is ErrorCode.NO_SOURCES
    assert sc.s.game.phase is GamePhase.LOBBY


def test_start_blocked_with_bridge_offline() -> None:
    sc = Scenario()
    sc.d(c.BridgeDisconnected(BRIDGE_ID))
    assert sc.on_phase("start_game").error is ErrorCode.BRIDGE_OFFLINE


def test_start_blocked_without_competitors() -> None:
    sc = Scenario(players=())
    assert sc.set_mode("mc").error is None
    assert sc.on_phase("start_game").error is ErrorCode.NO_COMPETITORS


@pytest.mark.parametrize("cmd", ["final_validate", "final_set", "final_reset", "new_game"])
def test_no_path_from_in_game_to_final_results(cmd: str) -> None:
    sc = Scenario()
    sc.to_open()
    args = {"player_id": sc.player_ids[0], "delta": 1} if cmd == "final_set" else {}
    phase = "FINAL_RESULTS" if cmd == "new_game" else "FINAL_SCORE_REVIEW"
    outcome = sc.host(cmd, expected_phase=phase, args=args)
    assert outcome.error is ErrorCode.STALE_COMMAND
    assert sc.s.game.phase is GamePhase.IN_GAME


def test_last_closed_round_enters_global_review_automatically() -> None:
    sc = Scenario(rounds=2)
    sc.to_review()
    assert sc.on_round("to_final_review").error is ErrorCode.INVALID_STATE
    sc.to_open()
    sc.to_review()
    assert sc.s.game.phase is GamePhase.FINAL_SCORE_REVIEW
    assert sc.on_round("next").error is ErrorCode.STALE_COMMAND
    assert len(sc.host_view().host.review_rounds) == 2


def _reach(sc: Scenario, state: str) -> None:
    if state == "PREPARING":
        sc.auto_serve = False
        sc.start()
    elif state == "LOADING":
        sc.start()
    elif state == "COUNTDOWN":
        sc.start()
        sc.ready()
    else:
        sc.to_open()
        if state == "REVIEW":
            assert sc.on_round("close").error is None


EARLY = ["PREPARING", "LOADING", "COUNTDOWN"]


@pytest.mark.parametrize("state", EARLY)
@pytest.mark.parametrize("mode", ["score", "abandon"])
def test_end_game_before_open_cancels_round(state: str, mode: str) -> None:
    sc = Scenario()
    _reach(sc, state)
    r = sc.current()
    assert r.state.value == state
    assert sc.on_round("end_game", {"current_round": mode}).error is None
    assert r.state is RoundState.CANCELLED
    assert r.cancel_reason is CancelReason.END_GAME
    assert sc.s.game.phase is GamePhase.FINAL_SCORE_REVIEW
    if state == "COUNTDOWN":
        assert sc.effects_of(e.SendStop)


@pytest.mark.parametrize("state", ["OPEN", "REVIEW"])
def test_end_game_score_enters_global_review_immediately(state: str) -> None:
    sc = Scenario()
    _reach(sc, state)
    r = sc.current()
    assert sc.on_round("end_game", {"current_round": "score"}).error is None
    assert sc.s.game.phase is GamePhase.FINAL_SCORE_REVIEW
    assert r.state is RoundState.REVIEW
    assert sc.on_round("next").error is ErrorCode.STALE_COMMAND
    sc.score({sc.player_ids[0]: 2})
    assert sc.s.journal.events() == ()
    sc.finalize()
    assert r.state is RoundState.REVEALED


@pytest.mark.parametrize("state", ["OPEN", "REVIEW"])
def test_end_game_abandon_cancels_without_points(state: str) -> None:
    sc = Scenario()
    _reach(sc, state)
    r = sc.current()
    assert sc.on_round("end_game", {"current_round": "abandon"}).error is None
    assert r.state is RoundState.CANCELLED
    assert sc.s.game.phase is GamePhase.FINAL_SCORE_REVIEW
    assert sc.s.journal.events() == ()


@pytest.mark.parametrize("mode", ["score", "abandon"])
def test_end_game_in_global_review_is_idempotent(mode: str) -> None:
    sc = Scenario(rounds=1)
    sc.to_review()
    r = sc.current()
    sc.score({sc.player_ids[0]: -2})
    assert sc.on_round("end_game", {"current_round": mode}).error is None
    assert r.state is RoundState.REVIEW
    assert r.score_draft[sc.player_ids[0]] == -2
    assert sc.s.game.phase is GamePhase.FINAL_SCORE_REVIEW


def test_abandon_after_score_request_in_review() -> None:
    sc = Scenario()
    _reach(sc, "REVIEW")
    sc.on_round("end_game", {"current_round": "score"})
    assert sc.on_round("end_game", {"current_round": "abandon"}).error is None
    assert sc.s.game.phase is GamePhase.FINAL_SCORE_REVIEW


def test_end_game_stops_prefetch() -> None:
    sc = Scenario(rounds=5)
    _reach(sc, "OPEN")
    assert sc.s.game.pipeline
    sc.on_round("end_game", {"current_round": "score"})
    assert not sc.s.game.pipeline


def test_final_validate_reaches_results_and_new_game_resets_scores() -> None:
    sc = Scenario(rounds=1)
    sc.to_review()
    a = sc.player_ids[0]
    sc.score({a: 3})
    sc.finalize()
    assert sc.s.game.phase is GamePhase.FINAL_RESULTS
    old_game = sc.s.game.game_id
    assert sc.on_phase("new_game").error is None
    assert sc.s.game.phase is GamePhase.LOBBY
    assert sc.s.game.game_id != old_game
    assert sc.view(a).standings == []
    assert a in sc.s.players


def test_end_session_revokes_everyone() -> None:
    sc = Scenario()
    sc.to_open()
    outcome = sc.on_phase("end_session")
    assert outcome.error is None
    closes = [x for x in outcome.effects if isinstance(x, e.CloseConnection)]
    assert {x.code for x in closes} == {CloseCode.SESSION_ENDED}
    assert e.RevokeTokens("ALL") in outcome.effects
    assert any(isinstance(x, e.ResetSession) for x in outcome.effects)
    assert sc.s.players == {}
    assert sc.s.game.phase is GamePhase.LOBBY
    assert BRIDGE_ID in sc.s.catalogs
