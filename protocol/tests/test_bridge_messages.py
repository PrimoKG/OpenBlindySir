"""Bridge protocol: closed command set and safe catalogue entries (spec §8.3, §11)."""

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from openblindysir_protocol.bridge import CatalogEntry, Prepare, ServerToBridge
from openblindysir_protocol.catalog_rules import compute_catalog_hash, compute_track_id

SERVER_TO_BRIDGE = TypeAdapter(ServerToBridge)
ASSET = "a_" + "A" * 22
TOKEN = "T" * 43


def prepare(**overrides: object) -> dict[str, object]:
    return {
        "t": "PREPARE",
        "job_id": "j_job001",
        "track_id": "t_0123456789abcdef",
        "start_fraction": 0.4,
        "duration": 25,
        "upload_url": f"/api/bridge/assets/{ASSET}",
        "upload_token": TOKEN,
        **overrides,
    }


def test_prepare_parses() -> None:
    assert isinstance(SERVER_TO_BRIDGE.validate_json(json.dumps(prepare())), Prepare)


@pytest.mark.parametrize("t", ["LIST", "READ_FILE", "RESCAN", "PONG", "JOB_DONE"])
def test_bridge_accepts_only_the_five_server_commands(t: str) -> None:
    with pytest.raises(ValidationError):
        SERVER_TO_BRIDGE.validate_json(json.dumps({"t": t}))


@pytest.mark.parametrize(
    "overrides",
    [
        {"path": "C:/Windows/win.ini"},
        {"ffmpeg_args": ["-i", "x"]},
        {"upload_url": "https://evil.example/upload"},
        {"upload_url": "/api/bridge/assets/../../etc"},
        {"track_id": "../secret"},
        {"start_fraction": 1.0},
        {"duration": 3601},
    ],
)
def test_prepare_rejects_paths_args_and_foreign_urls(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SERVER_TO_BRIDGE.validate_json(json.dumps(prepare(**overrides)))


def test_welcome_token_present_iff_catalog_needed() -> None:
    base = {
        "t": "WELCOME",
        "clip_format": "aac",
        "bitrate": 128,
        "limits": {"clip_min_s": 5, "clip_max_s": 60, "max_clip_bytes": 2_000_000},
    }
    SERVER_TO_BRIDGE.validate_json(json.dumps({**base, "catalog_needed": False}))
    with pytest.raises(ValidationError):
        SERVER_TO_BRIDGE.validate_json(json.dumps({**base, "catalog_needed": True}))


@pytest.mark.parametrize(
    "relpath", ["../x.mp3", "/abs.mp3", "a\\b.mp3", "a/./b.mp3", "a//b.mp3", "Ame\u0301lie.mp3"]
)
def test_catalog_entry_rejects_unsafe_relpath(relpath: str) -> None:
    with pytest.raises(ValidationError):
        CatalogEntry(
            track_id=compute_track_id(relpath), relpath=relpath, folder="", ext=".mp3", size=1
        )


def test_catalog_entry_folder_must_be_parent() -> None:
    relpath = "Anime/OST/a.flac"
    CatalogEntry(
        track_id=compute_track_id(relpath), relpath=relpath, folder="Anime/OST", ext=".flac", size=3
    )
    with pytest.raises(ValidationError):
        CatalogEntry(
            track_id=compute_track_id(relpath), relpath=relpath, folder="Anime", ext=".flac", size=3
        )


def test_track_id_is_stable_and_opaque() -> None:
    track_id = compute_track_id("Anime/OST/a.flac")
    assert track_id == compute_track_id("Anime/OST/a.flac")
    assert track_id.startswith("t_")
    assert len(track_id) == 18
    assert "Anime" not in track_id


def test_catalog_hash_is_order_independent() -> None:
    rows = [(compute_track_id(p), p, i) for i, p in enumerate(["a.mp3", "b/c.flac", "d.wav"])]
    assert compute_catalog_hash(rows) == compute_catalog_hash(list(reversed(rows)))
    changed = [*rows[:2], (rows[2][0], rows[2][1], 99)]
    assert compute_catalog_hash(changed) != compute_catalog_hash(rows)
