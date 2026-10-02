"""Append-only ScoreEvent journal: the single source of truth for scores (spec §13, ADR 0007).

``score(player) = Σ delta of active events`` (not revoked). No score is ever stored, drafts
are never events, and a game's journal is frozen once its results are validated.
"""

from collections.abc import Iterator
from dataclasses import dataclass

from openblindysir_protocol.base import POINTS_BOUND
from openblindysir_protocol.enums import ScoreKind


@dataclass(frozen=True, slots=True)
class ScoreEvent:
    id: int  # global, strictly increasing
    game_id: str
    player_id: str
    round_id: str | None
    delta: int  # |delta| <= 1000; 0 iff kind == revoke
    kind: ScoreKind
    by: str  # player id of the issuing host
    at_wall_ms: int
    note: str | None
    revokes: tuple[int, ...]  # non-empty iff kind == revoke


class ScoresFrozenError(Exception):
    """An event was appended to a game whose results are validated."""


class ScoreJournal:
    def __init__(self) -> None:
        self._events: list[ScoreEvent] = []
        self._revoked: set[int] = set()
        self._frozen: set[str] = set()

    def append(
        self,
        *,
        game_id: str,
        player_id: str,
        delta: int,
        kind: ScoreKind,
        by: str,
        at_wall_ms: int,
        round_id: str | None = None,
        note: str | None = None,
        revokes: tuple[int, ...] = (),
    ) -> ScoreEvent:
        """Validate (defence in depth, independent of the handlers) then append one event."""
        if game_id in self._frozen:
            raise ScoresFrozenError(game_id)
        self._validate(
            game_id=game_id,
            player_id=player_id,
            delta=delta,
            kind=kind,
            round_id=round_id,
            revokes=revokes,
        )
        event = ScoreEvent(
            id=len(self._events) + 1,
            game_id=game_id,
            player_id=player_id,
            round_id=round_id,
            delta=delta,
            kind=kind,
            by=by,
            at_wall_ms=at_wall_ms,
            note=note,
            revokes=revokes,
        )
        self._events.append(event)
        self._revoked.update(revokes)
        return event

    def _validate(
        self,
        *,
        game_id: str,
        player_id: str,
        delta: int,
        kind: ScoreKind,
        round_id: str | None,
        revokes: tuple[int, ...],
    ) -> None:
        if abs(delta) > POINTS_BOUND:
            raise ValueError("delta out of bounds")
        if kind is ScoreKind.REVOKE:
            if delta != 0 or not revokes:
                raise ValueError("a revoke has delta 0 and targets events")
            for target_id in revokes:
                if not 1 <= target_id <= len(self._events) or target_id in self._revoked:
                    raise ValueError("revoke target missing or already revoked")
                target = self._events[target_id - 1]
                if (
                    target.kind is not ScoreKind.ROUND
                    or target.game_id != game_id
                    or target.round_id != round_id
                    or target.player_id != player_id
                ):
                    raise ValueError("a revoke targets a round event of the same player")
            return
        if delta == 0 or revokes:
            raise ValueError("only a revoke may have delta 0 or targets")
        if kind is ScoreKind.ROUND and round_id is None:
            raise ValueError("a round event needs a round id")
        if kind is ScoreKind.FINAL_ADJUSTMENT and round_id is not None:
            raise ValueError("a final adjustment has no round id")

    def events(self, game_id: str | None = None) -> tuple[ScoreEvent, ...]:
        if game_id is None:
            return tuple(self._events)
        return tuple(event for event in self._events if event.game_id == game_id)

    def revoked_ids(self) -> frozenset[int]:
        return frozenset(self._revoked)

    def active(self, game_id: str) -> Iterator[ScoreEvent]:
        """Events that count: not revoked and not themselves revokes."""
        for event in self._events:
            if (
                event.game_id == game_id
                and event.kind is not ScoreKind.REVOKE
                and event.id not in self._revoked
            ):
                yield event

    def score(self, game_id: str, player_id: str) -> int:
        return sum(event.delta for event in self.active(game_id) if event.player_id == player_id)

    def scores(self, game_id: str) -> dict[str, int]:
        totals: dict[str, int] = {}
        for event in self.active(game_id):
            totals[event.player_id] = totals.get(event.player_id, 0) + event.delta
        return totals

    def round_points(self, game_id: str, round_id: str, player_id: str) -> int:
        return sum(
            event.delta
            for event in self.active(game_id)
            if event.kind is ScoreKind.ROUND
            and event.round_id == round_id
            and event.player_id == player_id
        )

    def has_events(self, game_id: str, player_id: str) -> bool:
        return any(event.player_id == player_id for event in self.active(game_id))

    def freeze(self, game_id: str) -> None:
        self._frozen.add(game_id)

    def is_frozen(self, game_id: str) -> bool:
        return game_id in self._frozen

    def frozen_games(self) -> frozenset[str]:
        return frozenset(self._frozen)
