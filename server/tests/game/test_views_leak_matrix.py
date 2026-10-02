"""Anti-leak matrix of ``view_for`` by role and phase (spec §6.8, §20.1 item 7, patch 2).

Each view is checked as a whole serialised object, so a field added later is caught too.
Canaries: every player answers a unique text, tracks live in ``CanaryFolder`` and carry the
tags ``CanaryTitle``/``CanaryArtist``.
"""

import json
from typing import Any

import pytest
from builders import CANARY_ARTIST, CANARY_FOLDER, CANARY_TITLE, Scenario

FORBIDDEN_KEYS = {"relpath", "track_id", "draft_last_changed_at", "token", "upload_token"}
TRACK_CANARIES = (CANARY_TITLE, CANARY_ARTIST, CANARY_FOLDER, "track-0")
TIMING_KEYS = {"elapsed_ms", "order", "near_tie", "late_start_ms"}


def answer_text(pid: str) -> str:
    return f"ANSWER-{pid}"


def dump(sc: Scenario, pid: str) -> str:
    return sc.view(pid).model_dump_json()


def keys_of(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            found |= keys_of(value)
    elif isinstance(node, list):
        for item in node:
            found |= keys_of(item)
    return found


def all_answer(sc: Scenario, *, except_last: bool = False) -> None:
    pids = [*sc.player_ids, sc.host_id]
    if except_last:
        pids = pids[:-2]
    for pid in pids:
        assert pid is not None
        sc.submit(pid, answer_text(pid))


@pytest.fixture
def mc() -> Scenario:
    sc = Scenario()
    assert sc.set_mode("mc").error is None
    return sc


def assert_never(text: str) -> None:
    data = json.loads(text)
    assert not FORBIDDEN_KEYS & keys_of(data)
    assert '"t_' not in text  # no track id value


# --- OPEN -------------------------------------------------------------------------------------


def test_open_player_sees_only_own_answer_and_aggregate_progress() -> None:
    sc = Scenario()
    sc.to_open()
    all_answer(sc, except_last=True)
    a, b = sc.player_ids[:2]
    text = dump(sc, b)
    assert answer_text(b) in text
    assert answer_text(a) not in text
    assert not TIMING_KEYS & keys_of(json.loads(text))
    for canary in TRACK_CANARIES:
        assert canary not in text
    view = sc.view(b)
    assert view.round is not None
    assert view.round.progress is not None  # type: ignore[union-attr]
    assert_never(text)


def test_open_host_player_mode_identical_round_and_no_metadata() -> None:
    sc = Scenario()
    sc.to_open()
    all_answer(sc, except_last=True)
    host_text = sc.host_view().model_dump_json()
    for canary in TRACK_CANARIES:
        assert canary not in host_text
    for pid in sc.player_ids[:1]:
        assert answer_text(pid) not in host_text
    host_round = sc.host_view().round
    player_round = sc.view(sc.player_ids[2]).round
    assert host_round is not None
    assert player_round is not None
    assert host_round.progress == player_round.progress  # type: ignore[union-attr]
    assert_never(host_text)


def test_open_mc_sees_metadata_and_per_player_status_but_no_text(mc: Scenario) -> None:
    mc.to_open()
    a = mc.player_ids[0]
    mc.submit(a, answer_text(a))
    text = mc.host_view().model_dump_json()
    assert CANARY_FOLDER in text
    assert "track-" in text  # file name shown to the MC
    assert answer_text(a) not in text
    view = mc.host_view()
    assert view.kind == "host_mc"
    assert any(row.validated for row in view.round.per_player)  # type: ignore[union-attr]
    assert_never(text)


def test_players_entries_have_only_public_keys() -> None:
    sc = Scenario()
    sc.to_open()
    all_answer(sc, except_last=True)
    for pid in sc.s.players:
        data = json.loads(dump(sc, pid))
        for entry in data["players"]:
            assert set(entry) == {"id", "nickname", "online", "is_host", "is_me"}


def test_progress_hidden_below_three_expected() -> None:
    sc = Scenario(players=("A",))
    sc.to_open()
    view = sc.view(sc.pid("A"))
    assert view.round is not None
    assert view.round.progress is None  # type: ignore[union-attr]


def test_mc_host_excluded_from_expected(mc: Scenario) -> None:
    mc.to_open()
    view = mc.view(mc.player_ids[0])
    assert view.round is not None
    progress = view.round.progress  # type: ignore[union-attr]
    assert progress is not None
    assert progress.expected == len(mc.player_ids)


def test_progress_updates_without_identifiers() -> None:
    sc = Scenario()
    sc.to_open()
    b = sc.player_ids[1]
    before = sc.view(b).round.progress  # type: ignore[union-attr]
    sc.submit(sc.player_ids[0], "x")
    after = sc.view(b).round.progress  # type: ignore[union-attr]
    assert before is not None
    assert after is not None
    assert after.validated == before.validated + 1
    assert set(after.model_dump()) == {"validated", "expected"}


# --- REVIEW -----------------------------------------------------------------------------------


def test_review_player_sees_nothing_of_others() -> None:
    sc = Scenario()
    sc.to_open()
    all_answer(sc, except_last=True)
    sc.on_round("close")
    b = sc.player_ids[1]
    text = dump(sc, b)
    assert answer_text(sc.player_ids[0]) not in text
    assert not TIMING_KEYS & keys_of(json.loads(text))
    for canary in TRACK_CANARIES:
        assert canary not in text
    assert_never(text)


def test_review_host_sees_all_answers_and_timing_but_no_metadata() -> None:
    sc = Scenario()
    sc.to_open()
    all_answer(sc, except_last=True)
    sc.on_round("close")
    text = sc.host_view().model_dump_json()
    assert answer_text(sc.player_ids[0]) in text
    assert keys_of(json.loads(text)) >= TIMING_KEYS
    for canary in TRACK_CANARIES:
        assert canary not in text
    assert_never(text)


def test_review_mc_also_sees_metadata(mc: Scenario) -> None:
    mc.to_open()
    mc.on_round("close")
    assert CANARY_FOLDER in mc.host_view().model_dump_json()


# --- REVEALED -------------------------------------------------------------------------------


def test_revealed_everyone_sees_everything_about_the_round() -> None:
    sc = Scenario()
    sc.to_open()
    all_answer(sc, except_last=True)
    sc.on_round("close")
    sc.publish({sc.player_ids[0]: 3})
    for pid in sc.s.players:
        text = dump(sc, pid)
        assert answer_text(sc.player_ids[0]) in text
        assert CANARY_TITLE in text
        assert {"elapsed_ms", "order", "near_tie"} <= keys_of(json.loads(text))
        assert "late_start_ms" not in keys_of(json.loads(text)) or pid == sc.host_id
        assert_never(text)


def test_next_track_never_visible_before_its_reveal() -> None:
    sc = Scenario(rounds=3)
    sc.to_open()
    sc.on_round("close")
    sc.publish()
    r1_title = CANARY_TITLE
    assert r1_title in dump(sc, sc.player_ids[0])
    sc.on_round("next")
    sc.ready()
    text = dump(sc, sc.player_ids[0])
    assert CANARY_TITLE not in text


# --- FINAL_SCORE_REVIEW -----------------------------------------------------------------------


def test_final_review_draft_only_for_hosts() -> None:
    sc = Scenario(rounds=1)
    sc.to_review()
    sc.publish({sc.player_ids[0]: 2})
    sc.on_round("to_final_review")
    sc.on_phase("final_set", {"player_id": sc.player_ids[0], "delta": 7})
    player = json.loads(dump(sc, sc.player_ids[1]))
    assert not {"draft_delta", "score_after", "final_review"} & keys_of(player)
    host = json.loads(sc.host_view().model_dump_json())
    assert {"draft_delta", "score_after"} <= keys_of(host)


@pytest.mark.parametrize("phase", ["LOBBY", "OPEN", "REVIEW", "REVEALED", "FINAL"])
def test_never_relpath_track_id_or_draft_instant(phase: str, mc: Scenario) -> None:
    if phase != "LOBBY":
        mc.to_open()
        mc.draft(mc.player_ids[0], "brouillon")
    if phase in ("REVIEW", "REVEALED", "FINAL"):
        mc.on_round("close")
    if phase in ("REVEALED", "FINAL"):
        mc.publish()
    if phase == "FINAL":
        mc.on_round("end_game", {"current_round": "score"})
    for pid in mc.s.players:
        assert_never(dump(mc, pid))
