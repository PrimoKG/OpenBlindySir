"""Real safe-container extraction, no video/tags, deterministic first audio and bounded IO."""

import array
import asyncio
import contextlib
import hashlib
import itertools
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_jobs_ffmpeg import ffprobe_json, prepare, run_job, track_id_of

from openblindysir_bridge import ffmpeg
from openblindysir_bridge.catalog import LocalCatalog
from openblindysir_bridge.clip import ClipRequest, clamp_request
from openblindysir_bridge.jobs import JobRunner
from openblindysir_bridge.sandbox import Sandbox
from openblindysir_bridge.scanner import scan
from openblindysir_protocol.bridge import JobDone, JobFailed, Welcome
from openblindysir_protocol.enums import ClipFormat, JobFailureCode
from openblindysir_protocol.media import DEMUXER_WHITELIST, INPUT_EXTENSIONS

pytestmark = pytest.mark.ffmpeg


def video(path: Path, *, audio: bool = True, multi: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        shutil.which("ffmpeg"),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:size=640x360:rate=10:duration=20",
    ]
    if audio:
        args += ["-f", "lavfi", "-i", "sine=frequency=440:duration=20"]
    if multi:
        args += ["-f", "lavfi", "-i", "sine=frequency=880:duration=20"]
    args += ["-map", "0:v:0"]
    if audio:
        args += ["-map", "1:a:0"]
    if multi:
        args += ["-map", "2:a:0", "-disposition:a:0", "0", "-disposition:a:1", "default"]
    args += [
        "-c:v",
        "mpeg4",
        "-c:a",
        "aac",
        "-metadata",
        "title=VIDEO-CANARY",
        "-metadata",
        "artist=ARTIST-CANARY",
        "-metadata",
        "album=ALBUM-CANARY",
        "-y",
        str(path),
    ]
    subprocess.run(args, check=True, capture_output=True)


@pytest.mark.parametrize("suffix", ["mp4", "mov", "mkv", "avi"])
def test_safe_video_containers_produce_only_tagless_audio(tmp_path: Path, suffix: str) -> None:
    root = tmp_path / "music"
    video(root / f"source.{suffix}")
    messages, uploads = run_job(root, track_id_of(root, f"source.{suffix}"), tmp_path / "work")
    done = next(m for m in messages if isinstance(m, JobDone))
    assert done.tags.title == "VIDEO-CANARY"
    encoded = next(iter(uploads.values()))
    assert len(encoded) < 300000  # 12 s at AAC 128 kbps, independent of source video
    for canary in (b"VIDEO-CANARY", b"ARTIST-CANARY", b"ALBUM-CANARY", b"source."):
        assert canary not in encoded
    output = tmp_path / "check.m4a"
    output.write_bytes(encoded)
    streams = ffprobe_json(output)["streams"]
    assert [(stream["codec_type"], stream["codec_name"]) for stream in streams] == [
        ("audio", "aac")
    ]
    assert int(streams[0]["bit_rate"]) <= 140000


def test_mp4_without_audio_has_specific_failure_and_never_uploads(tmp_path: Path) -> None:
    root = tmp_path / "music"
    video(root / "silent.mp4", audio=False)
    messages, uploads = run_job(root, track_id_of(root, "silent.mp4"), tmp_path / "work")
    assert not uploads
    assert next(m for m in messages if isinstance(m, JobFailed)).code is JobFailureCode.NO_AUDIO


