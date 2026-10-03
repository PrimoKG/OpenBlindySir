"""HOST command permission table: one source for handler guards, the host view and tests.

``rule_ok`` is step 3 of the HOST check order (after "issuer is host" and the idempotency
key): whether the command is allowed in the current phase and round state.
"""

from collections.abc import Callable

from openblindysir_protocol.enums import (
    AssetState,
    BridgeState,
    EndGameMode,
    GamePhase,
    HostMode,
    RoundState,
)
from openblindysir_protocol.errors import StartBlocker
from openblindysir_protocol.host_commands import HOST_COMMAND_NAMES
from openblindysir_server.game import selection
from openblindysir_server.game.readiness import ready_ids
from openblindysir_server.game.state import (
    Player,
    SessionState,
    active_play,
    active_players,
    current_round,
    is_participant,
    undo_target,
)

Predicate = Callable[[SessionState, Player], bool]

SKIPPABLE = frozenset(
    {
        RoundState.QUEUED,
        RoundState.PREPARING,
        RoundState.LOADING,
        RoundState.COUNTDOWN,
        RoundState.OPEN,
    }
)


def start_blockers(s: SessionState) -> list[StartBlocker]:
    """Why ``start_game`` is impossible right now (empty list: it is possible)."""
    blockers: list[StartBlocker] = []
    if not s.game.settings.sources or not selection.pool(s):
        blockers.append(StartBlocker.NO_SOURCES)
    elif not s.game.settings.allow_repeats and all(t in s.played for t in selection.pool(s)):
        blockers.append(StartBlocker.POOL_EXHAUSTED)
    selected_bridges = {bridge_id for bridge_id, _ in s.game.settings.sources}
    if not any(
        b.state is BridgeState.ONLINE and b.bridge_id in selected_bridges
        for b in s.bridges.values()
    ):
        blockers.append(StartBlocker.BRIDGE_OFFLINE)
    if not any(is_participant(p) for p in active_players(s)):
        blockers.append(StartBlocker.NO_COMPETITORS)
    return blockers


def _phase(*phases: GamePhase) -> Predicate:
    allowed = frozenset(phases)
    return lambda s, issuer: s.game.phase in allowed


def _round(*states: RoundState) -> Predicate:
    allowed = frozenset(states)

    def check(s: SessionState, issuer: Player) -> bool:
        del issuer
        r = current_round(s.game)
        return r is not None and r.state in allowed

    return check


def _always(s: SessionState, issuer: Player) -> bool:
    del s, issuer
    return True


def _start_game(s: SessionState, issuer: Player) -> bool:
    del issuer
    return s.game.phase is GamePhase.LOBBY and not start_blockers(s)


def _end_game(s: SessionState, issuer: Player) -> bool:
    del issuer
    return s.game.phase is not GamePhase.FINAL_RESULTS


def _next(s: SessionState, issuer: Player) -> bool:
    del issuer
    r = current_round(s.game)
    return (
        r is not None
        and r.state in {RoundState.REVIEW, RoundState.REVEALED}
        and s.game.ending is None
    )


def _force_start(s: SessionState, issuer: Player) -> bool:
    del issuer
    r = current_round(s.game)
    return (
        r is not None
        and r.state is RoundState.LOADING
        and len(ready_ids(s, r)) >= 1
        and r.slot.asset_id in s.assets
        and s.assets[r.slot.asset_id].state is AssetState.STORED
    )


def _stop(s: SessionState, issuer: Player) -> bool:
    del issuer
    r = current_round(s.game)
    return (
        r is not None
        and r.state is RoundState.OPEN
        and r.paused_at is None
        and active_play(r) is not None
    )


def _unpaused_open(s: SessionState, issuer: Player) -> bool:
    r = current_round(s.game)
    return _round(RoundState.OPEN)(s, issuer) and r is not None and r.paused_at is None


def _pause(s: SessionState, issuer: Player) -> bool:
    r = current_round(s.game)
    return (
        r is not None
        and r.paused_at is None
        and (_unpaused_open(s, issuer) or _round(RoundState.REVIEW)(s, issuer))
    )


def _resume(s: SessionState, issuer: Player) -> bool:
    r = current_round(s.game)
    return (
        (_round(RoundState.OPEN)(s, issuer) or _round(RoundState.REVIEW)(s, issuer))
        and r is not None
        and r.paused_at is not None
        and r.resume_at is None
        and r.pause_ready
    )


def _set_mode(s: SessionState, issuer: Player) -> bool:
    if s.game.phase is not GamePhase.IN_GAME:
        return True
    r = current_round(s.game)
    return issuer.host_mode is HostMode.PLAYER and (
        r is None or r.state not in {RoundState.COUNTDOWN, RoundState.OPEN}
    )


def _undo(s: SessionState, issuer: Player) -> bool:
    del issuer
    return undo_target(s.game) is not None


def _to_final_review(s: SessionState, issuer: Player) -> bool:
    del issuer
    r = current_round(s.game)
    return (
        r is not None
        and r.state in {RoundState.REVIEW, RoundState.REVEALED}
        and (r.number >= s.game.settings.rounds or s.game.ending is EndGameMode.SCORE)
    )


HOST_RULES: dict[str, Predicate] = {
    "select_track": lambda s, issuer: (
        issuer.host_mode is HostMode.MC and s.game.phase in {GamePhase.LOBBY, GamePhase.IN_GAME}
    ),
    "configure": _phase(GamePhase.LOBBY, GamePhase.IN_GAME, GamePhase.FINAL_RESULTS),
    "set_mode": _set_mode,
    "start_game": _start_game,
    "new_game": _phase(GamePhase.FINAL_RESULTS),
    "end_game": _end_game,
    "end_session": _always,
    "next": _next,
    "force_start": _force_start,
    "replay": _unpaused_open,
    "stop": _stop,
    "pause": _pause,
    "resume": _resume,
    "skip": _round(*SKIPPABLE),
    "add_time": _unpaused_open,
    "close": _round(RoundState.OPEN),
    "score_draft": _phase(GamePhase.FINAL_SCORE_REVIEW),
    "publish": lambda s, issuer: False,
    "track_metadata": _phase(GamePhase.FINAL_SCORE_REVIEW),
    "undo_publish": lambda s, issuer: False,
    "adjust": lambda s, issuer: False,
    "to_final_review": _to_final_review,
    "final_set": _phase(GamePhase.FINAL_SCORE_REVIEW),
    "final_reset": _phase(GamePhase.FINAL_SCORE_REVIEW),
    "final_validate": _phase(GamePhase.FINAL_SCORE_REVIEW),
    "kick": _always,
    "rename": _always,
    "participation": _phase(GamePhase.LOBBY),
    "join_lock": _always,
}
assert set(HOST_RULES) == set(HOST_COMMAND_NAMES)


def rule_ok(cmd: str, s: SessionState, issuer: Player) -> bool:
    return HOST_RULES[cmd](s, issuer)


def allowed(s: SessionState, issuer: Player) -> list[str]:
    """HOST commands allowed now, in protocol declaration order."""
    return [cmd for cmd in HOST_COMMAND_NAMES if rule_ok(cmd, s, issuer)]
