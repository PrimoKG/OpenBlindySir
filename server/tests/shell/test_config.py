"""Start-up refusal rules (spec §12, §15)."""

from pathlib import Path

import pytest

from openblindysir_server.cli import gen_secrets, main
from openblindysir_server.config import ConfigError, load_settings

GOOD = {
    "BLIND_PASSWORD": "example-blind-password",
    "HOST_PASSWORD": "example-host-password",
    "BRIDGE_SECRET": "example-bridge-secret-0123456789abcdef",
    "DOMAIN": "openblindysir.example.com",
}


def problems(env: dict[str, str]) -> set[tuple[str, str]]:
    with pytest.raises(ConfigError) as info:
        load_settings(env, dotenv=None)
    return set(info.value.problems)


def test_valid_configuration() -> None:
    settings = load_settings(GOOD, dotenv=None)
    assert settings.domain == "openblindysir.example.com"
    assert not settings.dev_mode


@pytest.mark.parametrize("var", ["BLIND_PASSWORD", "HOST_PASSWORD", "BRIDGE_SECRET"])
def test_missing_secret_refused(var: str) -> None:
    env = {k: v for k, v in GOOD.items() if k != var}
    assert (var, "missing") in problems(env)


def test_weak_values_refused_in_production() -> None:
    env = {**GOOD, "BLIND_PASSWORD": "example", "BRIDGE_SECRET": "changeme"}  # hygiene: allow
    found = problems(env)
    assert ("BLIND_PASSWORD", "too_short") in found
    assert ("BRIDGE_SECRET", "weak_value") in found


def test_weak_values_tolerated_in_dev_mode() -> None:
    env = {
        "BLIND_PASSWORD": "example",
        "HOST_PASSWORD": "example-h",
        "BRIDGE_SECRET": "example-s",
        "DEV_MODE": "1",
    }
    settings = load_settings(env, dotenv=None)
    assert settings.dev_mode
    assert settings.warnings


def test_host_password_equal_to_blind_password_always_refused() -> None:
    env = {**GOOD, "HOST_PASSWORD": GOOD["BLIND_PASSWORD"], "DEV_MODE": "1", "DOMAIN": "localhost"}
    assert ("HOST_PASSWORD", "equals_blind_password") in problems(env)


def test_dev_mode_refused_with_public_domain() -> None:
    assert ("DEV_MODE", "forbidden_with_public_domain") in problems({**GOOD, "DEV_MODE": "true"})


@pytest.mark.parametrize("value", ["*", "0.0.0.0/0", "not-a-network"])
def test_trusted_proxies_validated(value: str) -> None:
    assert any(var == "TRUSTED_PROXIES" for var, _ in problems({**GOOD, "TRUSTED_PROXIES": value}))


def test_bounds_checked() -> None:
    found = problems({**GOOD, "CLIP_MIN_S": "50", "CLIP_MAX_S": "20", "MAX_PLAYERS": "1"})
    assert ("CLIP_MIN_S", "greater_than_clip_max") in found
    assert ("MAX_PLAYERS", "out_of_range") in found


def test_refusal_exit_code_and_no_value_printed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    for key in [*GOOD, "DEV_MODE"]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BLIND_PASSWORD", "tiny-secret")
    monkeypatch.chdir(tmp_path)  # no local .env
    assert main(["serve"]) == 2
    err = capsys.readouterr().err
    assert "config_error var=BLIND_PASSWORD reason=too_short" in err
    assert "tiny-secret" not in err


def test_gen_secrets_are_accepted() -> None:
    lines = dict(line.split("=", 1) for line in gen_secrets().strip().splitlines())
    settings = load_settings({**lines, "DOMAIN": "example.org"}, dotenv=None)
    assert settings.host_password != settings.blind_password
    assert len(settings.bridge_secret) >= 32
