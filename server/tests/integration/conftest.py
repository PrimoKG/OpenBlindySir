"""Integration fixtures: the real server and the demo Bridge as subprocesses (spec §20.2).

Collected only with ``-m integration``. Requires FFmpeg on PATH (the demo Bridge generates
its synthetic library with ``ffmpeg -f lavfi``).
"""

import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

import httpx
import pytest

BLIND = "example-integration-blind"
HOST = "example-integration-host"
SECRET = "example-integration-bridge-secret-0123456789"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    here = Path(__file__).parent
    for item in items:
        if here in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.integration)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until(predicate: object, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if predicate():  # type: ignore[operator]
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise TimeoutError("condition not reached")


@dataclass
class Stack:
    base_url: str
    port: int
    workdir: Path
    server: subprocess.Popen[bytes]
    bridge: subprocess.Popen[bytes] | None = None
    logs: list[IO[bytes]] = field(default_factory=list)

    def bridge_state(self) -> str | None:
        return httpx.get(f"{self.base_url}/healthz", timeout=2).json()["bridge"]

    def start_bridge(self, *faults: str) -> None:
        args = [sys.executable, "-m", "openblindysir_bridge", "--demo", "--server", self.base_url]
        for fault in faults:
            args += ["--demo-fault", fault]
        env = {
            **os.environ,
            "OPENBLINDYSIR_BRIDGE_SECRET": SECRET,
            "OPENBLINDYSIR_BRIDGE_CONFIG": str(self.workdir / "bridge.toml"),
            "OPENBLINDYSIR_BRIDGE_NAME": "Demo",
        }
        log = (self.workdir / "bridge.log").open("ab")
        self.logs.append(log)
        self.bridge = subprocess.Popen(args, env=env, stdout=log, stderr=log)
        wait_until(lambda: self.bridge_state() == "ONLINE", 60)

    def server_log(self) -> str:
        return (self.workdir / "server.log").read_text(encoding="utf-8", errors="replace")

    def bridge_log(self) -> str:
        path = self.workdir / "bridge.log"
        return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""

    def stop_bridge(self) -> None:
        if self.bridge is not None:
            self.bridge.kill()
            self.bridge.wait(10)
            self.bridge = None
            wait_until(lambda: self.bridge_state() == "OFFLINE", 30)


@pytest.fixture
def stack(bare_stack: Stack) -> Stack:
    """Server plus a connected demo Bridge."""
    bare_stack.start_bridge()
    return bare_stack


@pytest.fixture
def bare_stack(tmp_path: Path) -> Iterator[Stack]:
    """Server only: the test starts the Bridge itself (e.g. with fault injection)."""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("FFmpeg is required for the demo Bridge")
    port = free_port()
    env = {
        **os.environ,
        "DEV_MODE": "1",
        "BLIND_PASSWORD": BLIND,
        "HOST_PASSWORD": HOST,
        "BRIDGE_SECRET": SECRET,
        "PORT": str(port),
        "STATE_DIR": str(tmp_path / "state"),
        "READY_TIMEOUT_S": "5",
        # Assertions inspect key=value events, regardless of the caller's logging preference.
        "LOG_FORMAT": "text",
        "LOG_LEVEL": "INFO",
    }
    env.pop("DOMAIN", None)
    log = (tmp_path / "server.log").open("ab")
    server = subprocess.Popen(
        [sys.executable, "-m", "openblindysir_server", "serve", "--host", "127.0.0.1"],
        env=env,
        cwd=tmp_path,
        stdout=log,
        stderr=log,
    )
    base_url = f"http://localhost:{port}"
    try:
        wait_until(lambda: httpx.get(f"{base_url}/healthz", timeout=2).status_code == 200)
        stack = Stack(base_url=base_url, port=port, workdir=tmp_path, server=server, logs=[log])
        try:
            yield stack
        finally:
            if stack.bridge is not None:
                stack.bridge.kill()
                stack.bridge.wait(10)
            server.kill()
            server.wait(10)
            for handle in stack.logs:
                handle.close()
    finally:
        if server.poll() is None:
            server.kill()
            server.wait(10)
        log.close()
