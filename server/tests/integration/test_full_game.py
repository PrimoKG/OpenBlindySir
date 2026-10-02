"""Gate §26-5: real server + demo Bridge + 10 bots play a complete game (spec §20.2)."""

import asyncio

from conftest import BLIND, HOST, Stack

from bots import play_game


def test_full_game_with_ten_bots(stack: Stack) -> None:
    result = asyncio.run(
        play_game(stack.base_url, players=10, rounds=2, password=BLIND, host_password=HOST)
    )
    final = result["final_results"]
    assert final["rounds_played"] == 2
    assert len(final["standings"]) == 11
    assert final["final_adjustments"] == [
        {"player_id": final["final_adjustments"][0]["player_id"], "delta": 1}
    ]
    for nickname, acks in result["acks"].items():
        assert acks == ["accepted", "accepted"], nickname
    assert not result["errors"]
    scores = sorted((row["score"] for row in final["standings"]), reverse=True)
    assert scores[0] >= 3  # the fastest correct answers got +3 from the host bot
