"""Server-side answer timing (spec §6.3, §20.1 item 3, ADR 0003)."""

from builders import Scenario

from openblindysir_protocol.enums import AnswerStatus
from openblindysir_server.game import commands as c


def test_elapsed_measured_from_official_start() -> None:
    sc = Scenario()
    a = sc.player_ids[0]
    r = sc.to_open()
    sc.advance(4_237)
    sc.submit(a, "x")
    assert r.answers[a].elapsed_ms == 4_237


def test_elapsed_unchanged_by_replay_and_stop() -> None:
    sc = Scenario()
    a, b = sc.player_ids[:2]
    r = sc.to_open()
    official = r.official_start_at
    sc.advance(2_000)
    sc.on_round("replay", {"play_id": r.plays[-1].play_id})
    sc.advance(3_000)
    sc.on_round("stop", {"play_id": r.plays[-1].play_id})
    sc.advance(1_000)
    sc.submit(a, "x")
    sc.submit(b, "y")
    assert r.official_start_at == official
    assert r.answers[a].elapsed_ms == 6_000
    assert r.answers[b].elapsed_ms == 6_000


def test_order_strict_for_ten_submits_at_the_same_instant() -> None:
    names = tuple(f"P{i}" for i in range(10))
    sc = Scenario(players=names, host=None)
    sc.host_id = sc.join("Hote")
    sc.d(c.ElevateHost(sc.host_id))
    sc.configure(
        rounds=3, sources=[{"bridge_id": sc.s.bridges.copy().popitem()[0], "folder_prefix": ""}]
    )
    r = sc.to_open()
    pids = [sc.pid(n) for n in names]
    for pid in pids:
        sc.submit(pid, "x")
    orders = [r.answers[pid].order for pid in pids]
    assert orders == list(range(1, 11))
    assert all(r.answers[pid].elapsed_ms == r.answers[pids[0]].elapsed_ms for pid in pids)


def test_near_tie_threshold_is_strict() -> None:
    sc = Scenario(players=("A", "B", "C", "D"))
    a, b, cc, d = (sc.pid(n) for n in ("A", "B", "C", "D"))
    r = sc.to_open()
    sc.advance(1_000)
    sc.submit(a, "x")
    sc.advance(299)
    sc.submit(b, "x")
    sc.advance(300)
    sc.submit(cc, "x")
    sc.advance(301)
    sc.submit(d, "x")
    assert not r.answers[a].near_tie
    assert r.answers[b].near_tie
    assert not r.answers[cc].near_tie
    assert not r.answers[d].near_tie


def test_late_start_from_ready_received_after_start() -> None:
    sc = Scenario()
    slow = sc.player_ids[0]
    sc.audio(slow, "IDLE")  # audio unlocked: the ready check awaits this player
    sc.start()
    others = [pid for pid in sc.ids.values() if pid != slow]
    sc.ready(*others)
    r = sc.current()
    assert r.state.value == "LOADING"  # the slow player is still awaited
    sc.advance(10_000)  # ready timeout
    assert r.official_start_at is not None
    sc.advance_to(r.official_start_at + 2_300)
    sc.audio(slow, "READY", r.slot.asset_id)
    sc.submit(slow, "x")
    sc.on_round("close")
    assert r.answers[slow].late_start_ms == 2_300
    host = sc.host_view()
    row = next(x for x in host.round.answers if x.player_id == slow)  # type: ignore[union-attr]
    assert row.late_start_ms == 2_300


def test_disconnection_during_playback_counts_as_late_start() -> None:
    sc = Scenario(clip_s=20.0)
    a = sc.player_ids[0]
    r = sc.to_open()
    assert r.official_start_at is not None
    sc.advance(5_000)
    sc.d(c.Disconnected(a))
    sc.advance(3_000)
    sc.d(c.Connected(a, "0.1.0"))
    assert r.listen[a].offline_since is not None  # Connected alone does not close an outage
    sc.audio(a, "PLAYING", r.slot.asset_id)
    sc.submit(a, "x")
    sc.on_round("close")
    assert r.answers[a].late_start_ms == 3_000


def test_draft_instants_never_influence_order_or_views() -> None:
    def run(draft_delay: int) -> tuple[object, ...]:
        sc = Scenario()
        a, b = sc.player_ids[:2]
        r = sc.to_open()
        sc.advance(draft_delay)
        sc.draft(b, "brouillon")
        sc.advance(2_000 - draft_delay)
        sc.submit(a, "x")
        sc.advance(100)
        sc.submit(b, "y")
        sc.on_round("close")
        assert r.answers[b].status is AnswerStatus.LOCKED
        host = sc.host_view().model_dump_json()
        return (host, tuple((x.order, x.elapsed_ms) for x in r.answers.values()))

    assert run(100) == run(1_900)
