"""Credential persistence failures and competing processes must not undo revocation."""

import copy
import json
import os
import subprocess
import sys
from unittest.mock import Mock

import pytest
from conftest import BRIDGE_ID, SECRET
from test_bridge_cli_v05 import environment

from openblindysir_server import cli
from openblindysir_server.auth import bridges
from openblindysir_server.auth.bridges import BridgeCredentials
from openblindysir_server.cli import main
from openblindysir_server.private_files import create_private_file, private_file_lock

SECOND = "12345678-1234-1234-1234-123456789abd"
OTHER = "synthetic-second-secret-0123456789abcdef"
ROTATED = "synthetic-rotated-secret-0123456789abcdef"


@pytest.mark.parametrize("action", ["rotate", "revoke", "bind"])
def test_failed_registry_write_keeps_memory_and_restart_in_agreement(tmp_path, monkeypatch, action):
    path = tmp_path / "credentials.json"
    registry = BridgeCredentials(path, SECRET)
    if action != "bind":
        assert registry.authorize(BRIDGE_ID, SECRET, bind=True)
    previous = copy.deepcopy(registry.data)
    operation = {
        "rotate": lambda: registry.replace(BRIDGE_ID, "Synthetic", ROTATED),
        "revoke": lambda: registry.revoke(BRIDGE_ID),
        "bind": lambda: registry.authorize(BRIDGE_ID, SECRET, bind=True),
    }[action]
    with monkeypatch.context() as patch:
        patch.setattr(bridges, "atomic_private_write", Mock(side_effect=OSError("synthetic disk")))
        with pytest.raises(OSError, match="synthetic"):
            operation()
    assert registry.data == previous
    restarted = BridgeCredentials(path, SECRET)
    for identity in (BRIDGE_ID, SECOND):
        for secret in (SECRET, ROTATED):
            assert registry.authorize(identity, secret) == restarted.authorize(identity, secret)
    assert not registry.authorize(BRIDGE_ID, ROTATED)
    if action == "bind":
        assert registry.authorize(SECOND, SECRET, bind=True)


