"""Real FFmpeg jobs on synthetic fixtures generated at run time (never committed audio)."""

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from openblindysir_bridge import ffmpeg
from openblindysir_bridge.catalog import LocalCatalog
from openblindysir_bridge.clip import ClipRequest
from openblindysir_bridge.jobs import JobRunner
from openblindysir_bridge.sandbox import Sandbox
from openblindysir_bridge.scanner import scan
from openblindysir_protocol.bridge import JobDone, JobFailed, Prepare
from openblindysir_protocol.enums import ClipFormat, JobFailureCode

pytestmark = pytest.mark.ffmpeg


def lavfi(out: Path, expr: str, *extra: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [shutil.which("ffmpeg") or "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", expr, "-ac", "2", *extra, "-y", str(out)],
        check=True,
    )  # fmt: skip


@pytest.fixture(scope="module")
def library(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("lib") / "music"
    lavfi(
        root / "Tagged" / "song.mp3", "sine=frequency=440:duration=90",
        "-metadata", "title=Synthetic Title", "-metadata", "artist=Synthetic Artist",
    )  # fmt: skip
    lavfi(root / "short.flac", "sine=frequency=300:duration=6")
    return root


def prepare(track_id: str, duration: float = 12.0) -> Prepare:
    return Prepare.model_validate_json(
        json.dumps(
            {
                "t": "PREPARE",
                "job_id": "j_000001",
                "track_id": track_id,
                "start_fraction": 0.3,
                "duration": duration,
                "upload_url": "/api/bridge/assets/a_" + "A" * 22,
                "upload_token": "T" * 43,
            }
        )
    )


def run_job(root: Path, track_id: str, tmp_path: Path) -> tuple[list[Any], dict[str, bytes]]:
    tools = ffmpeg.discover()
    catalog = LocalCatalog.from_scan(scan(root))
    sent: list[Any] = []
    uploads: dict[str, bytes] = {}

    async def uploader(url: str, token: str, file: Path, sha: str, mime: str) -> int:
        uploads[url] = await asyncio.to_thread(file.read_bytes)
        return 204

    async def main() -> None:
        runner = JobRunner(
            tools=tools,
            sandbox=Sandbox(str(root)),
            catalog=lambda: catalog,
            uploader=uploader,
            send=sent.append,
            tmpdir=tmp_path,
        )
        task = asyncio.create_task(runner.run())
        runner.submit(
            prepare(track_id), ClipRequest(12.0, 0.3, 128, 4 * 1024 * 1024, ClipFormat.AAC)
        )
        for _ in range(400):
            if any(isinstance(m, JobDone | JobFailed) for m in sent):
                break
            await asyncio.sleep(0.05)
        task.cancel()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
    return sent, uploads


def ffprobe_json(path: Path) -> dict[str, Any]:
    out = subprocess.run(
        [shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_format", "-show_streams",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout  # fmt: skip
    return json.loads(out)


def track_id_of(root: Path, relpath: str) -> str:
    catalog = LocalCatalog.from_scan(scan(root))
    return next(tid for tid, e in catalog.entries.items() if e.relpath == relpath)


def test_clip_is_tagless_aac_48k_stereo(library: Path, tmp_path: Path) -> None:
    sent, uploads = run_job(library, track_id_of(library, "Tagged/song.mp3"), tmp_path)
    done = next(m for m in sent if isinstance(m, JobDone))
    assert done.tags is not None
    assert done.tags.title == "Synthetic Title"
    assert 11.0 < done.clip_duration < 13.0
    clip = tmp_path / "check.m4a"
    clip.write_bytes(next(iter(uploads.values())))
    info = ffprobe_json(clip)
    streams = info["streams"]
    assert len(streams) == 1
    assert streams[0]["codec_name"] == "aac"
    assert streams[0]["sample_rate"] == "48000"
    assert streams[0]["channels"] == 2
    tags = {k.lower() for k in info["format"].get("tags", {})}
    assert not tags & {"title", "artist", "album"}
    assert not list(tmp_path.glob("j_*"))  # temporary clip deleted


def test_too_short_track(library: Path, tmp_path: Path) -> None:
    sent, _ = run_job(library, track_id_of(library, "short.flac"), tmp_path)
    failed = next(m for m in sent if isinstance(m, JobFailed))
    assert failed.code is JobFailureCode.TOO_SHORT


def test_unknown_track_is_not_found(library: Path, tmp_path: Path) -> None:
    sent, _ = run_job(library, "t_0000000000000000", tmp_path)
    assert next(m for m in sent if isinstance(m, JobFailed)).code is JobFailureCode.NOT_FOUND


@pytest.mark.windows
def test_ffconcat_playlist_cannot_read_outside_root(tmp_path: Path) -> None:
    """Spike S1 finding: a playlist disguised as audio, through a junction in the library."""
    import _winapi  # noqa: PLC0415

    root = tmp_path / "music"
    outside = tmp_path / "private"
    lavfi(outside / "secret.wav", "sine=frequency=1000:duration=60")
    root.mkdir()
    _winapi.CreateJunction(str(outside), str(root / "j"))
    (root / "trap.mp3").write_text(
        "ffconcat version 1.0\nfile 'j/secret.wav'\nduration 60\n", encoding="utf-8"
    )
    sent, uploads = run_job(root, track_id_of(root, "trap.mp3"), tmp_path / "work")
    assert not uploads
    failed = next(m for m in sent if isinstance(m, JobFailed))
    assert failed.code in (JobFailureCode.DECODE_ERROR, JobFailureCode.NOT_FOUND)
