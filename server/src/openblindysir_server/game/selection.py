"""Track selection (spec §6.9): folder-prefix pool, shuffled queue, no repeat in a session."""

from collections import deque

from openblindysir_protocol.enums import BridgeState, GamePhase, RoundState
from openblindysir_protocol.views import PoolStatus
from openblindysir_server.game.metadata import musical_metadata
from openblindysir_server.game.state import SessionState, Slot, TrackRef, current_round
from openblindysir_server.game.themes import matches_theme


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
            meta = musical_metadata(s, TrackRef(bridge_id, track_id))
            if (
                matches(entry.relpath, prefix)
                and meta.enabled is not False
                and matches_theme(meta, entry.relpath, s.game.settings.selection_filter)
            ):
                found.add(TrackRef(bridge_id, track_id))
    return sorted(found - s.game.unavailable)


def live_slots(s: SessionState) -> list[Slot]:
    """Slots whose track is in use: the pipeline and the current round while it is live."""
    slots: list[Slot] = list(s.game.pipeline)
    r = current_round(s.game)
    if r is not None and r.state not in {RoundState.REVIEW, RoundState.REVEALED}:
        slots.insert(0, r.slot)
    return slots


def drop_played_from_idle_slots(s: SessionState) -> None:
    """Repeats turned off: prefetch slots not prepared yet give up already-played tracks."""
    for slot in s.game.pipeline:
        if slot.track_ref in s.played and slot.asset_id is None:
            slot.track_ref = None


def prune_manual_plans(s: SessionState) -> None:
    g = s.game
    valid = set(pool(s))
    planned = {
        number: ref
        for number, ref in g.manual_tracks.items()
        if number <= g.settings.rounds
        and ref in valid
        and (g.settings.allow_repeats or ref not in s.played)
    }
    if planned != g.manual_tracks:
        g.manual_tracks = planned
        g.selection_revision += 1


def build_queue(s: SessionState, *, include_played: bool) -> deque[TrackRef]:
    """Shuffled queue; tracks never played in the session always come first."""
    in_use = {slot.track_ref for slot in live_slots(s) if slot.track_ref is not None}
    in_use.update(s.game.manual_tracks.values())
    candidates = [t for t in pool(s) if t not in in_use and online(s, t)]
    fresh = [t for t in candidates if t not in s.played]
    s.rng.shuffle(fresh)
    repeats: list[TrackRef] = []
    if include_played:
        repeats = [t for t in candidates if t in s.played]
        s.rng.shuffle(repeats)
    if s.game.settings.balance_folders:
        fresh = balanced(s, fresh)
        repeats = balanced(s, repeats)
    return deque(fresh + repeats)


def balanced(s: SessionState, tracks: list[TrackRef]) -> list[TrackRef]:
    groups: dict[tuple[str, str], deque[TrackRef]] = {}
    for ref in tracks:
        entry = s.catalogs[ref.bridge_id].entries[ref.track_id]
        # Deepest selected folder wins; overlapping selections never duplicate a track.
        prefixes = [
            f
            for b, f in s.game.settings.sources
            if b == ref.bridge_id and matches(entry.relpath, f)
        ]
        key = (ref.bridge_id, max(prefixes, key=len, default=entry.folder) or entry.folder)
        groups.setdefault(key, deque()).append(ref)
    keys = list(groups)
    s.rng.shuffle(keys)
    result: list[TrackRef] = []
    while any(groups.values()):
        for key in keys:
            if groups[key]:
                result.append(groups[key].popleft())
    return result


def track_exists(s: SessionState, ref: TrackRef) -> bool:
    catalog = s.catalogs.get(ref.bridge_id)
    return catalog is not None and ref.track_id in catalog.entries


def online(s: SessionState, ref: TrackRef) -> bool:
    info = s.bridges.get(ref.bridge_id)
    return info is not None and info.state is BridgeState.ONLINE


def take(s: SessionState) -> TrackRef | None:
    """Next usable track of the queue, or None when the pool is exhausted."""
    queue = s.game.queue
    while queue:
        ref = queue.popleft()
        reserved = set(s.game.manual_tracks.values()) | {slot.track_ref for slot in live_slots(s)}
        if (
            ref not in s.game.unavailable
            and musical_metadata(s, ref).enabled is not False
            and track_exists(s, ref)
            and matches_theme(
                musical_metadata(s, ref),
                s.catalogs[ref.bridge_id].entries[ref.track_id].relpath,
                s.game.settings.selection_filter,
            )
            and ref not in reserved
            and online(s, ref)
            and (s.game.settings.allow_repeats or ref not in s.played)
        ):
            return ref
    if s.game.settings.allow_repeats:
        reserved = set(s.game.manual_tracks.values()) | {slot.track_ref for slot in live_slots(s)}
        candidates = [t for t in pool(s) if t not in reserved and online(s, t)]
        # A one-track library may repeat after its previous round has finished.
        if candidates:
            if s.game.settings.balance_folders:
                candidates = balanced(s, candidates)
            else:
                s.rng.shuffle(candidates)
            queue.extend(candidates[1:])
            return candidates[0]
    return None


def new_slot(s: SessionState, number: int) -> Slot:
    manual = s.game.manual_tracks.pop(number, None)
    ref = manual or take(s)
    return Slot(
        track_ref=ref, attempts=1 if ref else 0, round_number=number, manual=manual is not None
    )


def pool_status(s: SessionState) -> PoolStatus:
    tracks = pool(s)
    size = len(tracks)
    fresh = sum(t not in s.played for t in tracks)
    reserved_refs = {slot.track_ref for slot in live_slots(s)} | set(s.game.manual_tracks.values())
    reserved = len((reserved_refs - {None}) - s.played)
    if s.game.phase is GamePhase.IN_GAME:
        valid = set(tracks)
        remaining = sum(ref in valid for ref in s.game.queue) + sum(
            ref in valid for ref in s.game.manual_tracks.values()
        )
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
