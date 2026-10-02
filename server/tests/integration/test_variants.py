"""Robustness variants of spec §20.2 on the real server, the demo Bridge and bots."""

import asyncio

import pytest
import websockets
from conftest import BLIND, HOST, Stack
from driver import Table

from bots import round_state


def run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


# --- reconnection during OPEN ------------------------------------------------------------


async def _reconnect_scenario(stack: Stack) -> None:
    async with Table(stack.base_url, 3, BLIND, HOST) as table:
        host, target, other = table.host, table.bots[0], table.bots[1]
        for bot in table.everyone:
            bot.auto_answer = False  # keep the round OPEN while the target is away
        await table.setup(rounds=2, clip=20, grace=40)
        await table.start()
        view = await table.wait_round(1, "OPEN")
        rid = view["round"]["round_id"]
        await target.wait_for(lambda v: round_state(v) == "OPEN")

        await target.draft(rid, "brouillon secret")
        await asyncio.sleep(0.3)
        await target.drop()
        await table.wait_host(
            lambda v: not next(p for p in v["players"] if p["id"] == target.player_id)["online"]
        )

        # The others go on; the offline player is not awaited by the counter.
        await table.bots[2].submit(rid, "réponse 3")
        progress = await other.wait_for(
            lambda v: (v["round"].get("progress") or {}).get("validated") == 1
        )
        assert progress["round"]["progress"]["expected"] == 3  # host + 2 online bots

        # Same identity, state restored, draft restored, late playback information present.
        await target.reconnect()
        back = await target.wait_for(lambda v: round_state(v) == "OPEN")
        assert back["me"]["player_id"] == target.player_id
        assert back["round"]["my_answer"]["draft_text"] == "brouillon secret"
        assert back["play"] is not None  # the clip is still playing: catch-up start (§9.6)

        # A second tab supersedes the managed connection, which can no longer act.
        tab = await target.raw_socket()
        await asyncio.wait_for(target._reader, 10)
        assert target.close_code == 4001
        with pytest.raises(websockets.ConnectionClosed):
            await target.submit(rid, "depuis l'ancien onglet")
        await tab.close()

        await target.reconnect()
        await target.submit(rid, "brouillon secret")
        await target.wait_for(lambda v: v["round"]["my_answer"]["status"] == "LOCKED")
        assert target.acks[-1]["status"] == "accepted"

        await host.submit(rid, "réponse hôte")
        await other.submit(rid, "réponse 2")
        review = await table.wait_round(1, "REVIEW")
        row = next(r for r in review["round"]["answers"] if r["player_id"] == target.player_id)
        assert row["status"] == "LOCKED"
        assert row["late_start_ms"] is not None
        assert row["late_start_ms"] > 0  # the outage during playback is measured by the server

        await table.score_and_publish({target.player_id: 2})
        for bot in table.everyone:
            bot.auto_answer = True
        await host.on_round("next")
        await table.wait_round(2, "REVIEW", timeout_s=90)
        await table.score_and_publish({})
        final = await table.finish()
        assert table.scores(final)[target.player_id] == 2


def test_reconnect_during_open_round(stack: Stack) -> None:
    run(_reconnect_scenario(stack))


# --- Bridge lost and found ---------------------------------------------------------------


async def _bridge_scenario(stack: Stack) -> None:
    async with Table(stack.base_url, 2, BLIND, HOST) as table:
        await table.setup(rounds=3, clip=8, grace=5)
        await table.start()
        view = await table.wait_round(1, "OPEN")
        current = view["audio"]["current"]["url"]
        await table.wait_host(lambda v: v["host"]["bridge"]["jobs_in_flight"] == 0, timeout_s=60)

        stack.stop_bridge()
        await table.wait_host(lambda v: v["host"]["bridge"]["state"] == "OFFLINE")
        # Already STORED clips stay playable.
        assert (await table.bots[0].http.get(current)).status_code == 200

        review = await table.wait_round(1, "REVIEW")
        assert review["audio"]["next"] is not None  # N+1 was prepared before the loss
        await table.score_and_publish({})
        await table.host.on_round("next")
        await table.wait_round(2, "OPEN", "REVIEW", timeout_s=60)  # round 2 uses the stored clip
        await table.wait_round(2, "REVIEW")
        await table.score_and_publish({})
        await table.host.on_round("next")
        waiting = await table.wait_round(3, "QUEUED", "PREPARING")
        assert "bridge_offline" in waiting["host"]["warnings"]
        diag = await table.diagnostics()
        assert diag["jobs"] == []  # no zombie job while the Bridge is away

        stack.start_bridge()
        await table.wait_round(3, "LOADING", "COUNTDOWN", "OPEN", "REVIEW", timeout_s=90)
        await table.wait_round(3, "REVIEW", timeout_s=60)
        await table.score_and_publish({})
        final = await table.finish()
        assert final["final_results"]["rounds_played"] == 3
    log = stack.server_log()
    assert "event=bridge_lost" in log
    assert log.count("event=bridge_connected") >= 2


