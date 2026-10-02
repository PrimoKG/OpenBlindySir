"""A small table driver for integration scenarios: one host bot and N player bots."""

from collections.abc import Callable
from typing import Any

from bots import Bot, HostBot, round_state

View = dict[str, Any]


class Table:
    def __init__(self, base_url: str, players: int, password: str, host_password: str) -> None:
        self.host_password = host_password
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
        return await self.wait_host(
            lambda v: (
                v.get("phase") == "IN_GAME"
                and (v.get("round") or {}).get("number") == number
                and round_state(v) in states
            ),
            timeout_s,
        )

    async def score_and_publish(self, points: dict[str, int]) -> None:
        for pid, pts in points.items():
            await self.host.on_round("score_draft", {"player_id": pid, "points": pts})
        if points:
            await self.wait_host(
                lambda v: all(
                    any(
                        r["player_id"] == pid and r["points_draft"] == pts
                        for r in v["round"]["answers"]
                    )
                    for pid, pts in points.items()
                )
            )
        await self.host.on_round("publish")
        await self.wait_host(lambda v: round_state(v) == "REVEALED")

    async def finish(self, final: dict[str, int] | None = None) -> View:
        """From a REVEALED last round (or after an early end): final review then results."""
        if self.host.view["phase"] == "IN_GAME":
            await self.host.on_round("to_final_review")
        await self.wait_host(lambda v: v["phase"] == "FINAL_SCORE_REVIEW")
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
        await self.host.on_phase("final_validate")
        return await self.bots[0].wait_for(lambda v: v["phase"] == "FINAL_RESULTS")

    async def diagnostics(self) -> dict[str, Any]:
        return (await self.host.http.get("/api/host/diagnostics")).json()

    def scores(self, view: View) -> dict[str, int]:
        return {row["player_id"]: row["score"] for row in view["standings"]}
