"""Rate limiting primitives (spec §12): login limits per IP, per-connection message budget,
open connections per IP."""

from collections import defaultdict, deque


class SlidingWindowLimiter:
    """At most ``limit`` events per ``window_ms`` per key, plus a global cap."""

    def __init__(self, limit: int, global_limit: int, window_ms: int = 60_000) -> None:
        self.limit = limit
        self.global_limit = global_limit
        self.window_ms = window_ms
        self._per_key: dict[str, deque[int]] = defaultdict(deque)
        self._global: deque[int] = deque()

    def _trim(self, events: deque[int], now_ms: int) -> None:
        while events and events[0] <= now_ms - self.window_ms:
            events.popleft()

    def blocked(self, key: str, now_ms: int) -> bool:
        """True once ``limit`` events of this key (or the global cap) fall in the window."""
        events = self._per_key[key]
        self._trim(events, now_ms)
        self._trim(self._global, now_ms)
        return len(events) >= self.limit or len(self._global) >= self.global_limit

    def record(self, key: str, now_ms: int) -> None:
        self._per_key[key].append(now_ms)
        self._global.append(now_ms)

    def allow(self, key: str, now_ms: int) -> bool:
        """Check and count in one step."""
        if self.blocked(key, now_ms):
            return False
        self.record(key, now_ms)
        return True


class TokenBucket:
    """Per-connection message budget: ``capacity`` burst, ``refill_per_s`` sustained."""

    def __init__(self, capacity: float, refill_per_s: float, now_ms: int) -> None:
        self.capacity = capacity
        self.refill_per_ms = refill_per_s / 1000
        self.tokens = capacity
        self.updated_ms = now_ms

    def take(self, now_ms: int) -> bool:
        elapsed = max(0, now_ms - self.updated_ms)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_ms)
        self.updated_ms = now_ms
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class ConnectionCounter:
    """Open WebSocket connections per IP (friends behind one NAT are allowed up to a cap)."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._open: dict[str, int] = defaultdict(int)

    def acquire(self, ip: str) -> bool:
        if self._open[ip] >= self.limit:
            return False
        self._open[ip] += 1
        return True

    def release(self, ip: str) -> None:
        if self._open[ip] > 0:
            self._open[ip] -= 1