def test_bridge_killed_and_restarted(stack: Stack) -> None:
    run(_bridge_scenario(stack))


async def _bridge_lost_mid_job(stack: Stack) -> None:
    async with Table(stack.base_url, 2, BLIND, HOST) as table:
        await table.setup(rounds=2, clip=8, grace=5)
        await table.start()
        await table.wait_host(lambda v: v["host"]["bridge"]["jobs_in_flight"] >= 1)
        stack.stop_bridge()  # a PREPARE is being encoded (slow-encode fault)
        await table.wait_host(lambda v: v["host"]["bridge"]["state"] == "OFFLINE")
        assert (await table.diagnostics())["jobs"] == []
        stack.start_bridge()
        await table.wait_round(1, "OPEN", "REVIEW", timeout_s=90)
        await table.host.on_round("end_game", {"current_round": "abandon"})
        await table.finish()
    assert "event=job_failed" in stack.server_log()


def test_bridge_lost_while_a_job_is_running(bare_stack: Stack) -> None:
    bare_stack.start_bridge("slow-encode=4000")
    run(_bridge_lost_mid_job(bare_stack))


# --- invalid assets and vanished files ------------------------------------------------------


async def _first_round_then_abandon(stack: Stack) -> None:
    async with Table(stack.base_url, 2, BLIND, HOST) as table:
        await table.setup(rounds=2, clip=8, grace=5)
        await table.start()
        await table.wait_round(1, "OPEN", timeout_s=90)
        await table.host.on_round("end_game", {"current_round": "abandon"})
        final = await table.finish()
        assert final["final_results"]["rounds_played"] == 0


def test_corrupted_upload_is_rejected_then_retried(bare_stack: Stack) -> None:
    bare_stack.start_bridge("corrupt-upload=1")
    run(_first_round_then_abandon(bare_stack))
    log = bare_stack.server_log()
    assert "event=upload_rejected reason=sha256" in log
    assert log.count("event=asset_stored") >= 1


def test_file_deleted_after_scan_is_replaced(bare_stack: Stack) -> None:
    bare_stack.start_bridge("delete-track=1")
    run(_first_round_then_abandon(bare_stack))
    log = bare_stack.server_log()
    assert "event=track_unavailable" in log
    assert "code=NOT_FOUND" in log
    assert "openblindysir-bridge-demo" not in bare_stack.bridge_log()  # no path on the console


# --- early end during OPEN -----------------------------------------------------------------


async def _early_end(stack: Stack, mode: str) -> None:
    async with Table(stack.base_url, 3, BLIND, HOST) as table:
        table.host.auto_answer = False
        await table.setup(rounds=3, clip=20, grace=30)
        await table.start()
        view = await table.wait_round(1, "OPEN")
        assert view["round"]["round_id"]
        await table.bots[0].wait_for(
            lambda v: ((v.get("round") or {}).get("my_answer") or {}).get("status") == "LOCKED"
        )
        await table.host.on_round("end_game", {"current_round": mode})
        if mode == "score":
            review = await table.wait_round(1, "REVIEW")
            assert review["round"]["ending"] is True
            assert review["audio"]["next"] is None  # prefetch stopped
            locked = [r["player_id"] for r in review["round"]["answers"] if r["status"] == "LOCKED"]
            await table.score_and_publish({pid: 1 for pid in locked})
            final = await table.finish()
            assert final["final_results"]["rounds_played"] == 1
            assert sum(table.scores(final["final_results"]).values()) == len(locked)
        else:
            await table.wait_host(lambda v: v["phase"] == "FINAL_SCORE_REVIEW")
            final = await table.finish()
            assert final["final_results"]["rounds_played"] == 0
            assert set(table.scores(final["final_results"]).values()) == {0}
        diag = await table.diagnostics()
        assert diag["jobs"] == []  # prefetch jobs cancelled
        assert diag["cache"] == []  # assets evicted


@pytest.mark.parametrize("mode", ["score", "abandon"])
def test_end_game_during_open(stack: Stack, mode: str) -> None:
    run(_early_end(stack, mode))
