"""Session tokens: 256 random bits, stored only as their sha256 (spec §12)."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from openblindysir_server.logging import redaction


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_password(candidate: str, expected: str) -> bool:
    """Constant-time comparison of two passwords (sha256 first: equal lengths)."""
    a = hashlib.sha256(candidate.encode("utf-8")).digest()
    b = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(a, b)


@dataclass(slots=True)
class SessionRecord:
    player_id: str
    created_mono: int
    last_seen_mono: int


class SessionRegistry:
    """token hash → player; expires after ``idle_ttl_ms`` without activity."""

    def __init__(self, idle_ttl_ms: int) -> None:
        self.idle_ttl_ms = idle_ttl_ms
        self._by_hash: dict[str, SessionRecord] = {}

    def issue(self, player_id: str, now_ms: int) -> str:
        token = new_token()
        self._by_hash[hash_token(token)] = SessionRecord(player_id, now_ms, now_ms)
        redaction().add_secret(token)
        return token

    def resolve(self, token: str | None, now_ms: int, *, touch: bool = True) -> str | None:
        if not token:
            return None
        record = self._by_hash.get(hash_token(token))
        if record is None:
            return None
        if now_ms - record.last_seen_mono > self.idle_ttl_ms:
            del self._by_hash[hash_token(token)]
            return None
        if touch:
            record.last_seen_mono = now_ms
        return record.player_id

    def touch_player(self, player_id: str, now_ms: int) -> None:
        for record in self._by_hash.values():
            if record.player_id == player_id:
                record.last_seen_mono = now_ms

    def revoke(self, player_ids: tuple[str, ...]) -> None:
        targets = set(player_ids)
        for key in [k for k, r in self._by_hash.items() if r.player_id in targets]:
            del self._by_hash[key]

    def revoke_all(self) -> None:
        self._by_hash.clear()

    def expire_idle(self, now_ms: int) -> None:
        stale = [
            k for k, r in self._by_hash.items() if now_ms - r.last_seen_mono > self.idle_ttl_ms
        ]
        for key in stale:
            del self._by_hash[key]

    def snapshot(self, now_ms: int) -> list[dict[str, str | int]]:
        return [
            dict(token_hash=key, player_id=r.player_id, idle_ms=max(0, now_ms - r.last_seen_mono))
            for key, r in self._by_hash.items()
        ]

    def restore(
        self, records: list[dict], now_ms: int, downtime_ms: int, players: set[str]
    ) -> None:
        self._by_hash.clear()
        for row in records:
            key, pid, age = row["token_hash"], row["player_id"], row["idle_ms"] + downtime_ms
            if (
                len(key) == 64
                and all(c in "0123456789abcdef" for c in key)
                and pid in players
                and 0 <= age <= self.idle_ttl_ms
            ):
                self._by_hash[key] = SessionRecord(pid, now_ms - age, now_ms - age)
