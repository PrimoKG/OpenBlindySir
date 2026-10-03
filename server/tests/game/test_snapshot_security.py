"""Snapshots and backups are private before their first byte and refuse filesystem links."""

import os
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from builders import Scenario

from openblindysir_server.auth.sessions import SessionRegistry
from openblindysir_server.persistence import SnapshotStore


def link_directory(link: Path, target: Path) -> None:
    if sys.platform == "win32":
        import _winapi  # noqa: PLC0415

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def test_linked_state_directory_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "elsewhere"
    real.mkdir()
    link = tmp_path / "state"
    link_directory(link, real)
    scenario = Scenario()
    with pytest.raises(ValueError, match="link"):
        SnapshotStore(link, ("synthetic",)).save(
            scenario.engine, SessionRegistry(1000), scenario.clock.now()
        )
    assert not list(real.iterdir())


def test_fixed_temporary_name_is_never_opened(tmp_path: Path) -> None:
    sentinel = tmp_path / "session.tmp"
    sentinel.write_bytes(b"synthetic-unrelated")
    scenario = Scenario()
    SnapshotStore(tmp_path, ("synthetic",)).save(
        scenario.engine, SessionRegistry(1000), scenario.clock.now()
    )
    assert sentinel.read_bytes() == b"synthetic-unrelated"


def test_permission_failure_preserves_snapshot_and_leaves_no_partial_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openblindysir_server import private_files  # noqa: PLC0415

    scenario = Scenario()
    store = SnapshotStore(tmp_path, ("synthetic",))
    sessions = SessionRegistry(1000)
    store.save(scenario.engine, sessions, scenario.clock.now())
    previous = (tmp_path / "session.json").read_bytes()
    monkeypatch.setattr(private_files, "protect_file", Mock(side_effect=OSError("synthetic")))
    with pytest.raises(OSError, match="synthetic"):
        store.save(scenario.engine, sessions, scenario.clock.now())
    assert (tmp_path / "session.json").read_bytes() == previous
    assert sorted(p.name for p in tmp_path.iterdir()) == ["session.json"]


@pytest.mark.skipif(os.name != "posix", reason="Unix permission bits")
def test_snapshots_and_backup_have_private_permissions(tmp_path: Path) -> None:
    scenario = Scenario()
    directory = tmp_path / "state"
    store = SnapshotStore(directory, ("synthetic",))
    sessions = SessionRegistry(1000)
    for _ in range(2):
        store.save(scenario.engine, sessions, scenario.clock.now())
    assert directory.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in directory.iterdir())
