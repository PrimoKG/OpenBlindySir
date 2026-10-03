"""Credential mount safety checks support both Compose JSON serializers."""

import json
import subprocess
from pathlib import Path

import pytest

from docker_smoke import validate_profiles


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

    def compose(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
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
