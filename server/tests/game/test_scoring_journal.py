"""Score journal (spec §6.4–6.5, §13, §20.1 item 4)."""

import pytest
from builders import Scenario

from openblindysir_protocol.enums import ScoreKind
from openblindysir_protocol.errors import ErrorCode
from openblindysir_server.game.scoring import ScoreJournal, ScoresFrozenError

G = "g_test"


def naive_score(journal: ScoreJournal, game_id: str, player_id: str) -> int:
    revoked = journal.revoked_ids()
    return sum(
        ev.delta
        for ev in journal.events(game_id)
        if ev.player_id == player_id and ev.id not in revoked
    )


def check_invariant(sc: Scenario) -> None:
    game_id = sc.s.game.game_id
    for pid in sc.s.players:
        assert sc.s.journal.score(game_id, pid) == naive_score(sc.s.journal, game_id, pid)


def test_publish_creates_one_event_per_non_zero_delta() -> None:
    sc = Scenario()
    a, b, c3 = sc.player_ids
    sc.to_review()
    sc.publish({a: 3, b: -1, c3: 0})
    events = sc.s.journal.events()
    assert [(ev.player_id, ev.delta, ev.kind) for ev in events] == [
        (a, 3, ScoreKind.ROUND),
        (b, -1, ScoreKind.ROUND),
    ]
    check_invariant(sc)


def test_drafts_never_create_events() -> None:
    sc = Scenario()
    a = sc.player_ids[0]
    sc.to_review()
    sc.on_round("score_draft", {"player_id": a, "points": 3})
    sc.on_round("score_draft", {"player_id": a, "points": 0})
    sc.on_round("score_draft", {"player_id": a, "points": -2})
    assert sc.s.journal.events() == ()


def test_host_scores_himself_in_review() -> None:
    sc = Scenario()
    assert sc.host_id is not None
    sc.to_review()
    sc.publish({sc.host_id: 2})
    assert sc.s.journal.score(sc.s.game.game_id, sc.host_id) == 2


def test_undo_revokes_and_restores_draft() -> None:
    sc = Scenario()
    a = sc.player_ids[0]
    r = sc.to_review()
    sc.publish({a: 3})
    sc.host("undo_publish", round_id=r.id, args={})
    kinds = [ev.kind for ev in sc.s.journal.events()]
    assert kinds == [ScoreKind.ROUND, ScoreKind.REVOKE]
    assert sc.s.journal.score(sc.s.game.game_id, a) == 0
    assert r.score_draft == {a: 3}
    sc.publish()
    assert sc.s.journal.score(sc.s.game.game_id, a) == 3
    check_invariant(sc)


def test_adjust_anyone_including_host_and_negative() -> None:
    sc = Scenario()
    assert sc.host_id is not None
    sc.to_open()
    args = {"player_id": sc.host_id, "delta": -4, "op_id": "op-0000001", "note": "faute"}
    assert sc.on_phase("adjust", args).error is None
    assert sc.on_phase("adjust", args).error is ErrorCode.STALE_COMMAND  # same op_id
    assert sc.s.journal.score(sc.s.game.game_id, sc.host_id) == -4
    check_invariant(sc)


def test_adjust_round_must_belong_to_game() -> None:
    sc = Scenario()
    sc.to_open()
    args = {
        "player_id": sc.player_ids[0],
        "delta": 1,
        "op_id": "op-0000002",
        "round_id": "r_000999",
    }
    assert sc.on_phase("adjust", args).error is ErrorCode.INVALID_ARGS


def test_journal_rejects_invalid_events() -> None:
    journal = ScoreJournal()
    with pytest.raises(ValueError, match="delta 0"):
        journal.append(
            game_id=G, player_id="p_1", delta=0, kind=ScoreKind.ADJUSTMENT, by="h", at_wall_ms=0
        )
    with pytest.raises(ValueError, match="bounds"):
        journal.append(
            game_id=G, player_id="p_1", delta=1001, kind=ScoreKind.ADJUSTMENT, by="h", at_wall_ms=0
        )
    with pytest.raises(ValueError, match="round id"):
        journal.append(
            game_id=G, player_id="p_1", delta=1, kind=ScoreKind.ROUND, by="h", at_wall_ms=0
        )
    adj = journal.append(
        game_id=G, player_id="p_1", delta=2, kind=ScoreKind.ADJUSTMENT, by="h", at_wall_ms=0
    )
    with pytest.raises(ValueError, match="round event"):
        journal.append(
            game_id=G,
            player_id="p_1",
            delta=0,
            kind=ScoreKind.REVOKE,
            by="h",
            at_wall_ms=0,
            revokes=(adj.id,),
        )


def test_revoke_only_once() -> None:
    journal = ScoreJournal()
    ev = journal.append(
        game_id=G,
        player_id="p_1",
        delta=3,
        kind=ScoreKind.ROUND,
        by="h",
        at_wall_ms=0,
        round_id="r_1",
    )
    journal.append(
        game_id=G,
        player_id="p_1",
        delta=0,
        kind=ScoreKind.REVOKE,
        by="h",
        at_wall_ms=0,
        round_id="r_1",
        revokes=(ev.id,),
    )
    with pytest.raises(ValueError, match="already revoked"):
        journal.append(
            game_id=G,
            player_id="p_1",
            delta=0,
            kind=ScoreKind.REVOKE,
            by="h",
            at_wall_ms=0,
            round_id="r_1",
            revokes=(ev.id,),
        )
    assert journal.score(G, "p_1") == 0


def test_frozen_game_refuses_events() -> None:
    journal = ScoreJournal()
    journal.freeze(G)
    with pytest.raises(ScoresFrozenError):
        journal.append(
            game_id=G, player_id="p_1", delta=1, kind=ScoreKind.ADJUSTMENT, by="h", at_wall_ms=0
        )


def test_journal_has_no_stored_score() -> None:
    assert set(ScoreJournal().__dict__) == {"_events", "_revoked", "_frozen"}
