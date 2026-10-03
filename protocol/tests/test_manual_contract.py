"""Malformed manual commands cannot bypass identity, revision or phase checks."""

import pytest
from pydantic import TypeAdapter, ValidationError

from openblindysir_protocol.host_commands import HostCommand

COMMAND = TypeAdapter(HostCommand)
VALID = {"round_number": 1, "expected_revision": 0, "bridge_id": None, "track_id": None}


@pytest.mark.parametrize(
    "patch",
    [
        {"round_number": 0},
        {"round_number": 101},
        {"round_number": True},
        {"expected_revision": -1},
        {"bridge_id": "not-a-uuid"},
        {"track_id": "t_aaaaaaaaaaaaaaaaaaaaaaaa"},
        {"path": "../private"},
    ],
)
def test_invalid_manual_args_rejected(patch):
    with pytest.raises(ValidationError):
        COMMAND.validate_python(
            {
                "t": "HOST",
                "cmd": "select_track",
                "expected_phase": "LOBBY",
                "args": VALID | patch,
            }
        )


def test_manual_not_in_final_phase_contract():
    with pytest.raises(ValidationError):
        COMMAND.validate_python(
            {
                "t": "HOST",
                "cmd": "select_track",
                "expected_phase": "FINAL_RESULTS",
                "args": VALID,
            }
        )
