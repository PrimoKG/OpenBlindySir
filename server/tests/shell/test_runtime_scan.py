"""Reject scan evidence detached from the immutable image or corresponding source."""

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from scan_runtime_images import archive_config_id, validate_ffmpeg_component


def image_archive(path: Path, count: int) -> bytes:
    config = b'{"architecture":"amd64","os":"linux"}'
    with tarfile.open(path, "w") as archive:
        for name, data in (
            ("manifest.json", json.dumps([{"Config": "config.json"}] * count).encode()),
            ("config.json", config),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return config


def test_scan_identity_is_the_actual_config_bytes(tmp_path: Path) -> None:
    path = tmp_path / "image.tar"
    config = image_archive(path, 1)
    assert archive_config_id(path) == "sha256:" + hashlib.sha256(config).hexdigest()


@pytest.mark.parametrize("count", [0, 2])
def test_ambiguous_image_archive_is_refused(tmp_path: Path, count: int) -> None:
    path = tmp_path / "image.tar"
    image_archive(path, count)
    with pytest.raises(ValueError, match="exactly one image"):
        archive_config_id(path)


@pytest.mark.parametrize("change", ["version", "hash", "duplicate"])
def test_ffmpeg_declaration_cannot_hide_another_binary_or_source(change: str) -> None:
    component = {
        "name": "ffmpeg",
        "version": "9.0.2",
        "hashes": [{"alg": "SHA-256", "content": "a" * 64}],
    }
    sbom = {"components": [component]}
    facts = {"version": "9.0.2", "sha256": "a" * 64}
    validate_ffmpeg_component(sbom, facts)
    if change == "version":
        facts["version"] = "7.1.5"
    elif change == "hash":
        facts["sha256"] = "b" * 64
    else:
        sbom["components"].append(component.copy())
    with pytest.raises(ValueError, match="does not match"):
        validate_ffmpeg_component(sbom, facts)
