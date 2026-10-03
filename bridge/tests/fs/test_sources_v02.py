"""Authorization, overlapping folders, stable IDs and normalized-path ambiguity."""

import os
import subprocess
from pathlib import Path

import pytest

from openblindysir_bridge.catalog import LocalCatalog
from openblindysir_bridge.scanner import scan
from openblindysir_bridge.sources import scan_sources


def music(root: Path) -> None:
    for path in ("A/a.mp4", "A/Sub/b.mkv", "B/c.mp3", "A/ignored.m3u8"):
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"synthetic")


def test_dynamic_folder_selection_preserves_ids_and_counts_overlaps_once(tmp_path: Path) -> None:
    music(tmp_path)
    all_files = scan_sources(tmp_path, ("",))
    a = scan_sources(tmp_path, ("A", "A/Sub"))
    assert len(a.entries) == 2
    assert set(a.entries) <= set(all_files.entries)
    assert len(scan_sources(tmp_path, ("A/Sub", "B")).entries) == 2
    assert scan_sources(tmp_path, ()).entries == {}
    assert all(not e.relpath.endswith("m3u8") for e in all_files.entries.values())


@pytest.mark.parametrize(
    "prefix", ["../outside", "C:/music", "/music", "A/../B", "A\\Sub", "file:secret"]
)
def test_no_arbitrary_path_can_be_scanned(tmp_path: Path, prefix: str) -> None:
    music(tmp_path)
    with pytest.raises(ValueError, match="path"):
        scan_sources(tmp_path, (prefix,))


def test_inaccessible_folder_preserves_the_callers_previous_catalog(tmp_path: Path) -> None:
    music(tmp_path)
    previous = scan_sources(tmp_path, ("A",))
    with pytest.raises(OSError, match="inaccessible folder"):
        scan_sources(tmp_path, ("not-mounted",))
    assert len(previous.entries) == 2


def test_nfc_collisions_are_both_excluded_instead_of_selecting_an_arbitrary_file(
    tmp_path: Path,
) -> None:
    (tmp_path / "é.mp3").write_bytes(b"one")
    (tmp_path / "e\u0301.mp3").write_bytes(b"two")
    catalog = LocalCatalog.from_scan(scan(tmp_path))
    assert catalog.entries == {}
    assert catalog.ambiguous_paths == ("é.mp3",)
    assert catalog.dropped == 2


@pytest.mark.windows
def test_source_junction_and_root_parent_junction_are_refused(tmp_path: Path) -> None:
    root, outside = tmp_path / "music", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.mp3").write_bytes(b"private")
    junction = root / "link"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)], check=True, capture_output=True
    )
    try:
        with pytest.raises(ValueError, match="invalid folder"):
            scan_sources(root, ("link",))
        with pytest.raises(ValueError, match="root must not be a link or junction"):
            scan(junction)
    finally:
        os.rmdir(junction)
