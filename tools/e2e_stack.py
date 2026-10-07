"""Run the server (serving web/dist) and the demo Bridge for the Playwright tests.

Started by ``web/playwright.config.ts`` as its web server; stops both children on exit.
Synthetic demo library only, test passwords only (spec §20.3).
"""

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("E2E_PORT", "8765"))
BASE = f"http://localhost:{PORT}"
BLIND = "example-e2e-blind"
HOST = "example-e2e-host"
SECRET = "example-e2e-bridge-secret-0123456789abcdef"  # noqa: S105 - test value


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="openblindysir-e2e-"))
    server_env = {
        **os.environ,
        "DEV_MODE": "1",
        "BLIND_PASSWORD": BLIND,
        "HOST_PASSWORD": HOST,
        "BRIDGE_SECRET": SECRET,
        "PORT": str(PORT),
        "STATIC_DIR": str(ROOT / "web" / "dist"),
        "STATE_DIR": str(work / "state"),
        # Playwright's Chromium has no AAC decoder; Opus decodes everywhere.
        "CLIP_FORMAT": "opus",
        "READY_TIMEOUT_S": "10",
    }
    server_env.pop("DOMAIN", None)
    bridge_env = {
        **os.environ,
        "OPENBLINDYSIR_BRIDGE_SECRET": SECRET,
        "OPENBLINDYSIR_BRIDGE_CONFIG": str(work / "bridge.toml"),
        "OPENBLINDYSIR_BRIDGE_NAME": "Demo",
        # Synthetic sources only: exercise opt-in full review without changing production defaults.
        "OPENBLINDYSIR_BRIDGE_ALLOW_FULL_REVIEW": "true",
    }
    children: list[subprocess.Popen[bytes]] = []

    def stop(*_: object) -> None:
        for child in children:
            if child.poll() is None:
                if os.name == "nt":
                    # The venv launcher owns another Python process on Windows.
                    # Killing only that launcher leaves the server and output pipes
                    # alive, preventing Playwright from completing its teardown.
                    subprocess.run(
                        ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    child.kill()
                child.wait(timeout=10)
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    children.append(
        subprocess.Popen(
            [sys.executable, "-m", "openblindysir_server", "serve", "--host", "127.0.0.1"],
            env=server_env,
            cwd=work,
        )
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{BASE}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    children.append(
        subprocess.Popen(
            [sys.executable, "-m", "openblindysir_bridge", "--demo", "--server", BASE],
            env=bridge_env,
            cwd=work,
            stdout=subprocess.DEVNULL,
        )
    )
    try:
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
    finally:
        stop()
    return 1


if __name__ == "__main__":
    sys.exit(main())
