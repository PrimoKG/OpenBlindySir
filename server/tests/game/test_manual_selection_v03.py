"""Manual choices respect ownership, preparation, repeat rules and recovery."""

import json
import random

import pytest
from builders import BRIDGE_ID, Scenario

from openblindysir_protocol.enums import JobFailureCode, RoundState
from openblindysir_protocol.errors import ErrorCode
from openblindysir_server.auth.sessions import SessionRegistry
from openblindysir_server.game import GameEngine, Instant, SecretIds
from openblindysir_server.game import commands as c
from openblindysir_server.game.effects import SendPlay
from openblindysir_server.game.state import TrackRef
from openblindysir_server.persistence import SnapshotStore


def choice(sc, number, ref=None, *, revision=None, by=None):
    return sc.host(
        "select_track",
        by=by,
        expected_phase=sc.s.game.phase.value,
        args={
            "round_number": number,
            "expected_revision": sc.s.game.selection_revision if revision is None else revision,
            "bridge_id": ref.bridge_id if ref else None,
            "track_id": ref.track_id if ref else None,
        },
    )


def refs(sc):
    return [TrackRef(BRIDGE_ID, tid) for tid in sc.s.catalogs[BRIDGE_ID].entries]


def test_only_mc_hosts_can_choose_and_player_schemas_never_receive_choices():
    sc = Scenario()
    ref = refs(sc)[0]
    assert choice(sc, 1, ref, by=sc.player_ids[0]).error is ErrorCode.NOT_HOST
    assert choice(sc, 1, ref).error is ErrorCode.INVALID_STATE
    sc.set_mode("mc")
    assert choice(sc, 1, ref).error is None
    assert sc.host_view().mc.manual_choices[0].track_id == ref.track_id
    for pid in sc.player_ids:
        text = sc.view(pid).model_dump_json()
        assert ref.track_id not in text
        assert "manual_choices" not in text
    sc.set_mode("player")
    assert not sc.s.game.manual_tracks
    assert "manual_choices" not in sc.host_view().model_dump_json()


def test_prepared_choices_wait_for_explicit_launch_and_cannot_change():
    sc = Scenario()
    sc.set_mode("mc")
    ref, other, *_ = refs(sc)
    assert choice(sc, 1, ref).error is None
    sc.start()
    sc.ready(*sc.player_ids)
    r = sc.current()
    assert r.slot.track_ref == ref
    assert r.state is RoundState.LOADING
    assert not sc.effects_of(SendPlay)
    assert choice(sc, 1, other).error is ErrorCode.INVALID_STATE
    assert sc.on_round("force_start").error is None
    assert r.state is RoundState.COUNTDOWN
    assert choice(sc, 1, other).error is ErrorCode.INVALID_STATE
    for pid in sc.player_ids:
        assert ref.track_id not in sc.view(pid).model_dump_json()


def test_revision_prevents_concurrent_edits_and_reservations_cannot_duplicate():
    sc = Scenario()
    sc.set_mode("mc")
    ref, other, *_ = refs(sc)
    assert choice(sc, 2, ref, revision=0).error is None
    assert choice(sc, 1, other, revision=0).error is ErrorCode.STALE_COMMAND
    assert choice(sc, 1, ref).error is ErrorCode.INVALID_ARGS
    assert choice(sc, 2).error is None
    assert choice(sc, 1, ref).error is None


def test_played_offline_and_outside_sources_choices_are_refused():
    sc = Scenario()
    sc.set_mode("mc")
    ref = refs(sc)[0]
    sc.s.played.add(ref)
    assert choice(sc, 1, ref).error is ErrorCode.POOL_EXHAUSTED
    sc.configure(allow_repeats=True)
    assert choice(sc, 1, ref).error is None
    choice(sc, 1)
    sc.configure(sources=[])
    assert choice(sc, 1, ref).error is ErrorCode.NO_SOURCES
    sc.configure(sources=[{"bridge_id": BRIDGE_ID, "folder_prefix": ""}])
    sc.d(c.BridgeDisconnected(BRIDGE_ID))
    assert choice(sc, 1, ref).error is ErrorCode.BRIDGE_OFFLINE


