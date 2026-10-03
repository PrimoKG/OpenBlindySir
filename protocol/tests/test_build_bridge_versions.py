"""A cached editable version cannot silently contaminate native provenance."""

import pytest

from build_bridge import require_runtime_versions


@pytest.mark.parametrize("stale", ["openblindysir-bridge", "openblindysir-protocol"])
def test_native_build_refuses_stale_installed_workspace_metadata(monkeypatch, stale):
    monkeypatch.setattr(
        "build_bridge.importlib.metadata.version",
        lambda name: "0.3.0.dev0" if name == stale else "0.5.0.dev0",
    )
    with pytest.raises(ValueError, match=f"{stale} installation is stale"):
        require_runtime_versions("0.5.0.dev0")


def test_matching_native_runtime_versions_are_accepted(monkeypatch):
    monkeypatch.setattr("build_bridge.importlib.metadata.version", lambda name: "0.5.0.dev0")
    require_runtime_versions("0.5.0.dev0")
