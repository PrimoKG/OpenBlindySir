"""HOST permissions (spec §12, §20.1 item 6): every HOST command is refused to a player."""

import copy

import pytest
from builders import Scenario

from openblindysir_protocol.errors import ErrorCode
from openblindysir_protocol.host_commands import HOST_COMMAND_EXAMPLES, HOST_COMMAND_NAMES
from openblindysir_server.game import commands as c
from openblindysir_server.game import permissions


def snapshot(sc: Scenario) -> str:
    """Comparable dump of the observable state (every view) plus the journal."""
    views = [sc.view(pid).model_dump_json() for pid in sc.s.players]
    return repr((views, sc.s.journal.events(), sc.s.game.phase))


@pytest.mark.parametrize("cmd", HOST_COMMAND_NAMES)
@pytest.mark.parametrize("phase", ["LOBBY", "OPEN", "REVIEW", "FINAL_SCORE_REVIEW"])
def test_every_host_command_refused_to_a_player(cmd: str, phase: str) -> None:
    sc = Scenario(rounds=1)
    if phase == "OPEN":
        sc.to_open()
    elif phase == "REVIEW":
        sc.to_review()
    elif phase == "FINAL_SCORE_REVIEW":
        sc.to_review()
        sc.publish()
        sc.on_round("to_final_review")
    fields = copy.deepcopy(HOST_COMMAND_EXAMPLES[cmd])
    if "round_id" in fields and phase in ("OPEN", "REVIEW"):
        fields["round_id"] = sc.current().id
    if "expected_phase" in fields and cmd in ("kick", "rename", "set_mode", "end_session"):
        fields["expected_phase"] = sc.s.game.phase.value
    before = snapshot(sc)
    version = sc.engine.version
    outcome = sc.host(cmd, by=sc.player_ids[0], **fields)
    assert outcome.error is ErrorCode.NOT_HOST
    assert not outcome.changed
    assert sc.engine.version == version
    assert snapshot(sc) == before


def test_rejected_command_leaves_state_unchanged() -> None:
    sc = Scenario()
    sc.to_open()
    before = snapshot(sc)
    assert sc.on_round("publish").error is ErrorCode.INVALID_STATE
    assert sc.host("final_validate", expected_phase="FINAL_SCORE_REVIEW", args={}).error
    assert snapshot(sc) == before


def test_elevated_player_becomes_host_in_player_mode() -> None:
    sc = Scenario()
    a = sc.player_ids[0]
    sc.d(c.ElevateHost(a))
    view = sc.view(a)
    assert view.kind == "host_player"


def test_allowed_commands_follow_the_state() -> None:
    sc = Scenario(rounds=2)
    host = sc.s.players[sc.host_id]
    assert "start_game" in permissions.allowed(sc.s, host)
    r = sc.to_open()
    allowed = set(permissions.allowed(sc.s, host))
    assert {"replay", "stop", "add_time", "close", "skip", "end_game"} <= allowed
    assert "publish" not in allowed
    sc.on_round("close")
    assert {"score_draft", "publish"} <= set(permissions.allowed(sc.s, host))
    sc.publish()
    allowed = set(permissions.allowed(sc.s, host))
    assert {"next", "undo_publish"} <= allowed
    assert "to_final_review" not in allowed
    assert r.number == 1


def test_host_view_lists_allowed_commands() -> None:
    sc = Scenario()
    sc.to_open()
    view = sc.host_view()
    assert view.kind == "host_player"
    assert "close" in view.host.commands  # type: ignore[union-attr]


def test_kick_self_is_invalid_and_kick_removes() -> None:
    sc = Scenario()
    assert sc.host_id is not None
    assert sc.on_phase("kick", {"player_id": sc.host_id}).error is ErrorCode.INVALID_ARGS
    target = sc.player_ids[0]
    outcome = sc.on_phase("kick", {"player_id": target})
    assert outcome.error is None
    assert sc.on_phase("kick", {"player_id": target}).error is ErrorCode.STALE_COMMAND
    assert not sc.engine.player_exists(target)
