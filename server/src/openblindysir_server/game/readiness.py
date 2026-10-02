"""Ready check sets (spec §9.4)."""

from openblindysir_protocol.enums import AudioState
from openblindysir_server.game.state import Player, Round, SessionState, online_participants


def expected_ready(s: SessionState) -> list[Player]:
    """Online participants whose audio is unlocked; offline or LOCKED players are not awaited."""
    return [p for p in online_participants(s) if p.audio_state is not AudioState.LOCKED]


def ready_ids(s: SessionState, r: Round) -> set[str]:
    """Online participants who declared READY for the round's asset."""
    ready = s.asset_ready.get(r.slot.asset_id or "", {})
    return {p.id for p in online_participants(s) if p.id in ready}
