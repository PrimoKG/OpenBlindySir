"""Audio-only Docker FFmpeg must keep real decoding across all advertised containers."""

from pathlib import Path

import pytest
from test_jobs_ffmpeg import ffprobe_json, lavfi, run_job, track_id_of

from openblindysir_bridge.clip import ClipRequest
from openblindysir_protocol.bridge import JobDone
from openblindysir_protocol.enums import ClipFormat

pytestmark = pytest.mark.ffmpeg


@pytest.mark.parametrize(
    ("extension", "codec"),
    [
        ("mp3", "libmp3lame"),
        ("flac", "flac"),
        ("wav", "pcm_s16le"),
        ("wav", "adpcm_ima_wav"),
        ("aiff", "pcm_s16be"),
        ("ogg", "libvorbis"),
        ("opus", "libopus"),
        ("aac", "aac"),
        ("m4a", "aac"),
        ("m4a", "alac"),
        ("wma", "wmav2"),
        ("mp4", "aac"),
        ("mov", "pcm_s16le"),
        ("mkv", "flac"),
        ("webm", "libopus"),
        ("avi", "pcm_s16le"),
    ],
)
def test_advertised_containers_keep_audio_decoding(
    tmp_path: Path, extension: str, codec: str
) -> None:
    root = tmp_path / "music"
    filename = "synthetic." + extension
    lavfi(root / filename, "sine=frequency=440:duration=40", "-c:a", codec)
    messages, uploads = run_job(root, track_id_of(root, filename), tmp_path / "work")
    assert any(isinstance(message, JobDone) for message in messages)
    output = tmp_path / "result.m4a"
    output.write_bytes(next(iter(uploads.values())))
    assert [(s["codec_type"], s["codec_name"]) for s in ffprobe_json(output)["streams"]] == [
        ("audio", "aac")
    ]


def test_opus_output_remains_available(tmp_path: Path) -> None:
    root = tmp_path / "music"
    lavfi(root / "source.flac", "sine=frequency=440:duration=40")
    messages, uploads = run_job(
        root,
        track_id_of(root, "source.flac"),
        tmp_path / "work",
        request=ClipRequest(12, 0.3, 128, 4 * 1024 * 1024, ClipFormat.OPUS),
    )
    assert any(isinstance(message, JobDone) for message in messages)
    output = tmp_path / "result.webm"
    output.write_bytes(next(iter(uploads.values())))
    assert [(s["codec_type"], s["codec_name"]) for s in ffprobe_json(output)["streams"]] == [
        ("audio", "opus")
    ]
