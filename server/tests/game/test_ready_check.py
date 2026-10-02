"""Ready check (spec §9.4)."""

from builders import Scenario

from openblindysir_protocol.enums import RoundState
from openblindysir_protocol.errors import ErrorCode
from openblindysir_server.game import commands as c


def unlock_all(sc: Scenario) -> None:
    for pid in sc.ids.values():
        sc.audio(pid, "IDLE")


def test_auto_start_when_every_expected_player_is_ready() -> None:
    sc = Scenario()
    unlock_all(sc)
    sc.start()
    pids = list(sc.ids.values())
    sc.ready(*pids[:-1])
    assert sc.current().state is RoundState.LOADING
    sc.ready(pids[-1])
    assert sc.current().state is RoundState.COUNTDOWN


def test_locked_and_offline_players_are_not_awaited() -> None:
    sc = Scenario()
    unlock_all(sc)
    locked, offline = sc.player_ids[:2]
    sc.audio(locked, "LOCKED")
    sc.d(c.Disconnected(offline))
    sc.start()
    others = [pid for pid in sc.ids.values() if pid not in (locked, offline)]
    sc.ready(*others)
    assert sc.current().state is RoundState.COUNTDOWN


def test_timeout_starts_anyway_even_without_auto_start() -> None:
    sc = Scenario()
    unlock_all(sc)
    sc.configure(auto_start=False)
    sc.start()
    sc.ready()
    assert sc.current().state is RoundState.LOADING
    sc.advance(10_000)
    assert sc.current().state is RoundState.COUNTDOWN


def test_nobody_unlocked_waits_for_timeout_or_force() -> None:
    sc = Scenario()
    sc.start()
    assert sc.current().state is RoundState.LOADING
    assert sc.on_round("force_start").error is ErrorCode.INVALID_STATE
    sc.advance(10_000)
    assert sc.current().state is RoundState.COUNTDOWN


def test_force_start_needs_one_ready_player() -> None:
    sc = Scenario()
    unlock_all(sc)
    sc.start()
    assert sc.on_round("force_start").error is ErrorCode.INVALID_STATE
    sc.ready(sc.player_ids[0])
    assert sc.on_round("force_start").error is None
    assert sc.current().state is RoundState.COUNTDOWN


def test_host_sees_ready_counts() -> None:
    sc = Scenario()
    unlock_all(sc)
    sc.start()
    sc.ready(sc.player_ids[0])
    check = sc.host_view().host.ready_check  # type: ignore[union-attr]
    assert check is not None
    assert (check.ready, check.expected, check.can_force) == (1, 4, True)


def test_countdown_then_open_at_official_start() -> None:
    sc = Scenario()
    sc.start()
    sc.ready()
    r = sc.current()
    assert r.official_start_at is not None
    assert r.official_start_at == sc.clock.now().mono_ms + 3_000
    sc.advance(2_999)
    assert r.state is RoundState.COUNTDOWN
    sc.advance(1)
    assert r.state is RoundState.OPEN
