"""Release gates reject altered provenance/content instead of publishing it."""

import hashlib
import io
import json
import tarfile
import zipfile

import pytest

import release

DATA = {"version": "0.3.0", "protocol": 5, "commit": "a" * 40, "dirty": False}
PREFIX = "OpenBlindySir-Bridge-0.3.0-windows-x86_64/"


def archive(*, patch=None, content=b"synthetic", extra=None):
    manifest = (
        DATA
        | {
            "os": "windows",
            "arch": "x86_64",
            "ffmpeg_included": False,
            "files": {"README.txt": hashlib.sha256(b"synthetic").hexdigest()},
        }
        | (patch or {})
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr(PREFIX + "README.txt", content)
        z.writestr(PREFIX + "release.json", json.dumps(manifest))
        if extra:
            z.writestr(extra, b"unexpected")
    return zipfile.ZipFile(stream)


@pytest.mark.parametrize(
    "patch",
    [{"commit": "b" * 40}, {"version": "0.2.0"}, {"dirty": True}, {"ffmpeg_included": True}],
)
def test_release_rejects_wrong_or_dirty_provenance(patch):
    with archive(patch=patch) as z, pytest.raises(ValueError, match="provenance"):
        release.check_binary(z, DATA, clean=True)


@pytest.mark.parametrize(
    "extra",
    [
        "bundle/config.toml",
        "bundle/ffmpeg.exe",
        "../private",
        "bundle/unknown.txt",
        "C:/secret",
        "bundle/bridge-credentials.json",
        "bundle/credentials.toml",
    ],
)
def test_release_rejects_unlisted_or_private_content(extra):
    with archive(extra=extra) as z, pytest.raises(ValueError, match=r"content|path"):
        release.check_binary(z, DATA, clean=True)


def test_release_rejects_altered_bytes():
    with archive(content=b"altered") as z, pytest.raises(ValueError, match="checksum"):
        release.check_binary(z, DATA, clean=True)


def test_clean_binary_and_exact_python_set_accepted():
    with archive() as z:
        assert release.check_binary(z, DATA, clean=True) == ("windows", "x86_64")
    assert len(release.python_filenames("0.3.0")) == 4


def test_release_refuses_dirty_checkout_before_tag_or_publish(monkeypatch):
    actual = DATA | {"version": release.ROOT.joinpath("VERSION").read_text().strip(), "dirty": True}
    monkeypatch.setattr(release, "metadata", lambda: actual)
    with pytest.raises(ValueError, match="clean checkout"):
        release.verify_version(clean=True)


@pytest.mark.parametrize(
    "name",
    [
        "./file",
        "folder//file",
        "CON.txt",
        "aux",
        "a/file.",
        "a/file ",
        "a/\x00file",
        "a/\x01file",
        "LPT1.txt",
        "folder/../file",
    ],
)
def test_archive_paths_have_one_portable_meaning(name):
    assert not release.safe_archive_name(name)


@pytest.mark.parametrize("name", [".env.backup", "config.toml.bak-synthetic"])
def test_manifest_cannot_allow_private_backups(name):
    content = b"synthetic-private"
    stream = io.BytesIO()
    manifest = DATA | {
        "os": "windows",
        "arch": "x86_64",
        "ffmpeg_included": False,
        "files": {name: hashlib.sha256(content).hexdigest()},
    }
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr(PREFIX + name, content)
        z.writestr(PREFIX + "release.json", json.dumps(manifest))
    with zipfile.ZipFile(stream) as z, pytest.raises(ValueError, match="private"):
        release.check_binary(z, DATA, clean=True)


def test_python_filename_must_match_package_metadata(tmp_path):
    path = tmp_path / "openblindysir_protocol-0.3.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "openblindysir_bridge-0.3.0.dist-info/METADATA",
            "Name: openblindysir-bridge\nVersion: 0.3.0\n"
            "Requires-Dist: openblindysir-protocol==0.3.0\n",
        )
    with pytest.raises(ValueError, match="name"):
        release.check_python(path, "0.3.0")


def test_binary_target_must_match_archive_root():
    with archive(patch={"os": "linux"}) as z, pytest.raises(ValueError, match="target"):
        release.check_binary(z, DATA, clean=True)


@pytest.mark.parametrize("variant", ["case", "unicode", "symlink"])
def test_extraction_refuses_ambiguous_paths_or_links_before_writing(tmp_path, variant):
    from smoke_bridge_distribution import extract  # noqa: PLC0415

    stream = tmp_path / "invalid.zip"
    with zipfile.ZipFile(stream, "w") as z:
        if variant == "symlink":
            item = zipfile.ZipInfo("folder/link")
            item.create_system = 3
            item.external_attr = 0o120777 << 16
            z.writestr(item, "../synthetic")
        else:
            names = (
                ("folder/A.txt", "folder/a.txt")
                if variant == "case"
                else ("folder/é.txt", "folder/e\u0301.txt")
            )
            for name in names:
                z.writestr(name, "synthetic")
    destination = tmp_path / "extracted"
    destination.mkdir()
    with pytest.raises(ValueError, match="path"):
        extract(stream, destination)
    assert not list(destination.iterdir())


def stage_python(directory):
    for package in ("bridge", "protocol"):
        stem = f"openblindysir_{package}-0.3.0"
        metadata = f"Name: openblindysir-{package}\nVersion: 0.3.0\n"
        if package == "bridge":
            metadata += "Requires-Dist: openblindysir-protocol==0.3.0\n"
        content = metadata.encode()
        with zipfile.ZipFile(directory / f"{stem}-py3-none-any.whl", "w") as z:
            z.writestr(f"{stem}.dist-info/METADATA", content)
        with tarfile.open(directory / f"{stem}.tar.gz", "w:gz") as tar:
            info = tarfile.TarInfo(f"{stem}/PKG-INFO")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    provenance = DATA | {"files": {p.name: release.sha256(p) for p in directory.iterdir()}}
    (directory / "python-provenance.json").write_text(json.dumps(provenance))


def test_collect_rejects_foreign_private_file_instead_of_hashing_it(tmp_path, monkeypatch):
    stage_python(tmp_path)
    (tmp_path / ".env").write_text("SYNTHETIC-PRIVATE")
    monkeypatch.setattr(release, "verify_version", lambda *a, **kw: dict(DATA))
    with pytest.raises(ValueError, match="unexpected"):
        release.collect(tmp_path)
    assert not (tmp_path / "release-manifest.json").exists()
    assert not (tmp_path / "SHA256SUMS").exists()


def test_collect_accepts_valid_artifacts_and_is_repeatable(tmp_path, monkeypatch):
    stage_python(tmp_path)
    monkeypatch.setattr(release, "verify_version", lambda *a, **kw: dict(DATA))
    release.collect(tmp_path)
    expected = (tmp_path / "SHA256SUMS").read_bytes()
    release.collect(tmp_path)
    assert (tmp_path / "SHA256SUMS").read_bytes() == expected


def test_collect_rejects_wrong_binary_sidecar(tmp_path, monkeypatch):
    stage_python(tmp_path)
    path = tmp_path / (PREFIX.rstrip("/") + ".zip")
    with archive() as z:
        path.write_bytes(z.fp.getvalue())
    path.with_name(path.name + ".sha256").write_text("0" * 64 + "  " + path.name)
    monkeypatch.setattr(release, "verify_version", lambda *a, **kw: dict(DATA))
    with pytest.raises(ValueError, match="sidecar"):
        release.collect(tmp_path)
