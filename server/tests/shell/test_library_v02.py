"""Private source controls, metadata diagnostics, multi-Bridge and recovery permissions."""

import asyncio
import gzip
import io
import json
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import BLIND, BRIDGE_ID, ORIGIN, SECRET, Harness, bridge_hello, catalog, put_catalog
from fastapi import Request
from pydantic import TypeAdapter

from openblindysir_protocol.client import ClientMessage
from openblindysir_server.game import commands as c
from openblindysir_server.game import selection
from openblindysir_server.game.state import CatalogEntryData, Metadata, TrackRef
from openblindysir_server.library import routes

CLIENT = TypeAdapter(ClientMessage)
SECOND = "12345678-1234-1234-1234-123456789abd"


def test_corrupt_deflate_archive_is_rejected_without_changing_metadata(harness: Harness) -> None:
    _, token, _ = private_library(harness)
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("metadata-000001.json", '{"version":2,"rows":[]}')
    raw = bytearray(content.getvalue())
    # Reserved DEFLATE block type: valid ZIP headers, invalid compressed content.
    raw[30 + len("metadata-000001.json")] = 0x06
    state = harness.runtime.engine.state
    revision = state.metadata_revision
    response = harness.client.post(
        "/api/host/metadata/import-archive",
        headers={**harness.cookie(token), "Origin": ORIGIN, "Content-Type": "application/zip"},
        content=bytes(raw),
    )
    assert response.status_code == 400
    assert state.metadata_revision == revision
    assert not state.imported_metadata
    # An invalid archive must also release the shared library worker slot.
    assert (
        harness.client.get("/api/host/metadata/export", headers=harness.cookie(token)).status_code
        == 200
    )


def test_metadata_pack_reimport_and_revision_conflict(harness: Harness) -> None:
    _, token, body = private_library(harness)
    headers = {**harness.cookie(token), "Origin": ORIGIN}
    entry = body["entries"][0]
    edit = {
        "bridge_id": BRIDGE_ID,
        "track_id": entry["track_id"],
        "expected_revision": 0,
        "metadata": {"title": "Confirmed", "artist": "Artist", "cleared_fields": ["album"]},
    }
    assert harness.client.put("/api/host/metadata", headers=headers, json=edit).status_code == 200
    edit["metadata"]["title"] = "Stale replacement"
    assert harness.client.put("/api/host/metadata", headers=headers, json=edit).status_code == 409
    exported = harness.client.get("/api/host/metadata/export", headers=headers)
    assert exported.status_code == 200
    assert exported.headers["x-next-offset"] == ""
    imported = harness.client.post(
        "/api/host/metadata/import-archive",
        headers={**headers, "Content-Type": "application/zip"},
        content=exported.content,
    )
    assert imported.status_code == 200
    assert imported.json()["accepted"] == 1
    result = harness.client.get("/api/host/library/search?quality=ready", headers=headers).json()
    assert result["total"] == 1
    assert result["tracks"][0]["cleared_fields"] == ["album"]
    assert result["tracks"][0]["title"] == "Confirmed"
    pid, player_token = harness.join("Player")
    assert pid
    assert (
        harness.client.get(
            "/api/host/metadata/export", headers=harness.cookie(player_token)
        ).status_code
        == 403
    )


def host_command(h: Harness, pid: str, cmd: str, args: dict | None = None) -> None:
    msg = CLIENT.validate_json(
        json.dumps(
            {
                "t": "HOST",
                "cmd": cmd,
                "expected_phase": h.runtime.engine.state.game.phase.value,
                "args": args or {},
            }
        )
    )
    assert h.runtime.dispatch(c.HostIn(pid, msg)).error is None


def private_library(h: Harness) -> tuple[str, str, dict]:
    pid, token = h.join("Host")
    h.elevate(token)
    body = catalog()
    entries = {
        e["track_id"]: CatalogEntryData(e["relpath"], e["folder"], e["ext"], e["size"])
        for e in body["entries"]
    }
    h.runtime.dispatch(c.BridgeConnected(BRIDGE_ID, "PC", "example", body["catalog_hash"], 6))
    h.runtime.dispatch(c.CatalogLoaded(BRIDGE_ID, "PC", body["catalog_hash"], entries))
    return pid, token, body


