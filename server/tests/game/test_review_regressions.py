"""Regressions found by the adversarial review of the game core (2026-10-02)."""

from builders import Scenario

from openblindysir_protocol.enums import AssetState, JobFailureCode, RoundState
from openblindysir_server.game import commands as c


def test_evicting_current_asset_in_loading_prepares_it_again() -> None:
    sc = Scenario()
    sc.start()
    r = sc.current()
    asset = r.slot.asset_id
    assert asset is not None
    sc.d(c.AssetEvicted(asset))
    assert sc.s.assets[asset].state is AssetState.EVICTED
    sc.advance(10_000)  # the ready timeout must not crash the engine
    sc.advance(10_000)
    assert r.state in (RoundState.LOADING, RoundState.COUNTDOWN, RoundState.OPEN)
    assert r.slot.asset_id != asset


def test_prefetch_depth_two_keeps_the_prepared_n_plus_2() -> None:
    sc = Scenario(rounds=5)
    sc.configure(prefetch_depth=2)
    sc.to_open()
    sc.on_round("close")
    assert len(sc.s.game.pipeline) == 2
    n2 = sc.s.game.pipeline[1].asset_id
    assert n2 is not None
    sc.on_round("next")
    assert sc.s.assets[n2].state is AssetState.STORED
    assert any(slot.asset_id == n2 for slot in sc.s.game.pipeline)


def test_queue_full_slot_woken_by_a_late_result() -> None:
    sc = Scenario(auto_serve=False)
    sc.start()
    first = sc.pending_jobs.pop(0)
    sc.on_round("skip")  # cancels the first job
    second = sc.pending_jobs.pop(0)
    sc.d(c.JobFailedIn(second.job_id, JobFailureCode.QUEUE_FULL))
    assert sc.current().slot.waiting_bridge
    sc.d(c.JobFailedIn(first.job_id, JobFailureCode.CANCELLED))  # late: the Bridge freed a place
    assert not sc.current().slot.waiting_bridge
    assert sc.pending_jobs


def test_turning_repeats_off_removes_played_tracks() -> None:
    sc = Scenario(rounds=6, tracks=3)
    for _ in range(3):
        sc.to_open()
        sc.on_round("close")
    sc.on_phase("configure", {"allow_repeats": True})
    assert len(sc.s.game.queue) + len(sc.s.game.pipeline) == 3
    sc.on_phase("configure", {"allow_repeats": False})
    assert not [t for t in sc.s.game.queue if t in sc.s.played]


def test_forged_ready_messages_are_not_recorded() -> None:
    sc = Scenario()
    pid = sc.player_ids[0]
    for index in range(50):
        sc.audio(pid, "READY", f"a_{index:022d}")
    assert all(asset in sc.s.assets for asset in sc.s.asset_ready)
