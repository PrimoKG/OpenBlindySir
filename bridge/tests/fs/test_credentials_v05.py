"""Provisioned identity wins over stale bootstrap values without changing filesystem roots."""

import argparse
import tomllib

import pytest

from openblindysir_bridge.config import load_config, persist_bridge_id, write_config

ID = "12345678-1234-1234-1234-123456789abd"
SECRET = "synthetic-distinct-bridge-credential-0123456789"


def test_credentials_import_stable_identity_and_override_stale_secret(tmp_path):
    config = tmp_path / "config.toml"
    credentials = tmp_path / "issued.toml"
    music = tmp_path / "music"
    music.mkdir()
    write_config(
        config, {"bridge_id": "12345678-1234-1234-1234-123456789abc", "music_dir": str(music)}
    )
    write_config(credentials, {"bridge_id": ID, "name": "Second device", "secret": SECRET})
    args = argparse.Namespace(
        config=str(config),
        credentials=str(credentials),
        secret="stale-command-secret",
        name="Stale name",
    )
    cfg = load_config(
        args, {"OPENBLINDYSIR_BRIDGE_SECRET": "stale-bootstrap-secret"}, persist_identity=False
    )
    assert cfg.bridge_id == ID
    assert cfg.secret == SECRET
    assert cfg.name == "Second device"
    assert cfg.music_dir == music
    persist_bridge_id(cfg)
    assert tomllib.loads(config.read_text())["bridge_id"] == ID
    assert SECRET not in config.read_text()
    assert load_config(args, {}, persist_identity=False).bridge_id == ID


@pytest.mark.parametrize(
    "malformed",
    [
        "bridge_id = 'bad'\nname='Test'\nsecret='synthetic'",
        "secret='synthetic'",
        "bridge_id='" + ID + "'\nname='Test'\nsecret='synthetic'\nroot='/outside'",
    ],
)
def test_credential_file_is_closed_and_identity_cannot_be_replaced_silently(tmp_path, malformed):
    credentials = tmp_path / "issued.toml"
    credentials.write_text(malformed, encoding="utf-8")
    args = argparse.Namespace(config=str(tmp_path / "config.toml"), credentials=str(credentials))
    with pytest.raises(ValueError, match=r"credential|identity"):
        load_config(args, {}, persist_identity=False)
    assert not (tmp_path / "config.toml").exists()
