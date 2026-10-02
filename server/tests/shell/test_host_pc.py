"""PC hosting keeps HTTPS, exact origins, strong secrets and loopback upstreams."""

import subprocess
from pathlib import Path

import pytest

from host_pc import HostingError, address_for_mode, hosting_plan, init_config, run_plan
from openblindysir_server.config import ConfigError, load_settings, read_dotenv
from openblindysir_server.security import allowed_origins

GOOD = {
    "BLIND_PASSWORD": "example-blind-password",
    "HOST_PASSWORD": "example-host-password",
    "BRIDGE_SECRET": "example-bridge-secret-0123456789abcdef",
    "DOMAIN": "192.168.1.42:8443",
}


@pytest.fixture
def built_ui(tmp_path: Path) -> Path:
    static = tmp_path / "web" / "dist"
    static.mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>Example</title>")
    return tmp_path


@pytest.mark.parametrize(
    ("address", "mode", "authority", "bind"),
    [
        ("192.168.1.42:8443", "private", "192.168.1.42:8443", "192.168.1.42"),
        ("25.1.2.3:8443", "private", "25.1.2.3:8443", "25.1.2.3"),
        ("localhost:8443", "private", "localhost:8443", "127.0.0.1"),
        ("[::1]:8443", "private", "[::1]:8443", "::1"),
        ("192.168.1.42:443", "private", "192.168.1.42", "192.168.1.42"),
        ("Blind.Example.com:443", "public", "blind.example.com", "blind.example.com"),
    ],
)
def test_canonical_addresses(address: str, mode: str, authority: str, bind: str) -> None:
    assert address_for_mode(address, mode) == (authority, bind)


@pytest.mark.parametrize(
    ("address", "mode"),
    [
        ("https://192.168.1.42:8443", "private"),
        ("192.168.1.42:8443/path", "private"),
        ("example-user@192.168.1.42", "private"),
        ("192.168.1.42:0", "private"),
        ("192.168.1.42:70000", "private"),
        ("0.0.0.0:8443", "private"),
        ("[::]:8443", "private"),
        ("224.0.0.1:8443", "private"),
        ("blind.example.com", "private"),
        ("blind.example.com {", "public"),
        ("blind..example.com", "public"),
        ("192.168.1.42", "public"),
        ("localhost", "public"),
        ("blind.example.com:8443", "public"),
        ("192.168.1.42:8443", "unknown"),
    ],
)
def test_invalid_or_ambiguous_addresses_are_refused(address: str, mode: str) -> None:
    with pytest.raises(HostingError):
        address_for_mode(address, mode)


def test_init_creates_production_configuration_without_bom(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    init_config(path, "192.168.1.42:8443", "private")
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")
    values = read_dotenv(path)
    settings = load_settings(values, dotenv=None)
    assert not settings.dev_mode
    assert settings.host == "127.0.0.1"
    assert settings.blind_password != settings.host_password
    assert allowed_origins(settings) == {"https://192.168.1.42:8443"}
    assert values["PC_HOSTING_MODE"] == "private"


def test_init_never_overwrites_existing_configuration(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("example-existing-config")
    with pytest.raises(HostingError, match="existe déjà"):
        init_config(path, "localhost:8443", "private")
    assert path.read_text() == "example-existing-config"


def test_private_plan_binds_only_selected_interface_and_trusts_only_loopback(
    built_ui: Path,
) -> None:
    plan = hosting_plan(built_ui, {**GOOD, "BIND_HOST": "0.0.0.0"}, None)
    settings = load_settings(plan.env, dotenv=None)
    assert settings.host == "127.0.0.1"
    assert settings.trusted_proxies == ("127.0.0.1/32", "::1/128")
    assert plan.env["OPENBLINDYSIR_CADDY_BIND"] == "192.168.1.42"
    assert plan.env["PORT"] == "8000"
    assert plan.caddyfile.name == "Caddyfile.pc.private"
    assert plan.root_certificate.is_relative_to(built_ui / ".local")
    assert allowed_origins(settings) == {plan.url}


def test_public_plan_uses_https_and_default_port_origin(built_ui: Path) -> None:
    plan = hosting_plan(
        built_ui, {**GOOD, "DOMAIN": "blind.example.com:443", "PC_HOSTING_MODE": "public"}, None
    )
    assert plan.url == "https://blind.example.com"
    assert plan.caddyfile.name == "Caddyfile.pc.public"
    assert allowed_origins(load_settings(plan.env, dotenv=None)) == {plan.url}


@pytest.mark.parametrize("dev", ["1", "true", "yes"])
def test_pc_hosting_does_not_turn_off_secure_cookies(built_ui: Path, dev: str) -> None:
    with pytest.raises(HostingError, match="DEV_MODE=0"):
        hosting_plan(built_ui, {**GOOD, "DEV_MODE": dev}, None)


def test_missing_ui_has_an_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(HostingError, match="run build"):
        hosting_plan(tmp_path, GOOD, None)


def test_missing_secrets_are_still_refused(built_ui: Path) -> None:
    with pytest.raises(ConfigError) as error:
        hosting_plan(built_ui, {"DOMAIN": "localhost:8443"}, None)
    assert ("BLIND_PASSWORD", "missing") in error.value.problems


def test_colliding_backend_and_https_ports_are_refused(built_ui: Path) -> None:
    with pytest.raises(HostingError, match="différent"):
        hosting_plan(built_ui, {**GOOD, "PORT": "8443"}, None)


def test_second_service_launch_failure_stops_first_service(
    built_ui: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = hosting_plan(built_ui, GOOD, None)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: None)
    running = True

    class Process:
        def poll(self) -> int | None:
            return None if running else 0

        def terminate(self) -> None:
            nonlocal running
            running = False

        def wait(self, **kwargs: object) -> int:
            return 0

    launches = 0

    def launch(*args: object, **kwargs: object) -> Process:
        nonlocal launches
        launches += 1
        if launches == 2:
            raise OSError("example-launch-failure")
        return Process()

    monkeypatch.setattr(subprocess, "Popen", launch)
    with pytest.raises(OSError, match="example-launch-failure"):
        run_plan(plan, "example-caddy")
    assert not running
