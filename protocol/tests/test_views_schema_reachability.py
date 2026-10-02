"""Static anti-leak checks on the JSON Schema of the views (spec §6.8, §20.1 item 7).

A datum an audience must not see has no field reachable from that audience's root model.
"""

from collections.abc import Iterator
from typing import Any

import pytest

from openblindysir_protocol.export import web_json_schema

SCHEMA = web_json_schema()
DEFS: dict[str, Any] = SCHEMA["$defs"]
VIEW_ROOTS = ("PlayerView", "HostPlayerModeView", "HostMcView")


def refs_in(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value.rsplit("/", 1)[-1]
            else:
                yield from refs_in(value)
    elif isinstance(node, list):
        for item in node:
            yield from refs_in(item)


def reachable(root: str, *, avoid: frozenset[str] = frozenset()) -> set[str]:
    seen: set[str] = set()
    stack = [root]
    while stack:
        name = stack.pop()
        if name in seen or name in avoid:
            continue
        seen.add(name)
        stack.extend(refs_in(DEFS[name]))
    return seen


def view_defs() -> set[str]:
    names: set[str] = set()
    for root in VIEW_ROOTS:
        names |= reachable(root)
    return names


def test_mc_types_reachable_only_from_host_mc_view() -> None:
    mc_types = {"McTrackInfo", "McPanel", "RoundMcOpen", "McOpenRow"}
    assert mc_types <= reachable("HostMcView")
    assert not mc_types & reachable("PlayerView")
    assert not mc_types & reachable("HostPlayerModeView")


@pytest.mark.parametrize("root", VIEW_ROOTS)
def test_track_metadata_only_under_reveal_private_review_or_recap(root: str) -> None:
    assert "RevealTrack" in reachable(root)
    without_reveal = reachable(
        root, avoid=frozenset({"RoundRevealed", "RoundHostReview", "HistoryEntry"})
    )
    assert "RevealTrack" not in without_reveal
    assert "RevealRow" not in without_reveal


def test_private_host_rows_never_reachable_from_player_view() -> None:
    forbidden = {
        "ReviewRow",
        "RoundHostReview",
        "HostPanel",
        "PlayerOps",
    }
    assert not forbidden & reachable("PlayerView")
    assert not {"FinalReviewRow", "HistoryEntry"} & reachable(
        "PlayerView", avoid=frozenset({"FinalResults"})
    )


def test_history_entry_only_through_host_panel_or_final_results() -> None:
    for root in ("HostPlayerModeView", "HostMcView"):
        assert "HistoryEntry" in reachable(root)
        assert "HistoryEntry" not in reachable(root, avoid=frozenset({"HostPanel", "FinalResults"}))


@pytest.mark.parametrize(
    "name", ["relpath", "track_id", "draft_last_changed_at", "token", "upload_token", "path"]
)
def test_forbidden_property_names_absent(name: str) -> None:
    for def_name in view_defs():
        assert name not in DEFS[def_name].get("properties", {}), def_name


def test_view_player_has_only_public_fields() -> None:
    assert set(DEFS["ViewPlayer"]["properties"]) == {
        "id",
        "nickname",
        "online",
        "is_host",
        "is_me",
        "spectator",
        "team",
    }


def test_player_review_has_only_my_answer() -> None:
    assert set(DEFS["RoundPlayerReview"]["properties"]) == {
        "state",
        "round_id",
        "number",
        "my_answer",
    }


def test_my_answer_has_no_timing_field() -> None:
    assert set(DEFS["MyAnswer"]["properties"]) == {"status", "text", "draft_text"}


def test_open_round_for_players_has_only_aggregate_progress() -> None:
    assert set(DEFS["Progress"]["properties"]) == {"validated", "expected"}
    assert "per_player" not in DEFS["RoundOpen"]["properties"]


def test_no_mode_split() -> None:
    assert not [name for name in DEFS if name.endswith(("-Input", "-Output"))]
