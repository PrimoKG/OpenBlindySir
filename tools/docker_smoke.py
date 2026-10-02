"""Exercise the Docker deployment over verified HTTPS/WSS with synthetic clips only."""

import argparse
import asyncio
import ssl
import time
from pathlib import Path

import httpx

from bots import play_game
from openblindysir_server.config import read_dotenv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".local/docker/hosting.env"))
    parser.add_argument("--ca-file", type=Path, default=Path(".local/docker/root.crt"))
    args = parser.parse_args()
    config = read_dotenv(args.env_file)
    context = ssl.create_default_context(cafile=str(args.ca_file))
    base = "https://" + config["DOMAIN"]
    with httpx.Client(base_url=base, verify=context, timeout=5) as client:
        deadline = time.monotonic() + 90
        while True:
            health = client.get("/healthz")
            health.raise_for_status()
            if health.json()["bridge"] == "ONLINE":
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Docker Bridge did not become ONLINE")
            time.sleep(0.5)
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
