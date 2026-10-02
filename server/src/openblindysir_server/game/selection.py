"""Track selection (spec §6.9): folder-prefix pool, shuffled queue, no repeat in a session."""

from collections import deque

from openblindysir_protocol.enums import GamePhase, RoundState
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
    """Slots whose track is in use: the pipeline and the current round while it is live."""
    slots: list[Slot] = list(s.game.pipeline)
    r = current_round(s.game)
    if r is not None and r.state is not RoundState.REVEALED:
        slots.insert(0, r.slot)
    return slots


def drop_played_from_idle_slots(s: SessionState) -> None:
    """Repeats turned off: prefetch slots not prepared yet give up already-played tracks."""
    for slot in s.game.pipeline:
        if slot.track_ref in s.played and slot.asset_id is None:
            slot.track_ref = None


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
    if s.game.settings.allow_repeats:
        candidates = [t for t in pool(s) if t not in {slot.track_ref for slot in live_slots(s)}]
        # A one-track library may repeat after its previous round has finished.
        if candidates:
            s.rng.shuffle(candidates)
            queue.extend(candidates[1:])
            return candidates[0]
    return None


def pool_status(s: SessionState) -> PoolStatus:
    tracks = pool(s)
    size = len(tracks)
    fresh = sum(t not in s.played for t in tracks)
    reserved = sum(slot.track_ref is not None for slot in live_slots(s))
    if s.game.phase is GamePhase.IN_GAME:
        remaining = len(s.game.queue)
    else:
        remaining = size if s.game.settings.allow_repeats else fresh
    return PoolStatus(
        size=size,
        remaining=remaining,
        exhausted=size == 0 or (remaining == 0 and reserved == 0),
        fresh=fresh,
        played=size - fresh,
        unavailable=len(s.game.unavailable),
        reserved=reserved,
    )
