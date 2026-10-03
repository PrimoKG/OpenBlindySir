"""A second Bridge must never purge another live Bridge's audio or demo library."""

import os
from pathlib import Path

import pytest

from openblindysir_bridge import tempdirs


def test_live_process_probe_including_windows_is_read_only() -> None:
    assert tempdirs.process_running(os.getpid())
    assert tempdirs.process_running(-1)


def test_purge_keeps_live_and_unmarked_directories(tmp_path: Path) -> None:
    for name in ("openblindysir-bridge-live", "openblindysir-bridge-legacy"):
        (tmp_path / name).mkdir()
    live = tmp_path / "openblindysir-bridge-live"
    (live / tempdirs.OWNER).write_text(str(os.getpid()), encoding="ascii")
    (live / "example.txt").write_text("example", encoding="ascii")
    assert tempdirs.purge(tmp_path) == 0
    assert (live / "example.txt").is_file()
    assert (tmp_path / "openblindysir-bridge-legacy").is_dir()


def test_purge_removes_only_proven_dead_process_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dead = tmp_path / "openblindysir-bridge-dead"
    dead.mkdir()
    (dead / tempdirs.OWNER).write_text("123456", encoding="ascii")
    (dead / "example.txt").write_text("example", encoding="ascii")
    other = tmp_path / "unrelated"
    other.mkdir()
    monkeypatch.setattr(tempdirs, "process_running", lambda pid: False)
    assert tempdirs.purge(tmp_path) == 0
    assert not dead.exists()
    assert other.is_dir()
