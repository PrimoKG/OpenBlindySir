"""Operator commands produce private files and never expose credentials through output."""

import json
import tomllib

from conftest import BRIDGE_ID, SECRET

from openblindysir_server.auth.bridges import BridgeCredentials
from openblindysir_server.cli import main


def environment(monkeypatch, tmp_path):
    for key, value in {
        "DEV_MODE": "1",
        "DOMAIN": "localhost",
        "BLIND_PASSWORD": "example-player-password",
        "HOST_PASSWORD": "example-host-password",
        "BRIDGE_SECRET": SECRET,
        "STATE_DIR": str(tmp_path / "state"),
        "BRIDGE_SECRETS": "",
    }.items():
        monkeypatch.setenv(key, value)


def test_operator_issues_rotates_and_revokes_without_stdout_secret(tmp_path, monkeypatch, capsys):
    environment(monkeypatch, tmp_path)
    target = tmp_path / "private" / "issued.toml"
    args = [
        "bridge-credential",
        "--bridge-id",
        BRIDGE_ID,
        "--name",
        "Synthetic device",
        "--output",
        str(target),
    ]
    assert main(args) == 0
    issued = tomllib.loads(target.read_text())
    output = capsys.readouterr()
    assert issued["secret"] not in output.out + output.err
    registry = BridgeCredentials(tmp_path / "state" / "bridge-credentials.json", SECRET)
    assert registry.authorize(BRIDGE_ID, issued["secret"])
    assert main(args) == 2
    assert tomllib.loads(target.read_text()) == issued
    second = target.with_name("rotated.toml")
    assert main([*args[:-1], str(second)]) == 0
    rotated = tomllib.loads(second.read_text())
    assert rotated["bridge_id"] == BRIDGE_ID
    assert rotated["secret"] != issued["secret"]
    assert not registry.authorize(BRIDGE_ID, issued["secret"])
    assert registry.authorize(BRIDGE_ID, rotated["secret"])
    assert main(["bridge-revoke", "--bridge-id", BRIDGE_ID]) == 0
    assert not registry.authorize(BRIDGE_ID, rotated["secret"])
    text = json.dumps(registry.data)
    assert issued["secret"] not in text
    assert rotated["secret"] not in text
