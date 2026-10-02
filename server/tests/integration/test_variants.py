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