def test_first_audio_stream_wins_even_when_second_stream_is_default(tmp_path: Path) -> None:
    root = tmp_path / "music"
    video(root / "multi.mp4", multi=True)
    _, uploads = run_job(root, track_id_of(root, "multi.mp4"), tmp_path / "work")
    output = tmp_path / "check.m4a"
    output.write_bytes(next(iter(uploads.values())))
    raw = subprocess.run(
        [
            shutil.which("ffmpeg"),
            "-v",
            "error",
            "-i",
            str(output),
            "-af",
            "highpass=f=650,volumedetect",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    # Count zero crossings of decoded mono PCM instead of relying on stream disposition.
    samples = subprocess.run(
        [
            shutil.which("ffmpeg"),
            "-v",
            "error",
            "-i",
            str(output),
            "-ss",
            "3",
            "-t",
            "1",
            "-ac",
            "1",
            "-ar",
            "8000",
            "-f",
            "s16le",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    pcm = array.array("h", samples)
    crossings = sum(a <= 0 < b for a, b in itertools.pairwise(pcm))
    assert 430 <= crossings <= 450  # deterministic 440 Hz first audio, never 880 Hz default
    assert raw.returncode == 0


def test_large_mp4_never_transfers_video_or_full_source(tmp_path: Path) -> None:
    root = tmp_path / "music"
    source = root / "large.mp4"
    video(source)
    free_size = 96 * 1024 * 1024
    with source.open("r+b") as stream:
        stream.seek(0, 2)
        stream.write(free_size.to_bytes(4, "big") + b"free")
        stream.seek(free_size - 9, 1)
        stream.write(b"\0")
    assert source.stat().st_size > 96 * 1024 * 1024
    _, uploads = run_job(root, track_id_of(root, "large.mp4"), tmp_path / "work")
    assert len(next(iter(uploads.values()))) < 300000


def test_playlist_disguised_as_mp4_cannot_open_an_external_file(tmp_path: Path) -> None:
    root = tmp_path / "music"
    root.mkdir()
    secret = tmp_path / "private.wav"
    secret.write_bytes(b"private")
    (root / "playlist.mp4").write_text(
        f"ffconcat version 1.0\nfile '{secret.as_posix()}'\n", encoding="utf-8"
    )
    messages, uploads = run_job(root, track_id_of(root, "playlist.mp4"), tmp_path / "work")
    assert not uploads
    assert next(m for m in messages if isinstance(m, JobFailed)).code is JobFailureCode.DECODE_ERROR
    assert "concat" not in DEMUXER_WHITELIST
    assert ".m3u8" not in INPUT_EXTENSIONS


def test_exact_cached_replay_survives_source_removal_and_full_listening_requires_opt_in(
    tmp_path: Path,
) -> None:
    root, work = tmp_path / "music", tmp_path / "work"
    video(root / "played.mp4")
    work.mkdir()
    catalog = LocalCatalog.from_scan(scan(root))
    tid = track_id_of(root, "played.mp4")
    sent, uploads = [], []

    async def uploader(url: str, token: str, path: Path, digest: str, mime: str) -> int:
        data = await asyncio.to_thread(path.read_bytes)
        assert hashlib.sha256(data).hexdigest() == digest
        uploads.append(data)
        return 204

    async def wait(count: int) -> None:
        async with asyncio.timeout(20):
            while len([m for m in sent if isinstance(m, JobDone)]) < count:  # noqa: ASYNC110 - bounded protocol polling
                await asyncio.sleep(0.05)

    async def run() -> None:
        runner = JobRunner(
            ffmpeg.discover(), Sandbox(str(root)), lambda: catalog, uploader, sent.append, work
        )
        task = asyncio.create_task(runner.run())
        original = prepare(tid)
        request = ClipRequest(12, 0.3, 128, 2 * 1024 * 1024, ClipFormat.AAC)
        try:
            assert runner.submit(original, request) is None
            await wait(1)
            done = next(m for m in sent if isinstance(m, JobDone))
            full = original.model_copy(
                update={"job_id": "j_000003", "review_mode": "full", "exact_start": 0.0}
            )
            assert runner.submit(full, request) is JobFailureCode.NOT_FOUND
            (root / "played.mp4").unlink()
            replay = original.model_copy(
                update={
                    "job_id": "j_000002",
                    "review_mode": "excerpt",
                    "replay_sha256": done.sha256,
                }
            )
            assert runner.submit(replay, request) is None
            await wait(2)
            assert uploads[0] == uploads[1]
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run())


def test_subprocess_output_is_capped_and_timeout_reaps_the_process() -> None:
    async def run() -> None:
        result = await ffmpeg.run_bounded(
            [sys.executable, "-c", "import sys; sys.stdout.write('x'*1000000)"], 5
        )
        assert len(result.stdout) <= ffmpeg.STDOUT_LIMIT
        timed = await ffmpeg.run_bounded(
            [sys.executable, "-c", "import time; time.sleep(30)"], 0.05
        )
        assert timed.returncode is None

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run())


def test_partial_replay_cache_failure_keeps_the_uploaded_round_and_removes_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, work = tmp_path / "music", tmp_path / "work"
    video(root / "source.mp4")

    def fail_copy(source: Path, destination: Path) -> None:
        destination.write_bytes(b"partial")
        raise OSError("test cache full")

    monkeypatch.setattr("openblindysir_bridge.jobs.shutil.copyfile", fail_copy)
    messages, uploads = run_job(root, track_id_of(root, "source.mp4"), work)
    assert any(isinstance(m, JobDone) for m in messages)
    assert not any(isinstance(m, JobFailed) for m in messages)
    assert len(uploads) == 1
    assert list(work.iterdir()) == []


def test_full_review_caps_segments_and_rejects_a_changed_source(tmp_path: Path) -> None:
    root, work = tmp_path / "music", tmp_path / "work"
    video(root / "source.mp4")
    work.mkdir()
    catalog = LocalCatalog.from_scan(scan(root))
    original = prepare(track_id_of(root, "source.mp4"), 600).model_copy(
        update={"review_mode": "full", "exact_start": 10.0}
    )
    welcome = Welcome.model_validate(
        {
            "t": "WELCOME",
            "clip_format": ClipFormat.AAC,
            "bitrate": 128,
            "limits": {"clip_min_s": 5.0, "clip_max_s": 600.0, "max_clip_bytes": 2097152},
            "catalog_needed": False,
        }
    )
    request = clamp_request(original, welcome)
    assert request.duration_s == 30
    assert not request.fade_audio
    sent, uploads = [], []

    async def uploader(url: str, token: str, path: Path, digest: str, mime: str) -> int:
        uploads.append(await asyncio.to_thread(path.read_bytes))
        return 204

    async def wait(count: int) -> None:
        async with asyncio.timeout(20):
            while len([m for m in sent if isinstance(m, JobDone | JobFailed)]) < count:  # noqa: ASYNC110 - bounded protocol polling
                await asyncio.sleep(0.05)

    async def run() -> None:
        runner = JobRunner(
            ffmpeg.discover(),
            Sandbox(str(root)),
            lambda: catalog,
            uploader,
            sent.append,
            work,
            allow_full_review=True,
        )
        task = asyncio.create_task(runner.run())
        try:
            assert runner.submit(original, request) is None
            await wait(1)
            done = next(m for m in sent if isinstance(m, JobDone))
            assert done.actual_start == 10.0
            assert 9.0 < done.clip_duration < 11.0
            with (root / "source.mp4").open("ab") as stream:
                stream.write(b"changed")
            changed = original.model_copy(
                update={"job_id": "j_000002", "expected_source_revision": done.source_revision}
            )
            assert runner.submit(changed, request) is None
            await wait(2)
            assert (
                next(m for m in sent if isinstance(m, JobFailed)).code is JobFailureCode.NOT_FOUND
            )
            assert len(uploads) == 1
            assert not list(work.glob("replay-*"))  # full segments never populate the excerpt cache
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run())
