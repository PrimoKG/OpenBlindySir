"""Pure Bridge rules: start point, bounds against a hostile server, URLs, FFmpeg template."""

import json

import pytest

from openblindysir_bridge import ffmpeg
from openblindysir_bridge.clip import (
    BRIDGE_CLIP_MAX_S,
    BRIDGE_CLIP_MIN_S,
    TooShortError,
    clamp_request,
    compute_start,
)
from openblindysir_bridge.urls import InvalidServerUrlError, validate_server_url
from openblindysir_protocol.bridge import Prepare, Welcome
from openblindysir_protocol.enums import ClipFormat

TOOLS = ffmpeg.FfmpegTools(ffmpeg="ffmpeg", ffprobe="ffprobe")


def prepare(duration: float, fraction: float = 0.5) -> Prepare:
    return Prepare.model_validate_json(
        json.dumps(
            {
                "t": "PREPARE",
                "job_id": "j_000001",
                "track_id": "t_0123456789abcdef",
                "start_fraction": fraction,
                "duration": duration,
                "upload_url": "/api/bridge/assets/a_" + "A" * 22,
                "upload_token": "T" * 43,
            }
        )
    )


def welcome(clip_min: float, clip_max: float, bitrate: int = 128) -> Welcome:
    return Welcome.model_validate_json(
        json.dumps(
            {
                "t": "WELCOME",
                "clip_format": "aac",
                "bitrate": bitrate,
                "limits": {
                    "clip_min_s": clip_min,
                    "clip_max_s": clip_max,
                    "max_clip_bytes": 64_000_000,
                },
                "catalog_needed": False,
            }
        )
    )


def test_start_point_inside_valid_window() -> None:
    start, duration = compute_start(200.0, 25.0, 0.0)
    assert start == pytest.approx(max(10, 16))
    start, duration = compute_start(200.0, 25.0, 0.999)
    assert start + duration <= 200 - max(20, 20) + 0.01


def test_empty_window_starts_at_a_third() -> None:
    assert compute_start(40.0, 25.0, 0.5) == (pytest.approx(min(40 / 3, 15.0)), 25.0)


def test_track_shorter_than_clip_is_played_whole() -> None:
    assert compute_start(20.0, 30.0, 0.5) == (0.0, 20.0)


def test_track_under_eight_seconds_is_too_short() -> None:
    with pytest.raises(TooShortError):
        compute_start(7.9, 25.0, 0.5)


def test_bridge_bounds_win_against_hostile_server() -> None:
    request = clamp_request(prepare(600), welcome(500, 1))  # inverted, absurd limits
    assert BRIDGE_CLIP_MIN_S <= request.duration_s <= BRIDGE_CLIP_MAX_S
    assert request.max_bytes <= 4 * 1024 * 1024
    assert clamp_request(prepare(1), welcome(1, 2)).duration_s == BRIDGE_CLIP_MIN_S
    assert clamp_request(prepare(25), welcome(5, 60, bitrate=150)).bitrate_kbps == 128


def test_encode_argv_is_the_fixed_template() -> None:
    argv = ffmpeg.encode_argv(
        TOOLS,
        "/m/a.flac",
        "/tmp/out.m4a",
        start=12.5,
        duration=25.0,
        bitrate_kbps=128,
        clip_format=ClipFormat.AAC,
    )
    assert argv[argv.index("-i") + 1] == "file:/m/a.flac"
    assert argv.index("-ss") < argv.index("-i") < argv.index("-t")
    assert argv.index("-protocol_whitelist") < argv.index("-i")
    assert argv.index("-format_whitelist") < argv.index("-i")
    assert argv[argv.index("-format_whitelist") + 1] == ffmpeg.DEMUXER_WHITELIST
    assert "concat" not in ffmpeg.DEMUXER_WHITELIST
    for group in (["-map", "0:a:0"], ["-map_metadata", "-1"], ["-map_chapters", "-1"]):
        position = argv.index(group[0])
        assert argv[position : position + 2] == group
    assert {"-vn", "-sn", "-dn", "-nostdin"} <= set(argv)
    assert argv[argv.index("-af") + 1] == "afade=t=in:st=0:d=0.3,afade=t=out:st=23.500:d=1.5"
    assert argv[-1] == "file:/tmp/out.m4a"


def test_file_prefix_protects_names_starting_with_dash() -> None:
    argv = ffmpeg.encode_argv(
        TOOLS,
        "-evil.mp3",
        "out.m4a",
        start=0,
        duration=10,
        bitrate_kbps=128,
        clip_format=ClipFormat.AAC,
    )
    assert "-evil.mp3" not in argv
    assert "file:-evil.mp3" in argv


def test_probe_argv_is_whitelisted() -> None:
    argv = ffmpeg.probe_argv(TOOLS, "/m/a.flac")
    assert argv[-1] == "file:/m/a.flac"
    assert "-format_whitelist" in argv


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org",
        "ws://example.org",
        "https://user:pw@example.org",
        "https://x.org/path",
        "https://x.org?q=1",
        "ftp://x.org",
    ],
)
def test_server_url_refused(url: str) -> None:
    with pytest.raises(InvalidServerUrlError):
        validate_server_url(url)


def test_server_url_accepted() -> None:
    assert validate_server_url("https://openblindysir.example.com").ws_url() == (
        "wss://openblindysir.example.com/api/bridge/ws"
    )
    local = validate_server_url("http://localhost:8000")
    assert local.ws_url() == "ws://localhost:8000/api/bridge/ws"
    assert (
        local.join_path("/api/bridge/assets/a_x") == "http://localhost:8000/api/bridge/assets/a_x"
    )
    with pytest.raises(InvalidServerUrlError):
        local.join_path("//evil.example/x")
