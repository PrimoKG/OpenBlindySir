"""Players (spec §7.4): identity, connection, host role and mode switch rules."""

from builders import Scenario

from openblindysir_protocol.enums import ConnectionState
from openblindysir_protocol.errors import CloseCode, ErrorCode
from openblindysir_server.game import CoreConfig, players
from openblindysir_server.game import commands as c
from openblindysir_server.game import effects as e


def test_nickname_unique_case_insensitive_after_nfkc() -> None:
    sc = Scenario(players=("Ayoub",))
    assert sc.d(c.Join("AYOUB")).error is ErrorCode.NICKNAME_TAKEN
    assert sc.d(c.Join("Ａｙｏｕｂ")).error is ErrorCode.NICKNAME_TAKEN  # noqa: RUF001
    assert sc.d(c.Join("evil" + chr(0x202E))).error is ErrorCode.NICKNAME_INVALID


def test_game_full() -> None:
    sc = Scenario(players=("A", "B"), config=CoreConfig(max_players=3))
    assert sc.d(c.Join("C")).error is ErrorCode.GAME_FULL


def test_kick_closes_with_4003_and_frees_the_nickname() -> None:
    sc = Scenario(players=("Fantome",))
    ghost = sc.pid("Fantome")
    outcome = sc.on_phase("kick", {"player_id": ghost})
    assert e.CloseConnection(ghost, CloseCode.KICKED) in outcome.effects
    assert e.RevokeTokens((ghost,)) in outcome.effects
    assert sc.s.players[ghost].connection is ConnectionState.REMOVED
    assert sc.d(c.Join("Fantome")).error is None


def test_offline_player_stays_in_standings() -> None:
    sc = Scenario()
    a = sc.player_ids[0]
    sc.d(c.Disconnected(a))
    view = sc.view(sc.player_ids[1])
    assert view.standings == []
    sc.on_phase("end_game", {"current_round": "score"})
    sc.finalize()
    assert any(row.player_id == a for row in sc.view(sc.player_ids[1]).standings)
    assert not next(p for p in view.players if p.id == a).online


def test_rename() -> None:
    sc = Scenario(players=("Fantome",))
    pid = sc.pid("Fantome")
    assert sc.on_phase("rename", {"player_id": pid, "nickname": "Adam"}).error is None
    assert sc.s.players[pid].nickname == "Adam"


def test_mode_switch_rules() -> None:
    sc = Scenario()
    assert sc.set_mode("mc").error is None
    assert sc.set_mode("player").error is None
    sc.to_open()
    assert sc.set_mode("mc").error is ErrorCode.INVALID_STATE  # round being played
    sc.on_round("close")
    assert sc.set_mode("mc").error is None
    assert sc.set_mode("player").error is ErrorCode.INVALID_STATE  # an MC saw the tracks


def test_leave_revokes_token() -> None:
    sc = Scenario()
    a = sc.player_ids[0]
    outcome = sc.d(c.Leave(a))
    assert e.RevokeTokens((a,)) in outcome.effects
    assert not sc.engine.player_exists(a)


def test_repeated_join_leave_has_a_total_identity_cap_and_new_game_reclaims_it(monkeypatch):
    sc = Scenario()
    monkeypatch.setattr(players, "MAX_SESSION_IDENTITIES", 10)
    for _ in range(6):
        outcome = sc.d(c.Join("Synthetic churn"))
        assert outcome.error is None
        assert sc.d(c.Leave(outcome.value)).error is None
    assert len(sc.s.players) == 10
    for _ in range(100):
        assert sc.d(c.Join("Synthetic churn")).error is ErrorCode.GAME_FULL
    assert len(sc.s.players) == 10
    sc.to_open()
    sc.on_phase("end_game", {"current_round": "score"})
    sc.finalize()
    archive = sc.s.archives[0]
    assert sc.on_phase("new_game").error is None
    assert len(sc.s.players) == 4
    assert sc.s.archives == [archive]
    assert sc.d(c.Join("Synthetic churn")).error is None