def test_search_sorts_before_paginating_and_searches_session_corrections(harness: Harness) -> None:
    _, token, body = private_library(harness)
    headers = harness.cookie(token)
    root = "/api/host/library/search?sort=filename"
    full = harness.client.get(root, headers=headers).json()
    pages = [
        harness.client.get(f"{root}&limit=2&offset={offset}", headers=headers).json()
        for offset in range(0, full["total"], 2)
    ]
    assert [track for page in pages for track in page["tracks"]] == full["tracks"]
    names = [track["filename"].casefold() for track in full["tracks"]]
    assert names == sorted(names)
    descending = harness.client.get(f"{root}&descending=true", headers=headers).json()
    assert descending["tracks"] == list(reversed(full["tracks"]))
    entry = body["entries"][0]
    harness.runtime.engine.state.metadata[TrackRef(BRIDGE_ID, entry["track_id"])] = Metadata(
        title="Example corrected title", artist="Example corrected artist"
    )
    corrected = harness.client.get(
        "/api/host/library/search?q=corrected&sort=artist&limit=1", headers=headers
    ).json()
    assert corrected["total"] == 1
    assert corrected["tracks"][0]["title"] == "Example corrected title"
    assert harness.client.get(f"{root}&limit=101", headers=headers).status_code == 400
    assert harness.client.get(f"{root}&sort=unknown", headers=headers).status_code == 400


def receive(ws: object, kind: str) -> dict:
    for _ in range(30):
        msg = ws.receive_json()
        if msg["t"] == kind:
            return msg
    raise AssertionError(kind)


def test_catalog_completion_revision_changes_even_when_the_tracks_do_not(harness: Harness) -> None:
    _, token, body = private_library(harness)
    before = harness.client.get("/api/host/library", headers=harness.cookie(token))
    state = harness.runtime.engine.state
    harness.runtime.dispatch(
        c.CatalogLoaded(BRIDGE_ID, "PC", body["catalog_hash"], state.catalogs[BRIDGE_ID].entries)
    )
    after = harness.client.get("/api/host/library", headers=harness.cookie(token))
    assert before.json() == after.json()
    assert json.loads(before.headers["x-catalog-revisions"]) == {BRIDGE_ID: 1}
    assert json.loads(after.headers["x-catalog-revisions"]) == {BRIDGE_ID: 2}


