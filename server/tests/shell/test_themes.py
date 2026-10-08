"""The host's preview, search and actual selection use the same bounded criteria."""

import pytest
from conftest import BRIDGE_ID, ORIGIN, Harness, catalog
from pydantic import TypeAdapter

from openblindysir_protocol.client import ClientMessage
from openblindysir_protocol.enums import AssetState, GamePhase, Role
from openblindysir_server.game import commands as c
from openblindysir_server.game import selection
from openblindysir_server.game.metadata import musical_metadata
from openblindysir_server.game.state import (
    AssetRecord,
    CatalogEntryData,
    Metadata,
    Settings,
    ThemeFilterData,
    TrackRef,
)
from openblindysir_server.library import management


def test_draft_preflight_checks_requested_references_and_excludes_played_disabled(harness: Harness):
    _, headers, refs = themed_library(harness)
    state = harness.runtime.engine.state
    state.game.settings.answer_mode = "title"  # The saved rules are deliberately different.
    state.metadata[refs[0]] = Metadata(
        title="Complete", artist="Artist", album="Album", year=2012, featuring="Guest"
    )
    state.metadata[refs[1]] = Metadata(enabled=False)
    state.played.add(refs[2])
    response = harness.client.post(
        "/api/host/library/selection",
        headers=headers,
        json={
            "sources": [{"bridge_id": BRIDGE_ID, "folder_prefix": ""}],
            "scoring_criteria": ["title", "artist", "album", "year", "featuring"],
            "allow_repeats": False,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["reference_eligible"], body["reference_ready"]) == (4, 1)
    assert body["missing_by_criterion"] == {
        "title": 0,
        "artist": 3,
        "album": 3,
        "year": 1,
        "featuring": 3,
    }
    assert len(body["reference_issues"]) == 3
    assert all("artist" in row["missing_references"] for row in body["reference_issues"])


def test_preflight_uses_grading_cleanup_aliases_and_explicit_clears(harness: Harness):
    _, headers, refs = themed_library(harness)
    state = harness.runtime.engine.state
    for ref in refs[1:]:
        state.metadata[ref] = Metadata(enabled=False)
    state.imported_metadata[refs[0]] = Metadata()
    state.assets["cached"] = AssetRecord(
        "cached",
        refs[0],
        "job",
        AssetState.EVICTED,
        0,
        0,
        track_duration_ms=120_000,
        title="Artist - Song (Official Video)",
        artist=None,
    )
    payload = {
        "sources": [{"bridge_id": BRIDGE_ID, "folder_prefix": ""}],
        "scoring_criteria": ["title", "artist"],
    }
    response = harness.client.post("/api/host/library/selection", headers=headers, json=payload)
    assert response.json()["reference_ready"] == 1
    state.metadata[refs[0]] = Metadata(cleared_fields=["artist"])
    response = harness.client.post("/api/host/library/selection", headers=headers, json=payload)
    assert response.json()["missing_by_criterion"] == {"title": 0, "artist": 1}
    state.metadata[refs[0]] = Metadata(aliases={"artist": ["Artist"]})
    response = harness.client.post("/api/host/library/selection", headers=headers, json=payload)
    assert response.json()["reference_ready"] == 1


def test_search_preview_and_pool_share_cached_titles_and_respect_explicit_clears(harness: Harness):
    _, headers, refs = themed_library(harness)
    state = harness.runtime.engine.state
    state.imported_metadata[refs[0]] = Metadata()
    state.assets["cached"] = AssetRecord(
        "cached",
        refs[0],
        "job",
        AssetState.EVICTED,
        0,
        0,
        track_duration_ms=120_000,
        title="Cached title",
        artist="Cached artist",
    )
    filters = {"query": "Cached title artist"}
    state.game.settings.selection_filter = ThemeFilterData(**filters)
    response = harness.client.get(
        "/api/host/library/search",
        headers=headers,
        params={"q": filters["query"]},
    ).json()
    assert response["total"] == 1
    assert response["tracks"][0]["in_pool"] is True
    preview = harness.client.post(
        "/api/host/library/selection",
        headers=headers,
        json={
            "sources": [{"bridge_id": BRIDGE_ID, "folder_prefix": ""}],
            "selection_filter": filters,
        },
    ).json()
    assert preview["available"] == 1
    assert preview["examples"][0]["title"] == "Cached title"
    assert selection.pool(state) == [refs[0]]
    state.game.queue.extend(refs)
    assert selection.take(state) == refs[0]
    state.metadata[refs[0]] = Metadata(cleared_fields=["title", "artist"])
    assert selection.pool(state) == []
    assert (
        harness.client.get(
            "/api/host/library/search",
            headers=headers,
            params={"q": filters["query"]},
        ).json()["total"]
        == 0
    )


@pytest.mark.parametrize("field", ["genres", "languages", "tags", "linked_to"])
def test_every_valid_metadata_label_can_be_selected(harness: Harness, field: str):
    _, headers, refs = themed_library(harness)
    state = harness.runtime.engine.state
    label = "Long label " + "a" * 245
    state.imported_metadata[refs[0]] = Metadata(**{field: [label]})
    filters = {field: [label]}
    response = harness.client.post(
        "/api/host/library/selection",
        headers=headers,
        json={
            "sources": [{"bridge_id": BRIDGE_ID, "folder_prefix": ""}],
            "selection_filter": filters,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["available"] == 1
    search_field = {
        "genres": "genre",
        "languages": "language",
        "tags": "tag",
        "linked_to": "linked_to",
    }[field]
    response = harness.client.get(
        "/api/host/library/search",
        headers=headers,
        params={search_field: label},
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1


def test_symbolic_tags_and_search_do_not_match_every_track(harness: Harness):
    _, headers, refs = themed_library(harness)
    state = harness.runtime.engine.state
    state.imported_metadata[refs[0]] = Metadata(tags=["🎮"])
    state.imported_metadata[refs[1]] = Metadata(tags=["🎵"])
    for query in ({"tag": "🎮"}, {"q": "🎮"}):
        result = harness.client.get("/api/host/library/search", headers=headers, params=query)
        assert result.status_code == 200
        assert [r["track_id"] for r in result.json()["tracks"]] == [refs[0].track_id]
    state.game.settings.selection_filter = ThemeFilterData(tags=["🎮"])
    assert selection.pool(state) == [refs[0]]


@pytest.mark.parametrize("sort", ["genre", "language"])
@pytest.mark.parametrize("descending", ["true", "false"])
def test_unknown_categories_sort_last(harness: Harness, sort, descending):
    _, headers, refs = themed_library(harness)
    response = harness.client.get(
        "/api/host/library/search",
        headers=headers,
        params={"sort": sort, "descending": descending},
    )
    assert response.json()["tracks"][-1]["track_id"] == refs[4].track_id


def test_facets_stay_within_the_selected_folder(harness: Harness):
    _, headers, refs = themed_library(harness)
    state = harness.runtime.engine.state
    state.imported_metadata[refs[5]] = Metadata(tags=["Other folder"])
    state.catalogs[BRIDGE_ID].entries[refs[5].track_id] = CatalogEntryData(
        "Other/t5.flac",
        "Other",
        "flac",
        100,
    )
    result = harness.client.get(
        "/api/host/library/search",
        headers=headers,
        params={"folder": "Anime"},
    ).json()
    assert "Other folder" not in result["tags"]


@pytest.mark.parametrize("change", ["role", "phase", "epoch"])
def test_preview_never_returns_private_data_after_access_changes(
    harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
):
    pid, headers, _ = themed_library(harness)
    state = harness.runtime.engine.state

    async def changed_access(function, *args):
        result = function(*args)
        if change == "role":
            state.players[pid].role = Role.PLAYER
        elif change == "phase":
            state.game.phase = GamePhase.IN_GAME
        else:
            state.epoch = "0000000000000002"
        return result

    monkeypatch.setattr(management, "run_in_threadpool", changed_access)
    response = harness.client.post(
        "/api/host/library/selection",
        headers=headers,
        json={"sources": [{"bridge_id": BRIDGE_ID, "folder_prefix": ""}]},
    )
    assert response.status_code == (403 if change == "role" else 409)
    assert set(response.json()) == {"error"}
    assert harness.client.app.state.obs.library_search_busy is False


def test_worker_snapshot_detaches_selection_lists(harness: Harness):
    _, _, _ = themed_library(harness)
    state = harness.runtime.engine.state
    snapshot = management.search_snapshot(state)
    state.game.settings.selection_filter.tags.append("Changed")
    assert snapshot.game.settings.selection_filter.tags == []


def themed_library(h: Harness):
    pid, token = h.join("Theme host")
    h.elevate(token)
    body = catalog()
    entries = {
        e["track_id"]: CatalogEntryData(e["relpath"], e["folder"], e["ext"], e["size"])
        for e in body["entries"]
    }
    h.runtime.dispatch(c.BridgeConnected(BRIDGE_ID, "Example", "example", body["catalog_hash"], 6))
    h.runtime.dispatch(c.CatalogLoaded(BRIDGE_ID, "Example", body["catalog_hash"], entries))
    state = h.runtime.engine.state
    refs = [TrackRef(BRIDGE_ID, e["track_id"]) for e in body["entries"]]
    for ref, metadata in zip(
        refs,
        [
            Metadata(
                title="Générique de Wakfu",
                genres=["Hip-Hop"],
                languages=["Français"],
                year=2012,
                tags=["Génériques"],
                linked_to=["Wakfu"],
            ),
            Metadata(
                title="Dragon Ball",
                genres=["Pop"],
                languages=["fr"],
                year=2012,
                tags=["Génériques"],
            ),
            Metadata(title="English example", genres=["Rap"], languages=["en"], year=2012),
            Metadata(title="Later example", genres=["Rap"], languages=["fr"], year=2013),
            Metadata(title="Unknown language", year=2012),
            Metadata(title="Unknown year", genres=["Rap"], languages=["fr"]),
        ],
        strict=True,
    ):
        state.imported_metadata[ref] = metadata
    state.game.settings.sources = [(BRIDGE_ID, "")]
    return pid, {**h.cookie(token), "Origin": ORIGIN}, refs


def test_combined_preview_matches_the_actual_pool_and_counts_overlaps_once(harness: Harness):
    pid, headers, refs = themed_library(harness)
    state = harness.runtime.engine.state
    state.played.add(refs[0])
    filters = {
        "genres": ["Rap", "Pop"],
        "languages": ["french"],
        "year_min": 2012,
        "year_max": 2012,
    }
    sources = [{"bridge_id": BRIDGE_ID, "folder_prefix": prefix} for prefix in ("", "Anime")]
    result = harness.client.post(
        "/api/host/library/selection",
        headers=headers,
        json={"sources": sources, "selection_filter": filters},
    )
    assert result.status_code == 200, result.text
    assert (result.json()["matching"], result.json()["available"], result.json()["fresh"]) == (
        2,
        2,
        1,
    )
    assert result.json()["languages"] == ["en", "fr", "und"]
    msg = TypeAdapter(ClientMessage).validate_python(
        {
            "t": "HOST",
            "cmd": "configure",
            "expected_phase": "LOBBY",
            "args": {"sources": sources, "selection_filter": filters},
        }
    )
    outcome = harness.runtime.dispatch(c.HostIn(pid, msg))
    assert outcome.error is None
    assert set(selection.pool(state)) == {refs[0], refs[1]}
    assert set(selection.build_queue(state, include_played=False)) == {refs[1]}
    response = harness.client.get("/api/host/library/search?pool_only=true", headers=headers)
    assert {r["track_id"] for r in response.json()["tracks"]} == {
        refs[0].track_id,
        refs[1].track_id,
    }


@pytest.mark.parametrize(
    ("filters", "indexes"),
    [
        ({"languages": ["und"]}, [4]),
        ({"genres": ["Rap"], "languages": ["en"]}, [2]),
        ({"tags": ["generiques"], "linked_to": ["wakfu"]}, [0]),
        ({"query": "wakfu francais rap 2012"}, [0]),
        ({"year_min": 2012, "year_max": 2012}, [0, 1, 2, 4]),
    ],
)
def test_theme_aliases_accents_words_and_unknown_values(harness: Harness, filters, indexes):
    _, headers, refs = themed_library(harness)
    result = harness.client.post(
        "/api/host/library/selection",
        headers=headers,
        json={
            "sources": [{"bridge_id": BRIDGE_ID, "folder_prefix": ""}],
            "selection_filter": filters,
        },
    )
    assert result.status_code == 200, result.text
    assert {r["track_id"] for r in result.json()["examples"]} == {refs[i].track_id for i in indexes}


def test_disabled_offline_and_unavailable_tracks_do_not_inflate_capacity(harness: Harness):
    _, headers, refs = themed_library(harness)
    state = harness.runtime.engine.state
    state.metadata[refs[1]] = Metadata(enabled=False)
    state.game.unavailable.add(refs[2])
    data = {"sources": [{"bridge_id": BRIDGE_ID, "folder_prefix": ""}]}
    result = harness.client.post("/api/host/library/selection", headers=headers, json=data).json()
    assert result["matching"] == 5
    assert result["available"] == 4
    harness.runtime.dispatch(c.BridgeDisconnected(BRIDGE_ID))
    result = harness.client.post("/api/host/library/selection", headers=headers, json=data).json()
    assert result["available"] == result["fresh"] == 0


def test_year_sort_keeps_unknown_values_last_in_both_directions(harness: Harness):
    _, headers, refs = themed_library(harness)
    for descending in ("true", "false"):
        result = harness.client.get(
            f"/api/host/library/search?sort=year&descending={descending}", headers=headers
        )
        assert result.status_code == 200
        assert result.json()["tracks"][-1]["track_id"] == refs[5].track_id
    result = harness.client.get(
        "/api/host/library/search?genre=Rap&language=anglais&year_min=2012&year_max=2012",
        headers=headers,
    )
    assert [r["track_id"] for r in result.json()["tracks"]] == [refs[2].track_id]


@pytest.mark.parametrize(
    "filters",
    [
        {"year_min": 2013, "year_max": 2012},
        {"year_min": 999},
        {"tags": ["bad\u0000value"]},
        {"genres": ["x"] * 17},
    ],
)
def test_invalid_filters_are_refused_before_selection_changes(harness: Harness, filters):
    _, headers, _ = themed_library(harness)
    original = harness.runtime.engine.state.game.settings.copy()
    response = harness.client.post(
        "/api/host/library/selection",
        headers=headers,
        json={"sources": [], "selection_filter": filters},
    )
    assert response.status_code == 400
    assert harness.runtime.engine.state.game.settings == original


def test_selection_preview_is_private_and_origin_checked(harness: Harness):
    _, headers, _ = themed_library(harness)
    data = {"sources": []}
    assert harness.client.post("/api/host/library/selection", json=data).status_code == 401
    _, token = harness.join("Player")
    assert (
        harness.client.post(
            "/api/host/library/selection",
            headers={**harness.cookie(token), "Origin": ORIGIN},
            json=data,
        ).status_code
        == 403
    )
    assert (
        harness.client.post(
            "/api/host/library/selection",
            headers={**headers, "Origin": "https://other.example"},
            json=data,
        ).status_code
        == 403
    )


def test_metadata_v3_import_and_export_preserve_genres_languages(harness: Harness):
    _, headers, refs = themed_library(harness)
    response = harness.client.post(
        "/api/host/metadata/import",
        headers=headers,
        json={
            "version": 3,
            "rows": [
                {
                    "bridge_id": BRIDGE_ID,
                    "relpath": "Anime/t0.flac",
                    "genres": ["Pop"],
                    "languages": ["en"],
                }
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 1
    exported = harness.client.get("/api/host/metadata", headers=headers).json()
    assert exported["version"] == 3
    row = next(r for r in exported["rows"] if r["relpath"] == "Anime/t0.flac")
    assert (row["genres"], row["languages"], row["year"]) == (["Pop"], ["en"], 2012)
    assert selection.track_exists(harness.runtime.engine.state, refs[0])


def test_copying_settings_detaches_filter_lists():
    original = Settings(selection_filter=ThemeFilterData(genres=["Rap"]))
    copied = original.copy()
    copied.selection_filter.genres.append("Pop")
    assert original.selection_filter.genres == ["Rap"]


def test_exact_legacy_tags_supply_facets_but_an_explicit_clear_blocks_inference(harness: Harness):
    _, headers, refs = themed_library(harness)
    state = harness.runtime.engine.state
    state.imported_metadata[refs[0]] = Metadata(tags=["Hip-hop", "Français", "Génériques"])
    resolved = musical_metadata(state, refs[0])
    assert resolved.genres == ["Hip-Hop"]
    assert resolved.languages == ["fr"]
    state.metadata[refs[0]] = Metadata(genres=[], languages=[])
    resolved = musical_metadata(state, refs[0])
    assert resolved.genres == resolved.languages == []
    response = harness.client.get("/api/host/library/search?genre=Rap", headers=headers)
    assert refs[0].track_id not in {row["track_id"] for row in response.json()["tracks"]}
