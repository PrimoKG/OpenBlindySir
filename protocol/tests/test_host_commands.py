"""HOST commands: canonical command set, each with one idempotency key."""

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from openblindysir_protocol.client import ClientMessage
from openblindysir_protocol.host_commands import HOST_COMMAND_EXAMPLES, HOST_COMMAND_NAMES

CLIENT = TypeAdapter(ClientMessage)

SPEC_COMMANDS = {
    "select_track",
    "configure",
    "set_mode",
    "start_game",
    "new_game",
    "end_game",
    "end_session",
    "next",
    "force_start",
    "replay",
    "stop",
    "skip",
    "add_time",
    "close",
    "score_draft",
    "publish",
    "undo_publish",
    "adjust",
    "to_final_review",
    "final_set",
    "final_reset",
    "final_validate",
    "kick",
    "rename",
    "pause",
    "resume",
    "track_metadata",
    "participation",
    "join_lock",
}


def host(cmd: str, **fields: object) -> object:
    return CLIENT.validate_json(json.dumps({"t": "HOST", "cmd": cmd, **fields}))


def test_union_has_exactly_the_29_spec_commands() -> None:
    assert len(HOST_COMMAND_NAMES) == 29
    assert set(HOST_COMMAND_NAMES) == SPEC_COMMANDS


@pytest.mark.parametrize("cmd", sorted(SPEC_COMMANDS))
def test_every_command_has_a_valid_example(cmd: str) -> None:
    parsed = host(cmd, **HOST_COMMAND_EXAMPLES[cmd])
    assert getattr(parsed, "cmd") == cmd  # noqa: B009 - union member


@pytest.mark.parametrize("cmd", sorted(SPEC_COMMANDS))
def test_every_command_requires_exactly_one_idempotency_key(cmd: str) -> None:
    example = dict(HOST_COMMAND_EXAMPLES[cmd])
    key = "round_id" if "round_id" in example else "expected_phase"
    other = "expected_phase" if key == "round_id" else "round_id"
    missing = {k: v for k, v in example.items() if k != key}
    with pytest.raises(ValidationError):
        host(cmd, **missing)
    extra_value = "LOBBY" if other == "expected_phase" else "r_round01"
    with pytest.raises(ValidationError):
        host(cmd, **example, **{other: extra_value})


def test_final_validate_only_in_final_score_review() -> None:
    with pytest.raises(ValidationError):
        host("final_validate", expected_phase="IN_GAME", args={})


def test_adjust_rejects_zero_delta_and_requires_op_id() -> None:
    base = {"player_id": "p_player01", "op_id": "op-000001"}
    with pytest.raises(ValidationError):
        host("adjust", expected_phase="IN_GAME", args={**base, "delta": 0})
    with pytest.raises(ValidationError):
        host("adjust", expected_phase="IN_GAME", args={"player_id": "p_player01", "delta": 1})


@pytest.mark.parametrize("points", [-1001, 1001])
def test_points_bounded(points: int) -> None:
    with pytest.raises(ValidationError):
        host(
            "score_draft", round_id="r_round01", args={"player_id": "p_player01", "points": points}
        )


def test_final_set_accepts_zero_to_clear() -> None:
    host(
        "final_set", expected_phase="FINAL_SCORE_REVIEW", args={"player_id": "p_x0001", "delta": 0}
    )


def test_configure_rejects_unknown_setting() -> None:
    with pytest.raises(ValidationError):
        host("configure", expected_phase="LOBBY", args={"speed_bonus": True})


@pytest.mark.parametrize("prefix", ["..", "a/../b", "/abs", "a/", "a\\b", "a//b"])
def test_source_prefix_rejects_unsafe_paths(prefix: str) -> None:
    source = {"bridge_id": "12345678-1234-1234-1234-123456789abc", "folder_prefix": prefix}
    with pytest.raises(ValidationError):
        host("configure", expected_phase="LOBBY", args={"sources": [source]})


def test_source_prefix_empty_means_root() -> None:
    source = {"bridge_id": "12345678-1234-1234-1234-123456789abc", "folder_prefix": ""}
    host("configure", expected_phase="LOBBY", args={"sources": [source]})
