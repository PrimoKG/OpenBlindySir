"""Credential mount safety checks support both Compose JSON serializers."""

import json
import os
import subprocess
from pathlib import Path

import pytest

import docker_smoke
from docker_smoke import validate_profiles


def test_smoke_requires_explicit_mode_before_reading_credentials(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Implicit invocation must not access the installed session")

    monkeypatch.setattr(docker_smoke, "read_dotenv", forbidden)
    monkeypatch.setattr(docker_smoke, "validate_profiles", forbidden)
    with pytest.raises(SystemExit) as exc:
        docker_smoke.main([])
    assert exc.value.code == 2


def test_profiles_only_never_contacts_the_app(monkeypatch):
    calls = []
    monkeypatch.setattr(docker_smoke, "validate_profiles", lambda *args: calls.append(args))

    def forbidden(*args, **kwargs):
        raise AssertionError("Profile validation must not contact or log into the app")

    monkeypatch.setattr(docker_smoke, "read_dotenv", forbidden)
    monkeypatch.setattr(docker_smoke.httpx, "Client", forbidden)
    assert docker_smoke.main(["--profiles-only"]) == 0
    assert len(calls) == 1


@pytest.mark.parametrize("bind", [{}, {"create_host_path": False}, {"create_host_path": True}])
def test_credential_mount_false_may_be_omitted_but_true_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bind: dict,
) -> None:
    env_file = tmp_path / "example.env"
    env_file.write_text("BRIDGE_ID=example\n", encoding="utf-8")
    ca_file = tmp_path / "example.crt"
    ca_file.write_text("example", encoding="utf-8")
    original_run = subprocess.run

    def compose(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command[0] != "docker":
            return original_run(command, **_)
        profile = Path(command[command.index("--env-file") + 1])
        if profile.name == "profiles.env":
            assert "BRIDGE_ID=example" in profile.read_text(encoding="utf-8")
            if os.name == "posix":
                assert profile.parent.stat().st_mode & 0o777 == 0o700
                assert profile.stat().st_mode & 0o777 == 0o600
        if "deploy/compose.bridge-credential.yaml" in command:
            services = {
                "bridge": {
                    "environment": {
                        "SSL_CERT_FILE": "/trust/root.crt",
                        "OPENBLINDYSIR_BRIDGE_CREDENTIALS_FILE": "/credentials/issued.toml",
                    },
                    "volumes": [
                        {"target": "/credentials/issued.toml", "read_only": True, "bind": bind}
                    ],
                    "read_only": True,
                    "cap_drop": ["ALL"],
                    "security_opt": ["no-new-privileges:true"],
                }
            }
        elif "deploy/compose.bridge.yaml" in command:
            services = {
                "bridge": {
                    "environment": {"SSL_CERT_FILE": "/trust/root.crt"},
                    "volumes": [{"type": "bind", "read_only": True}],
                }
            }
        else:
            ports = [80, 443] if "deploy/compose.public.yaml" in command else [443]
            services = {
                "app": {
                    "environment": {"BIND_HOST": "127.0.0.1"},
                    "ports": [{"target": port} for port in ports],
                },
                "bridge": {"network_mode": "service:app", "volumes": [{"read_only": True}]},
            }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"services": services}))

    monkeypatch.setattr("docker_smoke.subprocess.run", compose)
    if bind.get("create_host_path") is True:
        with pytest.raises(AssertionError):
            validate_profiles(env_file, ca_file)
    else:
        validate_profiles(env_file, ca_file)
