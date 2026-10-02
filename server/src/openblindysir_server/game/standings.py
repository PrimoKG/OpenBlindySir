"""Standings: competition ranking (1, 1, 3) of the projection of the score journal (§6.7)."""

from openblindysir_protocol.views import StandingRow
from openblindysir_server.game.state import SessionState, active_players, is_participant


def standings_player_ids(s: SessionState) -> list[str]:
    """Players ranked: not removed, and participants or holders of at least one event."""
    game_id = s.game.game_id
    return [
        p.id for p in active_players(s) if is_participant(p) or s.journal.has_events(game_id, p.id)
    ]


def standings(s: SessionState) -> list[StandingRow]:
    """Sorted by score then arrival; equal scores share a rank, no automatic tie-break."""
    scores = s.journal.scores(s.game.game_id)
    ids = standings_player_ids(s)
    ordered = sorted(ids, key=lambda pid: (-scores.get(pid, 0), s.players[pid].join_seq))
    rows: list[StandingRow] = []
    previous_score: int | None = None
    rank = 0
    for position, pid in enumerate(ordered, start=1):
        score = scores.get(pid, 0)
        if score != previous_score:
            rank = position
            previous_score = score
        rows.append(StandingRow(player_id=pid, score=score, rank=rank))
    return rows
