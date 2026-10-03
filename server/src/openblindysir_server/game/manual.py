"""MC-only choices before preparation, with an authoritative revision and explicit play."""

import posixpath

from openblindysir_protocol.enums import RoundState
from openblindysir_protocol.errors import ErrorCode
from openblindysir_protocol.host_commands import HostSelectTrack
from openblindysir_protocol.views import ManualTrackChoice
from openblindysir_server.game import assets, selection
from openblindysir_server.game.clock import Instant
from openblindysir_server.game.effects import EffectSink
from openblindysir_server.game.game_flow import require_phase, require_rule
from openblindysir_server.game.metadata import musical_metadata
from openblindysir_server.game.rejections import require
from openblindysir_server.game.state import Player, SessionState, Slot, TrackRef, current_round


def slots_by_number(s: SessionState) -> dict[int, Slot]:
    r = current_round(s.game)
    result = {r.number: r.slot} if r else {}
    if r:
        result.update(
            {slot.round_number or r.number + i + 1: slot for i, slot in enumerate(s.game.pipeline)}
        )
    return result


def editable(s: SessionState, number: int) -> bool:
    if not 1 <= number <= s.game.settings.rounds:
        return False
    r = current_round(s.game)
    if r and (
        number < r.number
        or (number == r.number and r.state not in {RoundState.QUEUED, RoundState.PREPARING})
    ):
        return False
    slot = slots_by_number(s).get(number)
    return slot is None or slot.asset_id is None


def h_select_track(
    s: SessionState, issuer: Player, msg: HostSelectTrack, at: Instant, fx: EffectSink
) -> None:
    del at
    require_phase(s, msg.expected_phase)
    require_rule("select_track", s, issuer)
    args = msg.args
    require(args.expected_revision == s.game.selection_revision, ErrorCode.STALE_COMMAND)
    require(editable(s, args.round_number), ErrorCode.INVALID_STATE)
    slots = slots_by_number(s)
    slot = slots.get(args.round_number)
    ref = TrackRef(args.bridge_id, args.track_id) if args.bridge_id and args.track_id else None
    if ref is not None:
        require(selection.track_exists(s, ref), ErrorCode.NOT_FOUND)
        require(assets.bridge_online(s, ref.bridge_id), ErrorCode.BRIDGE_OFFLINE)
        require(ref in selection.pool(s), ErrorCode.NO_SOURCES)
        require(s.game.settings.allow_repeats or ref not in s.played, ErrorCode.POOL_EXHAUSTED)
        reserved = {value for n, value in s.game.manual_tracks.items() if n != args.round_number}
        reserved.update(
            value.track_ref
            for n, value in slots.items()
            if n != args.round_number and value.track_ref is not None
        )
        require(ref not in reserved, ErrorCode.INVALID_ARGS)
    if slot is not None:
        slot.track_ref = ref
        slot.manual = ref is not None
        slot.manual_error = None
        slot.waiting_bridge = False
        slot.same_track_retries = 0
        slot.attempts = 1 if ref else 0
    elif ref is None:
        s.game.manual_tracks.pop(args.round_number, None)
    else:
        s.game.manual_tracks[args.round_number] = ref
    s.game.selection_revision += 1
    s.game.queue = selection.build_queue(s, include_played=s.game.settings.allow_repeats)
    s.touched = True
    fx.log("manual_track_selected", round_number=args.round_number, manual=ref is not None)


def choices(s: SessionState) -> list[ManualTrackChoice]:
    r = current_round(s.game)
    first = r.number if r else 1
    slots = slots_by_number(s)
    result = []
    for number in range(first, s.game.settings.rounds + 1):
        slot = slots.get(number)
        ref = slot.track_ref if slot else s.game.manual_tracks.get(number)
        catalog = s.catalogs.get(ref.bridge_id) if ref else None
        entry = catalog.entries.get(ref.track_id) if catalog and ref else None
        meta = musical_metadata(s, ref) if ref else None
        result.append(
            ManualTrackChoice(
                round_number=number,
                bridge_id=ref.bridge_id if ref else None,
                track_id=ref.track_id if ref else None,
                filename=posixpath.basename(entry.relpath) if entry else None,
                bridge_name=catalog.bridge_name if catalog else None,
                folder=entry.folder if entry else None,
                title=meta.title if meta else None,
                artist=meta.artist if meta else None,
                locked=not editable(s, number),
                manual=slot.manual if slot else ref is not None,
                error=slot.manual_error.value if slot and slot.manual_error else None,
            )
        )
    return result
