"""Identifier factories: random in production, sequential and readable in tests."""

import secrets
from typing import Protocol


class IdFactory(Protocol):
    def player_id(self) -> str: ...

    def round_id(self) -> str: ...

    def play_id(self) -> str: ...

    def asset_id(self) -> str: ...

    def job_id(self) -> str: ...

    def game_id(self) -> str: ...

    def epoch(self) -> str: ...


class SecretIds:
    """Unpredictable identifiers. ``asset_id`` carries 128 random bits (spec §12)."""

    def player_id(self) -> str:
        return "p_" + secrets.token_urlsafe(8)[:10]

    def round_id(self) -> str:
        return "r_" + secrets.token_urlsafe(9)[:12]

    def play_id(self) -> str:
        return "pl_" + secrets.token_urlsafe(9)[:12]

    def asset_id(self) -> str:
        return "a_" + secrets.token_urlsafe(16)

    def job_id(self) -> str:
        return "j_" + secrets.token_urlsafe(9)[:12]

    def game_id(self) -> str:
        return "g_" + secrets.token_urlsafe(8)[:10]

    def epoch(self) -> str:
        return secrets.token_hex(8)


class SequentialIds:
    """Deterministic identifiers for tests (valid against the protocol patterns)."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def _next(self, kind: str) -> int:
        self._counters[kind] = self._counters.get(kind, 0) + 1
        return self._counters[kind]

    def player_id(self) -> str:
        return f"p_{self._next('p'):04d}"

    def round_id(self) -> str:
        return f"r_{self._next('r'):06d}"

    def play_id(self) -> str:
        return f"pl_{self._next('pl'):06d}"

    def asset_id(self) -> str:
        return f"a_{self._next('a'):022d}"

    def job_id(self) -> str:
        return f"j_{self._next('j'):06d}"

    def game_id(self) -> str:
        return f"g_{self._next('g'):04d}"

    def epoch(self) -> str:
        return f"{self._next('e'):016x}"
