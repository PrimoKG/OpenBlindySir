"""Compatibility messages expose a bounded range, never arbitrary remote close text."""

import pytest

from openblindysir_protocol.compatibility import Compatibility, mismatch_reason, required_range
from openblindysir_protocol.version import PROTOCOL_VERSION


def test_compatibility_versions_and_close_reason_are_consistent():
    info = Compatibility(server_version="0.5.0.dev0")
    assert info.protocol_min == info.protocol_max == PROTOCOL_VERSION == 12
    assert info.history_format == 2
    assert info.snapshot_format == 9
    assert required_range(mismatch_reason()) == (12, 12)


@pytest.mark.parametrize(
    "reason",
    [
        "protocol_mismatch",
        "protocol_mismatch;required=9..1",
        "protocol_mismatch;required=1..999999999999",
        "protocol_mismatch;required=7..7\nSECRET",
        "authentication",
        "\x1b[31msecret",
    ],
)
def test_close_text_is_not_propagated_to_cli(reason):
    assert required_range(reason) is None
