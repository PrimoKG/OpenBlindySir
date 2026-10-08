"""Exercise the Docker deployment over verified HTTPS/WSS with synthetic clips only."""

import argparse
import asyncio
import json
import ssl
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

import httpx

from bots import play_game
from openblindysir_server.config import read_dotenv
from openblindysir_server.private_files import atomic_private_write, protect_file


def validate_profiles(env_file: Path, ca_file: Path) -> None:
    """Validate Compose wiring without printing interpolated secrets."""

    def compose(path: Path, *files: str) -> dict:
        command = ["docker", "compose", "--env-file", str(path)]
        for file in files:
            command += ["-f", file]
        output = subprocess.run(
            [*command, "config", "--format", "json"], capture_output=True, text=True, check=True
        )
        return json.loads(output.stdout)

    private = compose(env_file, "compose.yaml")["services"]
    assert private["app"]["environment"]["BIND_HOST"] == "127.0.0.1"
    assert all(port["target"] == 443 for port in private["app"]["ports"])
    assert private["bridge"]["network_mode"] == "service:app"
    assert private["bridge"]["volumes"][0]["read_only"]
    with tempfile.TemporaryDirectory(prefix="docker-profiles-") as temporary:
        protect_file(Path(temporary))
        path = Path(temporary) / "profiles.env"
        lines = env_file.read_text(encoding="utf-8").splitlines()
        routing = {
            "DOMAIN",
            "TLS_HOST",
            "TLS_SERVER_NAME",
            "HTTPS_PORT",
            "BIND_IP",
            "CADDY_PROFILE",
        }
        base = "\n".join(line for line in lines if line.partition("=")[0] not in routing)
        atomic_private_write(
            path,
            (
                base + "\nDOMAIN=blind.example.com\nTLS_HOST=blind.example.com\n"
                "TLS_SERVER_NAME=blind.example.com\nHTTPS_PORT=443\nBIND_IP=0.0.0.0\n"
                "CADDY_PROFILE=public\nBRIDGE_SERVER=https://blind.example.com\n"
                f"BRIDGE_CA_FILE='{ca_file.resolve().as_posix()}'\n"
                f"BRIDGE_CREDENTIALS_FILE='{ca_file.resolve().as_posix()}'\n"
            ).encode("utf-8"),
        )
        public = compose(path, "compose.yaml", "deploy/compose.public.yaml")["services"]
        assert {port["target"] for port in public["app"]["ports"]} == {80, 443}
        remote = compose(path, "deploy/compose.bridge.yaml", "deploy/compose.bridge.private.yaml")[
            "services"
        ]["bridge"]
        assert remote["environment"]["SSL_CERT_FILE"] == "/trust/root.crt"
        assert not remote.get("ports")
        assert all(volume["read_only"] for volume in remote["volumes"] if volume["type"] == "bind")
        individual = compose(
            path, "deploy/compose.bridge-credential.yaml", "deploy/compose.bridge.private.yaml"
        )["services"]["bridge"]
        assert individual["environment"]["SSL_CERT_FILE"] == "/trust/root.crt"
        assert individual["environment"]["OPENBLINDYSIR_BRIDGE_CREDENTIALS_FILE"] == (
            "/credentials/issued.toml"
        )
        credential = next(
            v for v in individual["volumes"] if v["target"] == "/credentials/issued.toml"
        )
        assert credential["read_only"]
        # Older Compose-Go serializers omit bool false; newer ones retain it.
        # True must still fail: credentials must never create a missing host path.
        assert credential["bind"].get("create_host_path", False) is False
        assert individual["read_only"]
        assert individual["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in individual["security_opt"]
        assert not individual.get("ports")
    print("Compose profiles PASS: private, public, bootstrap and individual Bridges with TLS root.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".local/docker/hosting.env"))
    parser.add_argument("--ca-file", type=Path, default=Path(".local/docker/root.crt"))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--profiles-only", action="store_true", help="Validate Compose without contacting the app"
    )
    mode.add_argument(
        "--allow-test-session-mutation",
        action="store_true",
        help="Dedicated test installation only: creates players and changes game settings/scores",
    )
    args = parser.parse_args(argv)
    validate_profiles(args.env_file, args.ca_file)
    if args.profiles_only:
        return 0
    config = read_dotenv(args.env_file)
    context = ssl.create_default_context(cafile=str(args.ca_file))
    base = "https://" + config["DOMAIN"]
    with httpx.Client(base_url=base, verify=context, timeout=5) as client:
        health = client.get("/healthz")
        health.raise_for_status()
        assert health.json()["status"] == "ok"
        # Production health deliberately hides Bridge state. play_game waits for
        # ONLINE in the authenticated host view, not the development health payload.
        page = client.get("/host")
        assert page.status_code == 200
        assert '<div id="root">' in page.text
        assert "content-security-policy" in page.headers
        assert "strict-transport-security" in page.headers
        refused = client.post(
            "/api/session/join",
            headers={"Origin": "https://wrong.example.com"},
            json={"nickname": "Refused", "password": config["BLIND_PASSWORD"]},
        )
        assert refused.status_code == 403
        joined = client.post(
            "/api/session/join",
            headers={"Origin": base},
            json={"nickname": "Cookie check", "password": config["BLIND_PASSWORD"]},
        )
        assert joined.status_code == 200
        cookie = joined.headers["set-cookie"].lower()
        assert "__host-openblindysir=" in cookie
        assert "secure" in cookie
        assert "httponly" in cookie
    result = asyncio.run(
        play_game(
            base,
            players=2,
            rounds=2,
            password=config["BLIND_PASSWORD"],
            host_password=config["HOST_PASSWORD"],
            ssl_context=context,
        )
    )
    assert result["final_results"]["rounds_played"] == 2
    assert all(acks == ["accepted", "accepted"] for acks in result["acks"].values())
    assert not result["errors"]
    print("Docker smoke PASS: UI, HTTPS, origin, Secure cookie, Bridge, clips, WSS, final results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
