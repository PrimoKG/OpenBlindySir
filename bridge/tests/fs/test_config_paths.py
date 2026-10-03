"""The configured root and secret file cannot be reached through linked ancestors."""

import sys
from pathlib import Path

import pytest

from openblindysir_bridge.config import read_config, write_config
from openblindysir_bridge.sandbox import Sandbox


def linked(link: Path, target: Path) -> None:
    if sys.platform == "win32":
        import _winapi  # noqa: PLC0415

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def test_configuration_refuses_linked_parent_before_read_or_backup(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "config.toml").write_text('secret = "synthetic-original"\n')
    link = tmp_path / "link"
    linked(link, target)
    with pytest.raises(ValueError, match="link"):
        read_config(link / "config.toml")
    with pytest.raises(ValueError, match="link"):
        write_config(link / "config.toml", {"secret": "synthetic-new"}, backup=True)
    assert sorted(p.name for p in target.iterdir()) == ["config.toml"]
    assert "synthetic-original" in (target / "config.toml").read_text()


@pytest.mark.parametrize("child", [False, True])
def test_sandbox_refuses_linked_root_or_ancestor(tmp_path: Path, child: bool) -> None:
    target = tmp_path / "target"
    (target / "music").mkdir(parents=True)
    link = tmp_path / "link"
    linked(link, target)
    with pytest.raises(ValueError, match="link"):
        Sandbox(str(link / "music" if child else link))
