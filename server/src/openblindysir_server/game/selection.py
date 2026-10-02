"""Track selection (spec §6.9): folder-prefix pool, shuffled queue, no repeat in a session."""

from collections import deque

from openblindysir_protocol.enums import GamePhase
from openblindysir_protocol.views import PoolStatus
from openblindysir_server.game.state import SessionState, Slot, TrackRef, current_round


def matches(relpath: str, prefix: str) -> bool:
    """True when the track lies under the checked folder (by whole path segments)."""
    return prefix in ("", relpath) or relpath.startswith(prefix + "/")


def pool(s: SessionState) -> list[TrackRef]:
    """Available tracks matching the selected folders, sorted for determinism."""
    found: set[TrackRef] = set()
    for bridge_id, prefix in s.game.settings.sources:
        catalog = s.catalogs.get(bridge_id)
        if catalog is None:
            continue
        for track_id, entry in catalog.entries.items():
            if matches(entry.relpath, prefix):
                found.add(TrackRef(bridge_id, track_id))
    return sorted(found - s.game.unavailable)


def live_slots(s: SessionState) -> list[Slot]:
    slots: list[Slot] = list(s.game.pipeline)
    r = current_round(s.game)
    if r is not None:
        slots.insert(0, r.slot)
    return slots


def build_queue(s: SessionState, *, include_played: bool) -> deque[TrackRef]:
    """Shuffled queue; tracks never played in the session always come first."""
    in_use = {slot.track_ref for slot in live_slots(s) if slot.track_ref is not None}
    candidates = [t for t in pool(s) if t not in in_use]
    fresh = [t for t in candidates if t not in s.played]
    s.rng.shuffle(fresh)
    repeats: list[TrackRef] = []
    if include_played:
        repeats = [t for t in candidates if t in s.played]
        s.rng.shuffle(repeats)
    return deque(fresh + repeats)


def track_exists(s: SessionState, ref: TrackRef) -> bool:
    catalog = s.catalogs.get(ref.bridge_id)
    return catalog is not None and ref.track_id in catalog.entries


def take(s: SessionState) -> TrackRef | None:
    """Next usable track of the queue, or None when the pool is exhausted."""
    queue = s.game.queue
    while queue:
        ref = queue.popleft()
        if ref not in s.game.unavailable and track_exists(s, ref):
            return ref
    return None


def pool_status(s: SessionState) -> PoolStatus:
    size = len(pool(s))
    if s.game.phase is GamePhase.IN_GAME:
        remaining = len(s.game.queue)
    else:
        remaining = len([t for t in pool(s) if t not in s.played])
    return PoolStatus(size=size, remaining=remaining, exhausted=remaining == 0)
