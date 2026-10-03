"""V0.2 closes source paths and metadata values while admitting audio-bearing containers."""

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from openblindysir_protocol.bridge import CatalogEntry, ScanSources, ServerToBridge
from openblindysir_protocol.catalog_rules import compute_track_id
from openblindysir_protocol.metadata import MetadataDocument


@pytest.mark.parametrize(
    "extension", [".mp4", ".mov", ".m4v", ".3gp", ".mkv", ".avi", ".webm", ".wmv"]
)
def test_audio_bearing_video_containers_are_valid_catalog_entries(extension: str) -> None:
    path = "music/source" + extension
    assert (
        CatalogEntry(
            track_id=compute_track_id(path), relpath=path, folder="music", ext=extension, size=100
        ).ext
        == extension
    )


@pytest.mark.parametrize("extension", [".m3u", ".m3u8", ".pls", ".ffconcat", ".srt", ".txt"])
def test_playlists_and_sidecars_are_not_catalog_sources(extension: str) -> None:
    path = "music/source" + extension
    with pytest.raises(ValidationError):
        CatalogEntry(
            track_id=compute_track_id(path), relpath=path, folder="music", ext=extension, size=100
        )


@pytest.mark.parametrize(
    "path",
    [
        "../secret",
        "C:/Music",
        "file:secret",
        "/Music",
        "a\\b",
        "a/./b",
        "a//b",
        "a\u0301",
        "a\x01b",
    ],
)
def test_source_scan_rejects_arbitrary_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        ScanSources(t="SCAN_SOURCES", folders=[path])


def test_source_scan_accepts_refresh_empty_selection_and_overlapping_subfolders() -> None:
    parser = TypeAdapter(ServerToBridge)
    for folders in (None, [], ["", "Anime", "Anime/OST"]):
        message = parser.validate_json(json.dumps({"t": "SCAN_SOURCES", "folders": folders}))
        assert isinstance(message, ScanSources)
        assert message.folders == folders
    with pytest.raises(ValidationError):
        parser.validate_json(json.dumps({"t": "SCAN_SOURCES", "folders": ["safe"], "root": "C:/"}))


def test_metadata_optional_fields_are_strict_and_versioned() -> None:
    row = {"bridge_id": "12345678-1234-1234-1234-123456789abc", "relpath": "Music/song.mp4"}
    assert MetadataDocument.model_validate({"version": 1, "rows": [row]}).rows[0].year is None
    for changes in ({"year": True}, {"year": 999}, {"title": "line\nbreak"}, {"extra": "unknown"}):
        with pytest.raises(ValidationError):
            MetadataDocument.model_validate({"version": 1, "rows": [{**row, **changes}]})