def test_failure_after_replacement_rereads_the_committed_state(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    registry = BridgeCredentials(path)
    registry.replace(BRIDGE_ID, "Synthetic", SECRET)
    write = bridges.atomic_private_write

    def fail_after_write(target, data):
        write(target, data)
        raise OSError("synthetic post-replacement failure")

    monkeypatch.setattr(bridges, "atomic_private_write", fail_after_write)
    with pytest.raises(OSError, match="synthetic"):
        registry.revoke(BRIDGE_ID)
    assert not registry.authorize(BRIDGE_ID, SECRET)
    assert not BridgeCredentials(path).authorize(BRIDGE_ID, SECRET)
    path.unlink()
    with pytest.raises(ValueError, match="disappeared"):
        registry.recognizes(SECRET)


def test_other_process_cannot_overwrite_a_pending_revocation_and_can_retry(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    registry = BridgeCredentials(path)
    registry.replace(BRIDGE_ID, "First", SECRET)
    registry.replace(SECOND, "Second", OTHER)
    write = bridges.atomic_private_write
    script = (
        "from pathlib import Path; import sys; "
        "from openblindysir_server.auth.bridges import BridgeCredentials\n"
        "try:\n"
        "    BridgeCredentials(Path(sys.argv[1])).replace(sys.argv[2], 'Second', sys.argv[3])\n"
        "except OSError:\n"
        "    sys.exit(7)\n"
    )

    def rotate_other_process():
        return subprocess.run(
            [sys.executable, "-c", script, str(path), SECOND, ROTATED],
            capture_output=True,
            timeout=15,
            check=False,
        )

    def during_revocation(target, data):
        competing = rotate_other_process()
        assert competing.returncode == 7, competing.stderr.decode()
        assert competing.stdout == b""
        write(target, data)

    with monkeypatch.context() as patch:
        patch.setattr(bridges, "atomic_private_write", during_revocation)
        assert registry.revoke(BRIDGE_ID)
    assert rotate_other_process().returncode == 0
    restarted = BridgeCredentials(path)
    assert not restarted.authorize(BRIDGE_ID, SECRET)
    assert restarted.authorize(SECOND, ROTATED)
    assert not restarted.authorize(SECOND, OTHER)


def test_same_size_and_mtime_replacement_is_not_cached(tmp_path):
    path = tmp_path / "credentials.json"
    registry = BridgeCredentials(path)
    registry.replace(BRIDGE_ID, "Synthetic", SECRET)
    assert registry.authorize(BRIDGE_ID, SECRET)
    previous = path.stat()
    replacement = path.with_name("replacement.json")
    data = json.loads(path.read_bytes())
    data["bridges"][BRIDGE_ID]["secret_hash"] = bridges.secret_hash(ROTATED)
    replacement.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert replacement.stat().st_size == previous.st_size
    os.utime(replacement, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    os.replace(replacement, path)
    assert not registry.authorize(BRIDGE_ID, SECRET)
    assert registry.authorize(BRIDGE_ID, ROTATED)


@pytest.mark.parametrize("value", [42, False, [], {}, "not-an-identity"])
def test_malformed_bootstrap_identity_is_a_controlled_failure(tmp_path, value):
    path = tmp_path / "credentials.json"
    data = BridgeCredentials(None).data
    data["bootstrap_id"] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=r"identity|UUID"):
        BridgeCredentials(path)


@pytest.mark.parametrize("name", ["\ud800", "\u2028", "\u200b", " Synthetic ", ""])
def test_malformed_registry_names_are_refused_before_use(tmp_path, name):
    path = tmp_path / "credentials.json"
    registry = BridgeCredentials(path)
    registry.replace(BRIDGE_ID, "Synthetic", SECRET)
    data = registry.data
    data["bridges"][BRIDGE_ID]["name"] = name
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=r"nickname_invalid|Bridge name"):
        BridgeCredentials(path)


def test_failed_credential_issuance_removes_unusable_raw_secret(tmp_path, monkeypatch, capsys):
    environment(monkeypatch, tmp_path)
    output = tmp_path / "issued.toml"
    registry_path = tmp_path / "state" / "bridge-credentials.json"
    registry = BridgeCredentials(registry_path, SECRET)
    assert registry.authorize(BRIDGE_ID, SECRET, bind=True)
    previous = registry_path.read_bytes()
    write = Mock(side_effect=OSError("synthetic disk"))
    monkeypatch.setattr(bridges, "atomic_private_write", write)
    assert main(["bridge-credential", "--bridge-id", BRIDGE_ID, "--output", str(output)]) == 2
    assert not output.exists()
    assert registry_path.read_bytes() == previous
    write.assert_called_once()
    assert SECRET not in capsys.readouterr().err


def test_private_issuance_never_replaces_a_concurrent_creation(tmp_path):
    output = tmp_path / "issued.toml"
    create_private_file(output, b"synthetic original")
    with pytest.raises(FileExistsError):
        create_private_file(output, b"synthetic replacement")
    assert output.read_bytes() == b"synthetic original"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["issued.toml"]


def test_cli_creation_race_preserves_the_other_file_and_existing_secret(tmp_path, monkeypatch):
    environment(monkeypatch, tmp_path)
    path = tmp_path / "state" / "bridge-credentials.json"
    registry = BridgeCredentials(path, SECRET)
    assert registry.authorize(BRIDGE_ID, SECRET, bind=True)
    output = tmp_path / "issued.toml"

    def concurrently_created(target, data):
        target.write_bytes(b"synthetic unrelated file")
        create_private_file(target, data)

    monkeypatch.setattr(cli, "create_private_file", concurrently_created)
    assert main(["bridge-credential", "--bridge-id", BRIDGE_ID, "--output", str(output)]) == 2
    assert output.read_bytes() == b"synthetic unrelated file"
    assert registry.authorize(BRIDGE_ID, SECRET)


@pytest.mark.parametrize(
    "filename",
    ["bridge-credentials.json", "bridge-credentials.lock", "session.json", "session.previous.json"],
)
def test_cli_refuses_to_write_a_raw_secret_into_a_managed_state_file(
    tmp_path, monkeypatch, filename
):
    environment(monkeypatch, tmp_path)
    output = tmp_path / "state" / filename
    assert main(["bridge-credential", "--bridge-id", BRIDGE_ID, "--output", str(output)]) == 2
    assert not output.exists()


def test_duplicate_revocation_field_cannot_reactivate_a_registry_credential(tmp_path):
    path = tmp_path / "credentials.json"
    registry = BridgeCredentials(path)
    registry.replace(BRIDGE_ID, "Synthetic", SECRET)
    registry.revoke(BRIDGE_ID)
    path.write_text(
        path.read_text().replace('"revoked": true', '"revoked": true, "revoked": false'),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        registry.authorize(BRIDGE_ID, SECRET)


def test_credential_lock_is_released_after_process_termination(tmp_path):
    path = tmp_path / "credentials.json"
    script = (
        "from pathlib import Path; import sys; "
        "from openblindysir_server.private_files import private_file_lock\n"
        "with private_file_lock(Path(sys.argv[1])):\n"
        "    print('locked', flush=True)\n"
        "    sys.stdin.read()\n"
    )
    with subprocess.Popen(
        [sys.executable, "-c", script, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            assert process.stdout is not None
            assert process.stdout.readline().strip() == "locked"
            with pytest.raises(OSError, match=r"."), private_file_lock(path):
                pytest.fail("competing process lock should refuse")
        finally:
            process.kill()
            process.wait(timeout=10)
    with private_file_lock(path):
        pass
    assert path.with_suffix(".lock").is_file()
