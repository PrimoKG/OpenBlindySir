"""RAM audio cache (spec §5.3, ADR 0005): hard caps, retention dictated by the core."""

from collections.abc import Mapping
from dataclasses import dataclass

from openblindysir_protocol.enums import AssetRole


@dataclass(frozen=True, slots=True)
class PutResult:
    stored: bool
    evicted: tuple[str, ...]


class AudioCache:
    def __init__(self, cap_bytes: int, max_item_bytes: int) -> None:
        self.cap_bytes = cap_bytes
        self.max_item_bytes = max_item_bytes
        self._items: dict[str, tuple[bytes, str]] = {}

    @property
    def used_bytes(self) -> int:
        return sum(len(data) for data, _ in self._items.values())

    def items(self) -> list[tuple[str, int]]:
        return [(asset_id, len(data)) for asset_id, (data, _) in self._items.items()]

    def put_pending(self, asset_id: str, data: bytes, mime: str, keep: frozenset[str]) -> PutResult:
        """Store a verified upload; evict what is not in ``keep`` first if the cap requires it."""
        if len(data) > self.max_item_bytes:
            return PutResult(stored=False, evicted=())
        evicted: list[str] = []
        if self.used_bytes + len(data) > self.cap_bytes:
            for other in list(self._items):
                if other in keep or other == asset_id:
                    continue
                del self._items[other]
                evicted.append(other)
                if self.used_bytes + len(data) <= self.cap_bytes:
                    break
        if self.used_bytes + len(data) > self.cap_bytes:
            return PutResult(stored=False, evicted=tuple(evicted))
        self._items[asset_id] = (data, mime)
        return PutResult(stored=True, evicted=tuple(evicted))

    def get_servable(self, asset_id: str, servable: frozenset[str]) -> tuple[bytes, str] | None:
        if asset_id not in servable:
            return None
        return self._items.get(asset_id)

    def retain(self, roles: Mapping[str, AssetRole]) -> list[str]:
        """Drop every asset the core no longer retains (previous, current, next, next2)."""
        evicted = [asset_id for asset_id in self._items if asset_id not in roles]
        for asset_id in evicted:
            del self._items[asset_id]
        return evicted

    def has(self, asset_id: str) -> bool:
        return asset_id in self._items

    def clear(self) -> None:
        self._items.clear()
