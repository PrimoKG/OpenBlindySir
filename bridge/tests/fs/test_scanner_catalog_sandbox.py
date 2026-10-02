"""Scanner, catalogue and sandbox (spec §11, §12, §20.1 item 9)."""

import gzip
import os
import sys
import unicodedata
from pathlib import Path

import pytest

from openblindysir_bridge.catalog import LocalCatalog
from openblindysir_bridge.sandbox import Sandbox, SandboxError
from openblindysir_bridge.scanner import scan
from openblindysir_protocol.bridge import CatalogUpload
from openblindysir_protocol.catalog_rules import compute_track_id

BRIDGE_ID = "12345678-1234-1234-1234-123456789abc"


def make(path: Path, data: bytes = b"audio") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def junction(link: Path, target: Path) -> bool:
    if sys.platform != "win32":
        return False
    import _winapi  # noqa: PLC0415

    _winapi.CreateJunction(str(target), str(link))
    return True


def try_symlink(link: Path, target: Path) -> bool:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        return False
    return True


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "music"
    make(root / "Anime" / "OST" / "a.flac")
    make(root / "Anime" / "b.MP3")
    make(root / "notes.txt")
    make(root / ".hidden.mp3")
    make(root / "-dash.mp3")
    make(root / unicodedata.normalize("NFD", "Amélie.mp3"))
    return root


def test_scan_keeps_whitelisted_audio_only(library: Path) -> None:
    result = scan(library)
    relpaths = [e.relpath for e in result.entries]
    assert "Anime/OST/a.flac" in relpaths
    assert "Anime/b.MP3" in relpaths
    assert "notes.txt" not in relpaths
    assert ".hidden.mp3" not in relpaths
    assert result.skipped_hidden >= 1


def test_relpaths_are_nfc_but_reopen_with_real_names(library: Path) -> None:
    result = scan(library)
    entry = next(e for e in result.entries if e.relpath.startswith("Am"))
    assert entry.relpath == unicodedata.normalize("NFC", "Amélie.mp3")
    assert Sandbox(result.root_real).resolve_for_open(entry)


def test_symlinks_are_not_followed(library: Path, tmp_path: Path) -> None:
    outside = make(tmp_path / "secret" / "private.mp3")
    if not try_symlink(library / "link.mp3", outside):
        pytest.skip("symlink creation not permitted here")
    result = scan(library)
    assert all(e.relpath != "link.mp3" for e in result.entries)
    assert result.skipped_links >= 1


@pytest.mark.windows
def test_junctions_are_not_followed(library: Path, tmp_path: Path) -> None:
    outside = tmp_path / "secret"
    make(outside / "private.mp3")
    assert junction(library / "Junction", outside)
    result = scan(library)
    assert all("private" not in e.relpath for e in result.entries)
    assert result.skipped_links >= 1


@pytest.mark.windows
def test_sandbox_refuses_a_file_reached_through_a_junction(library: Path, tmp_path: Path) -> None:
    result = scan(library)
    entry = next(e for e in result.entries if e.relpath == "Anime/OST/a.flac")
    outside = tmp_path / "elsewhere"
    make(outside / "a.flac", b"audio")
    os.remove(library / "Anime" / "OST" / "a.flac")
    (library / "Anime" / "OST").rmdir()
    assert junction(library / "Anime" / "OST", outside)
    with pytest.raises(SandboxError):
        Sandbox(result.root_real).resolve_for_open(entry)


def test_sandbox_refuses_file_replaced_after_scan(library: Path, tmp_path: Path) -> None:
    result = scan(library)
    entry = next(e for e in result.entries if e.relpath == "Anime/b.MP3")
    target = library / "Anime" / "b.MP3"
    target.unlink()
    outside = make(tmp_path / "secret.mp3", b"audio")
    if not try_symlink(target, outside):
        make(target, b"changed content")  # still detected: size/mtime differ
    with pytest.raises(SandboxError):
        Sandbox(result.root_real).resolve_for_open(entry)


def test_sandbox_refuses_missing_file(library: Path) -> None:
    result = scan(library)
    entry = result.entries[0]
    os.remove(os.path.join(result.root_real, *entry.fs_parts))
    with pytest.raises(SandboxError):
        Sandbox(result.root_real).resolve_for_open(entry)


def test_catalog_ids_and_upload_match_protocol(library: Path) -> None:
    catalog = LocalCatalog.from_scan(scan(library))
    for track_id, entry in catalog.entries.items():
        assert track_id == compute_track_id(entry.relpath)
    upload = CatalogUpload.model_validate_json(gzip.decompress(catalog.to_upload(BRIDGE_ID)))
    assert upload.catalog_hash == catalog.catalog_hash
    assert {e.relpath for e in upload.entries} == {e.relpath for e in catalog.entries.values()}
    assert catalog.to_upload(BRIDGE_ID) == catalog.to_upload(BRIDGE_ID)  # deterministic
    assert catalog.lookup("t_0000000000000000") is None


def test_catalog_hash_changes_with_content(library: Path) -> None:
    before = LocalCatalog.from_scan(scan(library)).catalog_hash
    make(library / "new.flac")
    assert LocalCatalog.from_scan(scan(library)).catalog_hash != before