@pytest.mark.parametrize(
    "failure", [JobFailureCode.NOT_FOUND, JobFailureCode.DECODE_ERROR, JobFailureCode.NO_AUDIO]
)
def test_failure_keeps_choice_explicit_and_allows_replacement(failure):
    sc = Scenario(auto_serve=False)
    sc.set_mode("mc")
    ref, replacement, *_ = refs(sc)
    choice(sc, 1, ref)
    sc.start()
    job = sc.pending_jobs[-1]
    sc.d(c.JobFailedIn(job.job_id, failure))
    r = sc.current()
    assert r.slot.manual_error.value == failure.value
    assert r.slot.track_ref == ref
    assert r.slot.asset_id is None
    assert choice(sc, 1, replacement).error is None
    assert r.slot.track_ref == replacement
    assert r.slot.manual_error is None
    assert r.slot.asset_id is not None


def test_bridge_loss_allows_random_fallback_without_stuck_round():
    sc = Scenario(auto_serve=False)
    sc.set_mode("mc")
    choice(sc, 1, refs(sc)[0])
    sc.start()
    sc.d(c.BridgeDisconnected(BRIDGE_ID))
    assert sc.current().slot.manual_error.value == "BRIDGE_OFFLINE"
    assert choice(sc, 1).error is None
    assert not sc.current().slot.manual
    assert "skip" in sc.host_view().host.commands
    assert "end_game" in sc.host_view().host.commands


def test_skipping_current_does_not_consume_future_numbered_manual_choice():
    sc = Scenario(tracks=6)
    sc.set_mode("mc")
    ref = refs(sc)[0]
    choice(sc, 2, ref)
    sc.start()
    assert sc.s.game.pipeline[0].round_number == 2
    assert sc.s.game.pipeline[0].track_ref == ref
    sc.on_round("skip")
    assert sc.current().number == 1
    assert sc.current().slot.track_ref != ref
    assert sc.s.game.pipeline[0].track_ref == ref
    sc.ready(*sc.player_ids)
    sc.advance_to(sc.current().official_start_at)
    sc.on_round("close")
    sc.on_round("next")
    assert sc.current().number == 2
    assert sc.current().slot.track_ref == ref
    assert sc.current().state is RoundState.LOADING


def test_configure_prunes_invalid_plans_and_revisions_survive_serialization():
    sc = Scenario()
    sc.set_mode("mc")
    choice(sc, 3, refs(sc)[0])
    revision = sc.s.game.selection_revision
    sc.configure(rounds=2)
    assert not sc.s.game.manual_tracks
    assert sc.s.game.selection_revision == revision + 1
    assert json.loads(sc.host_view().model_dump_json())["mc"]["selection_revision"] == revision + 1


@pytest.mark.parametrize("legacy", [False, True])
def test_snapshot_restores_choices_and_reads_old_neutral_fields(tmp_path, legacy):
    sc = Scenario()
    sc.set_mode("mc")
    ref = refs(sc)[0]
    choice(sc, 2, ref)
    store = SnapshotStore(tmp_path, ("synthetic-only",))
    store.save(sc.engine, SessionRegistry(3600000), sc.clock.now())
    if legacy:
        path = tmp_path / "session.json"
        data = json.loads(path.read_text())
        data["format"] = 2
        fields = data["state"]["game"]["fields"]
        fields.pop("manual_tracks")
        fields.pop("selection_revision")
        path.write_text(json.dumps(data))
    now = Instant(0, sc.clock.now().wall_ms + 1000)
    restored = GameEngine(sc.s.config, ids=SecretIds(), rng=random.Random(1), started_at=now)
    assert store.restore(restored, SessionRegistry(3600000), now)
    assert restored.state.game.manual_tracks == ({} if legacy else {2: ref})
    assert restored.state.game.selection_revision == (0 if legacy else 1)
