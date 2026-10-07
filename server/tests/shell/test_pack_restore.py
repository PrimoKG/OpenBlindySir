"""Restore exact state and Bridge identity; interrupted staging leaves live data intact."""

from pathlib import Path

import pytest

import restore_pack_state as tool


def fixture(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "backup"
    source.mkdir()
    (source / "session.json").write_text("synthetic backup", encoding="utf-8")
    target = tmp_path / "volume/state"
    target.mkdir(parents=True)
    (target / "session.json").write_text("synthetic current", encoding="utf-8")
    (target / "later-secret.json").write_text("synthetic obsolete", encoding="utf-8")
    return source, target


def test_directory_restore_does_not_merge_later_state(tmp_path: Path) -> None:
    source, target = fixture(tmp_path)
    tool.restore(source, target, directory=True)
    assert (target / "session.json").read_text(encoding="utf-8") == "synthetic backup"
    assert sorted(p.name for p in target.iterdir()) == ["session.json"]
    assert sorted(p.name for p in target.parent.iterdir()) == ["state"]


@pytest.mark.parametrize("failure", ["copy", "install"])
def test_interrupted_restore_keeps_original_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    source, target = fixture(tmp_path)
    if failure == "copy":

        def fail_copy(src: Path, dst: Path) -> None:
            dst.mkdir()
            (dst / "partial").write_bytes(b"synthetic partial")
            raise OSError("synthetic disk failure")

        monkeypatch.setattr(tool.shutil, "copytree", fail_copy)
    else:
        rename = tool.os.replace

        def fail_install(src: Path, dst: Path) -> None:
            if src.name.startswith(".restore-"):
                raise OSError("synthetic install failure")
            rename(src, dst)

        monkeypatch.setattr(tool.os, "replace", fail_install)
    with pytest.raises(OSError, match="synthetic"):
        tool.restore(source, target, directory=True)
    assert (target / "session.json").read_text(encoding="utf-8") == "synthetic current"
    assert (target / "later-secret.json").is_file()
    assert sorted(p.name for p in target.parent.iterdir()) == ["state"]


def test_bridge_identity_is_atomically_restored(tmp_path: Path) -> None:
    source = tmp_path / "bridge-backup.toml"
    source.write_text("synthetic stable identity", encoding="utf-8")
    target = tmp_path / "config.toml"
    target.write_text("synthetic later identity", encoding="utf-8")
    tool.restore(source, target, directory=False)
    assert target.read_text(encoding="utf-8") == "synthetic stable identity"


def test_unexpected_target_is_rejected_before_mutation(tmp_path: Path) -> None:
    source, target = fixture(tmp_path)
    with pytest.raises(ValueError, match="unexpected restore target"):
        tool.restore(source, target.parent / "unrelated", directory=True)
    assert (target / "session.json").read_text(encoding="utf-8") == "synthetic current"
