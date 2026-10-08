"""Export/import budgets, archive traversal and explicit inheritance regressions."""

import io
import zipfile
from types import SimpleNamespace

import pytest

from openblindysir_protocol.metadata import MetadataRow
from openblindysir_server.game.metadata import musical_metadata
from openblindysir_server.game.state import Metadata, TrackRef
from openblindysir_server.library.metadata_archive import (
    JSON_LIMIT,
    PACK_LIMIT,
    document,
    pack,
    unpack,
)


def test_large_collection_exports_as_independently_importable_packs():
    rows = [
        {
            "bridge_id": "12345678-1234-1234-1234-123456789abc",
            "relpath": f"track-{index}.mp3",
            "title": "x" * 256,
            "tags": ["y" * 256 for _ in range(32)],
            "aliases": {"artist": ["z" * 256 for _ in range(8)]},
        }
        for index in range(850)
    ]
    assert len(document(rows)) > PACK_LIMIT
    for row in rows:
        MetadataRow.model_validate(row)
    offset = 0
    restored = []
    sizes = []
    while offset < len(rows):
        raw, end = pack(rows, offset)
        assert offset < end
        assert len(raw) <= PACK_LIMIT
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            assert all(info.file_size <= JSON_LIMIT for info in archive.infolist())
        restored.extend(unpack(raw)["rows"])
        sizes.append(len(raw))
        offset = end
    assert len(sizes) > 1
    assert restored == rows


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("../metadata-000001.json", document([])),
        ("metadata-000001.json", b"x" * (JSON_LIMIT + 1)),
        ("metadata-000001.json", b'{"version":true,"rows":[]}'),
        ("metadata-000001.json", b'{"version":2,"rows":{},"extra":0}'),
    ],
    ids=["traversal", "inflation", "bad-version", "bad-fields"],
)
def test_archive_refuses_traversal_oversized_inflation_and_bad_documents(filename, content):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename, content)
    with pytest.raises(ValueError, match=r"invalid|limit"):
        unpack(raw.getvalue())


def test_empty_export_is_reimportable():
    raw, offset = pack([], 0)
    assert offset == 0
    assert unpack(raw) == {"version": 3, "rows": []}


@pytest.mark.parametrize("compression", [zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA])
def test_complex_compression_is_rejected_before_reading(compression):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", compression=compression) as archive:
        archive.writestr("metadata-000001.json", document([]))
    with pytest.raises(ValueError, match="invalid member"):
        unpack(raw.getvalue())


def test_clear_blocks_import_and_alias_then_inherit_restores_it():
    ref = TrackRef("bridge", "track")
    state = SimpleNamespace(
        metadata={},
        imported_metadata={ref: Metadata(title="Imported", aliases={"title": ["Alias"]})},
    )
    state.metadata[ref] = Metadata(title=None, cleared_fields=["title"])
    result = musical_metadata(state, ref)
    assert result.title is None
    assert not result.aliases
    state.metadata[ref] = Metadata(title=None, cleared_fields=[])
    assert musical_metadata(state, ref).title == "Imported"
    assert musical_metadata(state, ref).aliases == {"title": ["Alias"]}


def test_manual_replacement_can_override_imported_clear():
    ref = TrackRef("bridge", "track")
    state = SimpleNamespace(
        metadata={ref: Metadata(title="Confirmed")},
        imported_metadata={ref: Metadata(cleared_fields=["title"])},
    )
    assert musical_metadata(state, ref).title == "Confirmed"
