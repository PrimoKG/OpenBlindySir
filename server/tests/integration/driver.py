"""A small table driver for integration scenarios: one host bot and N player bots."""

from collections.abc import Callable
from typing import Any

from bots import Bot, HostBot, round_state

View = dict[str, Any]


class Table:
    def __init__(self, base_url: str, players: int, password: str, host_password: str) -> None:
        self.host_password = host_password
        self.pending_scores: dict[int, dict[str, int]] = {}
        self.last_round = 1
        self.host = HostBot(base_url, "Hote", password)
        self.bots = [Bot(base_url, f"Bot{i}", password) for i in range(1, players + 1)]
        self.everyone: list[Bot] = [self.host, *self.bots]

    async def __aenter__(self) -> "Table":
        for bot in self.everyone:
            await bot.join()
        await self.host.elevate(self.host_password)
        for bot in self.everyone:
            await bot.connect()
        await self.host.wait_for(
            lambda v: v.get("kind") == "host_player" and v["host"]["bridge"]["state"] == "ONLINE",
            timeout_s=60,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        for bot in self.everyone:
            await bot.close()

    async def setup(
        self, rounds: int, *, clip: int = 8, grace: int = 30, prefetch: int = 1
    ) -> None:
        library = (await self.host.http.get("/api/host/library")).json()
        bridge_id = library["bridges"][0]["bridge_id"]
        await self.host.on_phase(
            "configure",
            {
                "rounds": rounds,
                "clip_seconds": clip,
                "answer_grace_s": grace,
                "prefetch_depth": prefetch,
                "sources": [{"bridge_id": bridge_id, "folder_prefix": ""}],
            },
        )
        await self.host.wait_for(lambda v: v["host"]["settings"]["rounds"] == rounds)

    async def start(self) -> None:
        await self.host.on_phase("start_game")

    async def wait_host(self, predicate: Callable[[View], bool], timeout_s: float = 60) -> View:
        return await self.host.wait_for(predicate, timeout_s=timeout_s)

    async def wait_round(self, number: int, *states: str, timeout_s: float = 60) -> View:
        self.last_round = number
        return await self.wait_host(
            lambda v: (
                (
                    v.get("phase") == "IN_GAME"
                    and (v.get("round") or {}).get("number") == number
                    and round_state(v) in states
                )
                or (
                    "REVIEW" in states
                    and v.get("phase") == "FINAL_SCORE_REVIEW"
                    and any(r["number"] == number for r in v["host"]["review_rounds"])
                )
            ),
            timeout_s,
        )

    async def defer_scores(self, points: dict[str, int]) -> None:
        """Record the human's test decision locally; submit it only in global review."""
        self.pending_scores[self.last_round] = points

    async def finish(self, final: dict[str, int] | None = None) -> View:
        """From a REVEALED last round (or after an early end): final review then results."""
        if self.host.view["phase"] == "IN_GAME":
            await self.host.on_phase("end_game", {"current_round": "score"})
        await self.wait_host(lambda v: v["phase"] == "FINAL_SCORE_REVIEW")
        for r in self.host.view["host"]["review_rounds"]:
            for pid, points in self.pending_scores.get(r["number"], {}).items():
                await self.host.host(
                    "score_draft", {"player_id": pid, "points": points}, round_id=r["round_id"]
                )
        if self.pending_scores:
            await self.wait_host(
                lambda v: all(
                    any(
                        row["player_id"] == pid
                        and row["points_draft"] == points
                        and row["reviewed"]
                        for row in r["answers"]
                    )
                    for r in v["host"]["review_rounds"]
                    for pid, points in self.pending_scores.get(r["number"], {}).items()
                )
            )
        for pid, delta in (final or {}).items():
            await self.host.on_phase("final_set", {"player_id": pid, "delta": delta})
        if final:
            await self.wait_host(
                lambda v: all(
                    any(
                        r["player_id"] == pid and r["draft_delta"] == d
                        for r in v["host"]["final_review"]
                    )
                    for pid, d in final.items()
                )
            )
        await self.host.on_phase("final_validate", {"confirm_unreviewed": True})
        return await self.bots[0].wait_for(lambda v: v["phase"] == "FINAL_RESULTS")

    async def diagnostics(self) -> dict[str, Any]:
        return (await self.host.http.get("/api/host/diagnostics")).json()

    def scores(self, view: View) -> dict[str, int]:
        return {row["player_id"]: row["score"] for row in view["standings"]}
