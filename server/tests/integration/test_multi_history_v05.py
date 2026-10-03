"""Two real Bridges with distinct credentials, equal local IDs, crash and history deletion."""

import asyncio
import json
import os
import subprocess
import sys
import tomllib

import httpx
from conftest import BLIND, HOST, SECRET, Stack, wait_until
from driver import Table

SECOND = "12345678-1234-1234-1234-123456789abd"


def server_env(stack):
    values = {
        **os.environ,
        "DEV_MODE": "1",
        "BLIND_PASSWORD": BLIND,
        "HOST_PASSWORD": HOST,
        "BRIDGE_SECRET": SECRET,
        "BRIDGE_SECRETS": "",
        "PORT": str(stack.port),
        "STATE_DIR": str(stack.workdir / "state"),
        "READY_TIMEOUT_S": "5",
        "LOG_FORMAT": "text",
        "LOG_LEVEL": "INFO",
    }
    values.pop("DOMAIN", None)
    return values


async def play(stack):
    async with Table(stack.base_url, 2, BLIND, HOST) as table:
        for bot in table.everyone:
            bot.auto_answer = False
        await table.setup(rounds=2, clip=5, prefetch=1)
        await table.host.on_phase("set_mode", {"mode": "mc"})
        await table.wait_host(
            lambda v: (
                v["kind"] == "host_mc"
                and len(v["host"]["bridges"]) == 2
                and all(b["state"] == "ONLINE" for b in v["host"]["bridges"])
            )
        )
        owners = [b["bridge_id"] for b in table.host.view["host"]["bridges"]]
        await table.host.on_phase(
            "configure", {"sources": [{"bridge_id": b, "folder_prefix": ""} for b in owners]}
        )
        await table.wait_host(lambda v: len(v["host"]["settings"]["sources"]) == 2)
        tracks = (
            await table.host.http.get("/api/host/library/search", params={"limit": 100})
        ).json()["tracks"]
        common = set(t["track_id"] for t in tracks if t["bridge_id"] == owners[0]) & set(
            t["track_id"] for t in tracks if t["bridge_id"] == owners[1]
        )
        assert common, "synthetic demo roots should have equal local IDs"
        local_id = sorted(common)[0]
        for number, owner in enumerate(owners, 1):
            revision = table.host.view["mc"]["selection_revision"]
            await table.host.on_phase(
                "select_track",
                {
                    "round_number": number,
                    "expected_revision": revision,
                    "bridge_id": owner,
                    "track_id": local_id,
                },
            )
            await table.wait_host(
                lambda v, expected=revision + 1: v["mc"]["selection_revision"] == expected
            )
        await table.start()
        for number, owner in enumerate(owners, 1):
            ready = await table.wait_round(number, "LOADING")
            assert (
                next(
                    choice
                    for choice in ready["mc"]["manual_choices"]
                    if choice["round_number"] == number
                )["bridge_id"]
                == owner
            )
            await table.wait_host(lambda v: v["host"]["ready_check"]["ready"] >= 1)
            await table.host.on_round("force_start")
            opened = await table.wait_round(number, "OPEN")
            await table.bots[0].submit(opened["round"]["round_id"], f"Synthetic response {number}")
            await table.wait_host(
                lambda v: any(row["validated"] for row in v["round"]["per_player"])
            )
            assert all(owner not in json.dumps(bot.view) for bot in table.bots)
            await table.host.on_round("close")
            await table.wait_round(number, "REVIEW")
            await table.defer_scores({table.bots[0].player_id: 2})
            if number == 1:
                await table.host.on_round("next")
        await table.finish({table.bots[0].player_id: 1})
        await table.wait_host(lambda v: v["phase"] == "FINAL_RESULTS")
        history = (await table.host.http.get("/api/host/history")).json()
        assert history["durable"]
        assert len(history["items"]) == 1
        game_id = history["items"][0]["game_id"]
        record = (await table.host.http.get(f"/api/host/history/{game_id}")).json()
        assert {source["bridge_id"] for source in record["sources"]} == set(owners)
        assert any(row["score"] == 5 for row in record["results"]["standings"])
        return game_id, record, table.host.cookie_header()


def test_two_bridges_scores_and_history_survive_abrupt_restart(bare_stack: Stack):
    stack = bare_stack
    stack.start_bridge()
    credentials = stack.workdir / "issued.toml"
    issued = subprocess.run(
        [
            sys.executable,
            "-m",
            "openblindysir_server",
            "bridge-credential",
            "--bridge-id",
            SECOND,
            "--name",
            "Second synthetic",
            "--output",
            str(credentials),
        ],
        cwd=stack.workdir,
        env=server_env(stack),
        capture_output=True,
        check=False,
        timeout=20,
    )
    assert issued.returncode == 0, issued.stderr.decode(errors="replace")
    raw = tomllib.loads(credentials.read_text())["secret"]
    assert raw.encode() not in issued.stdout + issued.stderr
    second_log = (stack.workdir / "second.log").open("ab")
    second = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "openblindysir_bridge",
            "--demo",
            "--server",
            stack.base_url,
            "--config",
            str(stack.workdir / "second.toml"),
            "--credentials",
            str(credentials),
        ],
        env=os.environ.copy(),
        stdout=second_log,
        stderr=second_log,
    )
    restarted = None
    try:
        game_id, record, cookie = asyncio.run(play(stack))
        stack.server.kill()
        stack.server.wait(10)
        server_log = (stack.workdir / "restart.log").open("ab")
        stack.logs.append(server_log)
        restarted = subprocess.Popen(
            [sys.executable, "-m", "openblindysir_server", "serve", "--host", "127.0.0.1"],
            cwd=stack.workdir,
            env=server_env(stack),
            stdout=server_log,
            stderr=server_log,
        )
        wait_until(lambda: httpx.get(f"{stack.base_url}/healthz", timeout=2).status_code == 200)
        headers = {"cookie": cookie, "origin": stack.base_url}
        assert (
            httpx.get(f"{stack.base_url}/api/host/history/{game_id}", headers=headers).json()
            == record
        )
        wait_until(
            lambda: (
                all(
                    b["online"]
                    for b in httpx.get(
                        f"{stack.base_url}/api/host/library", headers=headers
                    ).json()["bridges"]
                )
                and len(
                    httpx.get(f"{stack.base_url}/api/host/library", headers=headers).json()[
                        "bridges"
                    ]
                )
                == 2
            ),
            60,
        )
        deleted = httpx.request(
            "DELETE",
            f"{stack.base_url}/api/host/history/{game_id}",
            headers=headers,
            json={"confirm": True},
        )
        assert deleted.status_code == 200
        for path in (stack.workdir / "state").glob("session*.json"):
            payload = json.loads(path.read_text())
            assert payload["state"]["archives"] == []
            assert raw not in path.read_text()
        assert raw not in stack.server_log() + stack.bridge_log()
    finally:
        second.kill()
        second.wait(10)
        second_log.close()
        if restarted is not None:
            restarted.kill()
            restarted.wait(10)
