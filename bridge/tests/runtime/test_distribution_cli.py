"""The standalone CLI: no implicit work, masked input, private atomic configuration."""

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from openblindysir_bridge import cli, diagnostics, ffmpeg
from openblindysir_bridge.config import default_config_path, load_config, read_config, write_config

SECRET = "SYNTHETIC-TEST-ONLY-" + "x" * 32


def config(tmp_path: Path):
    cfg = load_config(
        cli.build_parser().parse_args(["--config", str(tmp_path / "config.toml")]),
        env={},
        persist_identity=False,
    )
    return replace(
        cfg, server_url="https://example.com", music_dir=tmp_path, secret=SECRET, name="Musique"
    )


@pytest.mark.parametrize("option", ["--help", "--version"])
def test_help_and_version_neither_write_nor_discover(tmp_path, monkeypatch, capsys, option):
    def forbidden(*args, **kwargs):
        raise AssertionError("no setup side effect")

    monkeypatch.setattr(cli, "load_config", forbidden)
    monkeypatch.setattr(ffmpeg, "discover", forbidden)
    with pytest.raises(SystemExit) as error:
        cli.main([option])
    assert error.value.code == 0
    assert "OpenBlindySir" in capsys.readouterr().out
    assert not (tmp_path / "config.toml").exists()


def test_atomic_config_round_trips_controls_and_keeps_private_backup(tmp_path):
    path = tmp_path / "config.toml"
    write_config(path, {"secret": SECRET, "name": 'ligne\n"deux"'})
    previous = path.read_bytes()
    write_config(path, {"secret": "NEW-" + SECRET, "name": "Bridge"}, backup=True)
    (backup,) = tmp_path.glob("config.toml.bak-*")
    assert backup.read_bytes() == previous
    assert read_config(path)["secret"] == "NEW-" + SECRET
    assert not list(tmp_path.glob(".config-*.tmp"))
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
        assert backup.stat().st_mode & 0o777 == 0o600


def test_failed_private_write_does_not_replace_configuration(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    write_config(path, {"secret": SECRET})
    previous = path.read_bytes()

    def denied(path):
        raise OSError("private permissions unavailable")

    monkeypatch.setattr("openblindysir_bridge.config.protect_file", denied)
    with pytest.raises(OSError, match="private permissions"):
        write_config(path, {"secret": "NEW"})
    assert path.read_bytes() == previous
    assert not list(tmp_path.glob(".config-*.tmp"))


def test_bad_configuration_is_safe_and_has_usage_exit(tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text(f"secret = {SECRET}\n", encoding="utf-8")
    assert cli.main(["check-config", "--config", str(path)]) == 2
    text = str(capsys.readouterr())
    assert SECRET not in text
    assert str(tmp_path) not in text
    assert "Traceback" not in text


def test_environment_overrides_file_without_changing_persistent_values(tmp_path):
    path = tmp_path / "config.toml"
    write_config(path, {"secret": SECRET, "name": "Original"})
    ns = cli.build_parser().parse_args(["--config", str(path), "--name", "Argument"])
    cfg = load_config(ns, env={"OPENBLINDYSIR_BRIDGE_NAME": "Environment"})
    assert cfg.name == "Argument"
    assert read_config(path)["name"] == "Original"
    assert load_config(ns, env={}).bridge_id == cfg.bridge_id


def test_wizard_cancellation_preserves_configuration_and_masks_secret(
    tmp_path, monkeypatch, capsys
):
    cfg = config(tmp_path)
    write_config(cfg.config_path, {"secret": SECRET, "name": "Previous"})
    previous = cfg.config_path.read_bytes()
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: SECRET)
    answers = iter(["", "", "", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert cli.cmd_init(cfg) == 130
    assert cfg.config_path.read_bytes() == previous
    assert SECRET not in capsys.readouterr().out


def test_noninteractive_wizard_does_not_write(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    assert cli.cmd_init(cfg) == 2
    assert not cfg.config_path.exists()


def test_wizard_saves_only_after_confirmation_and_can_defer_scan(tmp_path, monkeypatch, capsys):
    cfg = config(tmp_path)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: SECRET)
    answers = iter(["", "", "", "o", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(
        cli, "cmd_doctor", lambda *args, **kwargs: pytest.fail("scan not authorized")
    )
    assert cli.cmd_init(cfg) == 0
    assert read_config(cfg.config_path)["secret"] == SECRET
    assert SECRET not in capsys.readouterr().out


def test_diagnostic_report_excludes_all_private_values(tmp_path):
    cfg = config(tmp_path)
    report = diagnostics.diagnostic_report(cfg, config_ok=True, info=None)
    text = json.dumps(report)
    for private in (SECRET, str(tmp_path), "example.com", cfg.bridge_id, cfg.name):
        assert private not in text
    assert report["secret_configured"] is True


@pytest.mark.parametrize("secret", ["short", "a" * 32 + "\n", "a" * 32 + "\u202e"])
def test_invalid_secrets_rejected(tmp_path, secret):
    with pytest.raises(ValueError, match="secret"):
        diagnostics.validate_config(replace(config(tmp_path), secret=secret))


def test_doctor_without_connect_never_scans_or_connects(tmp_path, monkeypatch, capsys):
    cfg = config(tmp_path)
    monkeypatch.setattr(ffmpeg, "discover", lambda *args: ffmpeg.FfmpegTools("ffmpeg", "ffprobe"))
    monkeypatch.setattr(
        ffmpeg, "check", lambda *args: ffmpeg.FfmpegInfo("FFmpeg test", frozenset({"aac"}))
    )
    monkeypatch.setattr(cli, "scan_sources", lambda *args: pytest.fail("no implicit scan"))
    assert cli.cmd_doctor(cfg, connect=False, as_json=True) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["connection"] == "not_checked"
    assert report["tracks"] is None


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
def test_platform_configuration_locations(tmp_path, monkeypatch, platform):
    monkeypatch.setattr("openblindysir_bridge.config.sys.platform", platform)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "XDG"))
    path = default_config_path()
    assert path.is_absolute()
    assert path.name == "config.toml"
    assert (
        "Roaming"
        if platform == "win32"
        else "Application Support"
        if platform == "darwin"
        else "XDG"
    ) in str(path)