def test_replacing_bridge_rejects_an_old_catalog_upload_already_in_progress(
    harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started, release = threading.Event(), asyncio.Event()
    original = routes._read_gzip

    async def delayed(request: Request) -> bytes:
        raw = await original(request)
        started.set()
        await release.wait()
        return raw

    monkeypatch.setattr(routes, "_read_gzip", delayed)
    body = catalog()
    with (
        harness.bridge_ws() as old,
        harness.bridge_ws() as replacement,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        old.send_text(bridge_hello(body["catalog_hash"], 6))
        token = receive(old, "WELCOME")["catalog_upload_token"]
        future = executor.submit(put_catalog, harness, body, token)
        try:
            assert started.wait(3)
            replacement.send_text(bridge_hello(body["catalog_hash"], 6))
            fresh_token = receive(replacement, "WELCOME")["catalog_upload_token"]
        finally:
            assert harness.client.portal is not None
            harness.client.portal.call(release.set)
        assert future.result(3).status_code == 409
        assert BRIDGE_ID not in harness.runtime.engine.state.catalogs
        assert put_catalog(harness, body, fresh_token).status_code == 204


def test_metadata_partial_import_manual_priority_search_and_export(harness: Harness) -> None:
    _, token, body = private_library(harness)
    headers = {"origin": ORIGIN, **harness.cookie(token)}
    entry = body["entries"][0]
    row = {
        "bridge_id": BRIDGE_ID,
        "relpath": entry["relpath"],
        "title": "Imported",
        "artist": "Original",
        "album": "Album",
        "year": 2026,
    }
    rows = [
        row,
        row,
        {**row, "relpath": "missing.flac"},
        {**row, "year": "bad"},
        {**row, "relpath": "../escape.flac"},
    ]
    result = harness.client.post(
        "/api/host/metadata/import", json={"version": 1, "rows": rows}, headers=headers
    )
    assert result.status_code == 200
    assert result.json() == {
        "accepted": 1,
        "issues": [
            {"row": 2, "code": "duplicate"},
            {"row": 3, "code": "unknown"},
            {"row": 4, "code": "invalid"},
            {"row": 5, "code": "invalid"},
        ],
    }
    edited = harness.client.put(
        "/api/host/metadata",
        json={
            "bridge_id": BRIDGE_ID,
            "track_id": entry["track_id"],
            "metadata": {"artist": "Manual", "featuring": "Guest"},
        },
        headers=headers,
    )
    assert edited.status_code == 200
    found = harness.client.get(
        "/api/host/library/search?q=manual&ext=.flac", headers=headers
    ).json()
    assert found["total"] == 1
    assert (
        found["tracks"][0]["title"],
        found["tracks"][0]["album"],
        found["tracks"][0]["artist"],
    ) == ("Imported", "Album", "Manual")
    exported = harness.client.get("/api/host/metadata", headers=headers).json()
    assert exported["version"] == 2
    assert exported["rows"][0]["featuring"] == "Guest"
    assert (
        harness.client.get("/api/host/library/search?folder=Animes", headers=headers).json()[
            "total"
        ]
        == 0
    )


@pytest.mark.parametrize("route", ["/api/host/library/search", "/api/host/metadata"])
def test_library_data_is_host_only(harness: Harness, route: str) -> None:
    private_library(harness)
    assert harness.client.get(route).status_code == 401
    _, token = harness.join("Player")
    assert harness.client.get(route, headers=harness.cookie(token)).status_code == 403


@pytest.mark.parametrize(("host_mode", "expected"), [("player", 409), ("mc", 200)])
@pytest.mark.parametrize("route", ["/api/host/library", "/api/host/library/search"])
def test_library_during_play_respects_host_mode(
    harness: Harness, host_mode: str, expected: int, route: str
) -> None:
    pid, token, _ = private_library(harness)
    harness.join("Player")
    host_command(harness, pid, "set_mode", {"mode": host_mode})
    host_command(
        harness, pid, "configure", {"sources": [{"bridge_id": BRIDGE_ID, "folder_prefix": ""}]}
    )
    host_command(harness, pid, "start_game")
    assert harness.client.get(route, headers=harness.cookie(token)).status_code == expected


def test_metadata_ambiguous_path_and_whole_document_validation(harness: Harness) -> None:
    _, token, _ = private_library(harness)
    state = harness.runtime.engine.state
    state.catalogs[BRIDGE_ID].ambiguous_paths = ("ambiguous.flac",)
    headers = {"origin": ORIGIN, **harness.cookie(token)}
    row = {"bridge_id": BRIDGE_ID, "relpath": "ambiguous.flac", "title": "Unknown"}
    result = harness.client.post(
        "/api/host/metadata/import", json={"version": 1, "rows": [row]}, headers=headers
    )
    assert result.json()["issues"] == [{"row": 1, "code": "ambiguous"}]
    for payload in (
        {"version": 99, "rows": []},
        {"version": True, "rows": []},
        {"version": 1, "rows": [], "extra": True},
    ):
        assert (
            harness.client.post(
                "/api/host/metadata/import", json=payload, headers=headers
            ).status_code
            == 400
        )


def test_two_bridges_coexist_catalog_tokens_are_bound_and_sources_route_to_owner(
    harness: Harness,
) -> None:
    _, token = harness.join("Host")
    harness.elevate(token)
    first, second = catalog(), {**catalog(), "bridge_id": SECOND}
    second_secret = "synthetic-second-distinct-credential-0123456789"
    harness.runtime.credentials.replace(SECOND, "Second", second_secret)
    with harness.bridge_ws() as a, harness.bridge_ws(second_secret) as b:
        a.send_text(bridge_hello(first["catalog_hash"], 6))
        hello = json.loads(bridge_hello(second["catalog_hash"], 6))
        hello["bridge_id"] = SECOND
        b.send_json(hello)
        wa, wb = receive(a, "WELCOME"), receive(b, "WELCOME")
        assert len(harness.runtime.bridge.connections) == 2
        # Without identity selection, an upload with multiple active Bridges is rejected.
        assert put_catalog(harness, first, wa["catalog_upload_token"]).status_code == 403

        def upload(body: dict, grant: str) -> int:
            credential = second_secret if body["bridge_id"] == SECOND else SECRET
            return harness.client.put(
                "/api/bridge/catalog",
                content=gzip.compress(json.dumps(body).encode()),
                headers={
                    "authorization": f"Bearer {credential}",
                    "x-catalog-token": grant,
                    "x-bridge-id": body["bridge_id"],
                    "content-encoding": "gzip",
                    "content-type": "application/json",
                },
            ).status_code

        assert upload(second, wa["catalog_upload_token"]) == 403
        assert upload(first, wa["catalog_upload_token"]) == 204
        assert upload(second, wb["catalog_upload_token"]) == 204
        assert len(harness.runtime.engine.library().bridges) == 2
        headers = {"origin": ORIGIN, **harness.cookie(token)}
        for folder in ("../outside", "C:/music", "/music", "a\\b"):
            assert (
                harness.client.post(
                    "/api/host/library/sources",
                    json={"bridge_id": SECOND, "folders": [folder]},
                    headers=headers,
                ).status_code
                == 400
            )
        result = harness.client.post(
            "/api/host/library/sources",
            json={"bridge_id": SECOND, "folders": ["Anime"]},
            headers=headers,
        )
        assert result.status_code == 202
        assert receive(b, "SCAN_SOURCES")["folders"] == ["Anime"]


def test_recovery_code_requires_password_is_one_use_and_never_grants_host(harness: Harness) -> None:
    pid, token = harness.join("Host")
    harness.elevate(token)
    result = harness.client.post(
        "/api/session/recovery-code", headers={"origin": ORIGIN, **harness.cookie(token)}
    )
    code = result.json()["code"]
    assert code not in repr(harness.runtime.sessions.recovery_snapshot())
    bad = harness.client.post(
        "/api/session/recover", json={"password": "wrong", "code": code}, headers={"origin": ORIGIN}
    )
    assert bad.status_code == 401
    recovered = harness.client.post(
        "/api/session/recover", json={"password": BLIND, "code": code}, headers={"origin": ORIGIN}
    )
    assert recovered.status_code == 200
    assert recovered.json()["player_id"] == pid
    assert recovered.json()["role"] == "player"
    harness.client.cookies.clear()
    assert harness.client.get("/api/session", headers=harness.cookie(token)).status_code == 401
    replay = harness.client.post(
        "/api/session/recover", json={"password": BLIND, "code": code}, headers={"origin": ORIGIN}
    )
    assert replay.status_code == 401


def test_mutations_require_origin_and_import_has_a_memory_limit(harness: Harness) -> None:
    _, token, _ = private_library(harness)
    assert (
        harness.client.post(
            "/api/host/metadata/import",
            json={"version": 1, "rows": []},
            headers=harness.cookie(token),
        ).status_code
        == 403
    )
    response = harness.client.post(
        "/api/host/metadata/import",
        content=b" " * (1024 * 1024 + 1),
        headers={"origin": ORIGIN, "content-type": "application/json", **harness.cookie(token)},
    )
    assert response.status_code == 413


def test_labels_activation_and_partial_edits_preserve_library_and_history(harness: Harness):
    pid, token, body = private_library(harness)
    headers = {"origin": ORIGIN, **harness.cookie(token)}
    entry = body["entries"][0]
    key = {"bridge_id": BRIDGE_ID, "track_id": entry["track_id"]}
    assert (
        harness.client.put(
            "/api/host/metadata",
            json={
                **key,
                "metadata": {
                    "tags": [" Rock ", "rock", "2000s"],
                    "linked_to": ["video game - Example"],
                    "enabled": False,
                },
            },
            headers=headers,
        ).status_code
        == 200
    )
    # The older round editor sends only title/artist; it must retain newer classification fields.
    assert (
        harness.client.put(
            "/api/host/metadata", json={**key, "metadata": {"title": "Corrected"}}, headers=headers
        ).status_code
        == 200
    )
    root = "/api/host/library/search"
    disabled = harness.client.get(
        root + "?activation=disabled&tag=rock&linked_to=video%20game%20-%20Example", headers=headers
    ).json()
    assert disabled["total"] == 1
    track = disabled["tracks"][0]
    assert track["tags"] == ["Rock", "2000s"]
    assert track["linked_to"] == ["video game - Example"]
    assert track["title"] == "Corrected"
    assert not track["available"]
    assert harness.client.get(root + "?activation=active", headers=headers).json()["total"] == 5
    assert harness.client.get(root + "?q=2000s", headers=headers).json()["total"] == 1
    host_command(
        harness, pid, "configure", {"sources": [{"bridge_id": BRIDGE_ID, "folder_prefix": ""}]}
    )
    state = harness.runtime.engine.state
    ref = TrackRef(BRIDGE_ID, entry["track_id"])
    assert ref not in selection.pool(state)
    assert (
        harness.client.put(
            "/api/host/metadata",
            json={**key, "metadata": {"enabled": True, "tags": [], "linked_to": []}},
            headers=headers,
        ).status_code
        == 200
    )
    assert ref in selection.pool(state)
    exported = harness.client.get("/api/host/metadata", headers=headers).json()
    assert exported["version"] == 2
    assert exported["rows"][0]["enabled"] is True
    assert exported["rows"][0]["tags"] == []
    assert state.journal.events() == ()
    assert len(state.catalogs[BRIDGE_ID].entries) == 6


def test_import_v2_labels_can_be_cleared_without_breaking_v1(harness: Harness):
    _, token, body = private_library(harness)
    headers = {"origin": ORIGIN, **harness.cookie(token)}
    base = {"bridge_id": BRIDGE_ID, "relpath": body["entries"][0]["relpath"]}
    for version, data in [
        (2, {"tags": ["anime"], "linked_to": ["Naruto"], "enabled": False}),
        (1, {"title": "Legacy title"}),
        (2, {"tags": [], "linked_to": [], "enabled": True}),
    ]:
        response = harness.client.post(
            "/api/host/metadata/import",
            json={"version": version, "rows": [{**base, **data}]},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["accepted"] == 1
    track = harness.client.get("/api/host/library/search?q=Legacy", headers=headers).json()[
        "tracks"
    ][0]
    assert track["enabled"] is True
    assert track["tags"] == track["linked_to"] == []


def test_alias_export_import_roundtrip_preserves_scoring_variants(harness: Harness):
    _, token, body = private_library(harness)
    headers = {"origin": ORIGIN, **harness.cookie(token)}
    entry = body["entries"][0]
    ref = TrackRef(BRIDGE_ID, entry["track_id"])
    aliases = {"artist": ["Stage Name"], "title": ["Alternate Title"]}
    assert (
        harness.client.put(
            "/api/host/metadata",
            headers=headers,
            json={
                "bridge_id": BRIDGE_ID,
                "track_id": entry["track_id"],
                "metadata": {"aliases": aliases},
            },
        ).status_code
        == 200
    )
    exported = harness.client.get("/api/host/metadata", headers=headers).json()
    assert exported["rows"][0]["aliases"] == aliases
    harness.runtime.engine.state.metadata.pop(ref)
    assert (
        harness.client.post("/api/host/metadata/import", headers=headers, json=exported).json()[
            "accepted"
        ]
        == 1
    )
    assert harness.runtime.engine.state.imported_metadata[ref].aliases == aliases
