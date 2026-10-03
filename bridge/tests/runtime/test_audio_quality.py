"""Exercise silence avoidance and volume normalization on generated audio only."""

import asyncio
import re
from pathlib import Path

import pytest
from test_jobs_ffmpeg import lavfi, run_job, track_id_of

from openblindysir_bridge import ffmpeg
from openblindysir_bridge.clip import ClipRequest
from openblindysir_protocol.bridge import JobDone, JobFailed
from openblindysir_protocol.enums import ClipFormat, JobFailureCode

pytestmark = pytest.mark.ffmpeg


def test_silent_track_is_rejected_without_upload(tmp_path: Path) -> None:
    root = tmp_path / "music"
    lavfi(root / "silence.wav", "anullsrc=r=48000:cl=stereo:d=60")
    messages, uploads = run_job(root, track_id_of(root, "silence.wav"), tmp_path / "work")
    assert not uploads
    assert next(m for m in messages if isinstance(m, JobFailed)).code is JobFailureCode.SILENT_AUDIO


def test_leading_silence_moves_excerpt_into_audible_audio(tmp_path: Path) -> None:
    root = tmp_path / "music"
    lavfi(
        root / "leading.wav",
        "sine=frequency=440:duration=60",
        "-af",
        "volume=0:enable='lt(t,25)'",
    )
    messages, uploads = run_job(root, track_id_of(root, "leading.wav"), tmp_path / "work")
    done = next(m for m in messages if isinstance(m, JobDone))
    assert done.actual_start == pytest.approx(25, abs=0.2)
    assert uploads


def test_quiet_clip_normalization_can_be_disabled(tmp_path: Path) -> None:
    root = tmp_path / "music"
    lavfi(root / "quiet.wav", "sine=frequency=440:duration=60", "-af", "volume=0.01")
    levels = []
    tools = ffmpeg.discover()
    for normalize in (False, True):
        request = ClipRequest(12, 0.3, 128, 4 * 1024 * 1024, ClipFormat.AAC, normalize, True)
        messages, uploads = run_job(
            root, track_id_of(root, "quiet.wav"), tmp_path / str(normalize), request=request
        )
        assert any(isinstance(m, JobDone) for m in messages)
        clip = tmp_path / f"check-{normalize}.m4a"
        clip.write_bytes(next(iter(uploads.values())))
        run = asyncio.run(ffmpeg.run_bounded(ffmpeg.analysis_argv(tools, str(clip), 0, 12), 10))
        match = re.search(r"mean_volume:\s*([-\d.]+) dB", run.stderr)
        assert match is not None
        levels.append(float(match.group(1)))
    assert levels[1] - levels[0] > 20
    assert -22 < levels[1] < -12
