"""A real Bridge extracts the MC's choice; players see it only after final review."""

import asyncio
import json
import os
import subprocess
import sys

from conftest import BLIND, HOST, SECRET, Stack
from driver import Table


async def scenario(stack: Stack) -> None:
    async with Table(stack.base_url, 2, BLIND, HOST) as table:
        for bot in table.everyone:
            bot.auto_answer = False
        await table.setup(rounds=1, clip=5, prefetch=1)
        await table.host.on_phase("set_mode", {"mode": "mc"})
        view = await table.wait_host(lambda v: v["kind"] == "host_mc")
        tracks = (await table.host.http.get("/api/host/library/search")).json()["tracks"]
        track = tracks[0]
        await table.host.on_phase(
            "select_track",
            {
                "round_number": 1,
                "expected_revision": view["mc"]["selection_revision"],
                "bridge_id": track["bridge_id"],
                "track_id": track["track_id"],
            },
        )
        await table.wait_host(lambda v: v["mc"]["manual_choices"][0]["manual"])
        await table.start()
        ready = await table.wait_round(1, "LOADING")
        assert ready["mc"]["manual_choices"][0]["locked"]
        assert ready["mc"]["manual_choices"][0]["track_id"] == track["track_id"]
        assert ready["play"] is None
        assert track["track_id"] not in json.dumps(table.bots[0].view)
        await table.wait_host(lambda v: v["host"]["ready_check"]["ready"] >= 1)
        await table.host.host("force_start", round_id=ready["round"]["round_id"])
        await table.wait_round(1, "OPEN")
        for bot in table.bots:
            assert "manual_choices" not in json.dumps(bot.view)
        await table.host.host("close", round_id=table.host.view["round"]["round_id"])
        results = await table.finish()
        assert results["phase"] == "FINAL_RESULTS"
        assert results["final_results"]["recap"][0]["history"][0]["track"] is not None


def test_manual_choice_real_bridge_and_publication(stack: Stack) -> None:
    asyncio.run(scenario(stack))


def test_cli_doctor_registers_real_server_and_bad_secret_exits(bare_stack: Stack) -> None:
    music = bare_stack.workdir / "music"
    music.mkdir()
    env = {
        **os.environ,
        "OPENBLINDYSIR_BRIDGE_SERVER": bare_stack.base_url,
        "OPENBLINDYSIR_BRIDGE_SECRET": SECRET,
        "OPENBLINDYSIR_BRIDGE_DIR": str(music),
        "OPENBLINDYSIR_BRIDGE_CONFIG": str(bare_stack.workdir / "doctor.toml"),
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [sys.executable, "-m", "openblindysir_bridge", "doctor", "--connect", "--json"],
        cwd=bare_stack.workdir,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=35,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["connection"] == "registered"
    assert report["tracks"] == 0
    assert SECRET not in result.stdout + result.stderr
    assert str(music) not in result.stdout + result.stderr
    env["OPENBLINDYSIR_BRIDGE_SECRET"] = "SYNTHETIC-WRONG-SECRET-" + "x" * 32
    refused = subprocess.run(
        [sys.executable, "-m", "openblindysir_bridge", "run"],
        cwd=bare_stack.workdir,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=20,
    )
    assert refused.returncode == 4
    assert "refusé/révoqué" in refused.stdout
    assert env["OPENBLINDYSIR_BRIDGE_SECRET"] not in refused.stdout + refused.stderr
    assert "Traceback" not in refused.stdout + refused.stderr
