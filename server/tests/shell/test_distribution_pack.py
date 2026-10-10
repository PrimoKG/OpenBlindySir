"""The offline installer must track the current application compatibility."""

import pytest

import distribution_pack
from openblindysir_protocol.version import PROTOCOL_VERSION


def test_pack_accepts_the_current_protocol_without_a_hardcoded_release(monkeypatch):
    calls = []

    def run(*args):
        calls.append(args)
        return str(PROTOCOL_VERSION)

    monkeypatch.setattr(distribution_pack, "run", run)
    assert distribution_pack.image_protocol("example/app:candidate") == PROTOCOL_VERSION
    assert "--read-only" in calls[0]
    assert calls[0][calls[0].index("--network") + 1] == "none"


@pytest.mark.parametrize(
    "actual", [str(PROTOCOL_VERSION - 1), str(PROTOCOL_VERSION + 1), "unknown"]
)
def test_pack_refuses_incompatible_images_before_distribution(monkeypatch, actual):
    monkeypatch.setattr(distribution_pack, "run", lambda *args: actual)
    with pytest.raises(ValueError, match="Incompatible image protocol"):
        distribution_pack.image_protocol("example/app:candidate")
