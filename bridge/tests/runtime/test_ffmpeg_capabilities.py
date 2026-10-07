"""Reject incomplete tools before scanning/encoding; never echo build paths."""

import pytest

from openblindysir_bridge import ffmpeg
from openblindysir_protocol.enums import ClipFormat
from openblindysir_protocol.media import INPUT_DEMUXER_BY_EXTENSION


def capabilities(monkeypatch, *, missing=None, version="9.0.2", opus=True):
    demuxers = set(INPUT_DEMUXER_BY_EXTENSION.values()) - {missing}
    responses = {
        "-version": f"ffmpeg version {version} --prefix=/private/build/path",
        "-encoders": " A..... aac\n" + (" A..... libopus\n" if opus else ""),
        "-demuxers": "\n".join(f" D  {name}" for name in sorted(demuxers)),
        "-muxers": " E ipod\n E webm",
        "-filters": " ... loudnorm A->A\n ... afade A->A\n ... silencedetect A->A",
    }
    monkeypatch.setattr(ffmpeg, "_capabilities", lambda executable, option: responses[option])
    return responses


def test_aac_is_required_and_opus_is_optional(monkeypatch):
    capabilities(monkeypatch, opus=False)
    info = ffmpeg.check(ffmpeg.FfmpegTools("ffmpeg", "ffprobe"))
    assert info.formats() == [ClipFormat.AAC]
    assert info.version == "FFmpeg 9.0.2"
    assert "private" not in info.version


@pytest.mark.parametrize("missing", sorted(set(INPUT_DEMUXER_BY_EXTENSION.values())))
def test_missing_forced_demuxer_is_actionable(monkeypatch, missing):
    capabilities(monkeypatch, missing=missing)
    with pytest.raises(ffmpeg.FfmpegMissingError, match="Démultiplexeurs absents"):
        ffmpeg.check(ffmpeg.FfmpegTools("ffmpeg", "ffprobe"))


def test_restricted_extension_set_requires_only_its_input_demuxers(monkeypatch):
    capabilities(monkeypatch, missing="avi")
    assert ffmpeg.check(ffmpeg.FfmpegTools("ffmpeg", "ffprobe"), frozenset({".mp3"}))


@pytest.mark.parametrize("option", ["-encoders", "-muxers", "-filters"])
def test_missing_output_or_processing_capabilities_rejected(monkeypatch, option):
    responses = capabilities(monkeypatch)
    responses[option] = ""
    with pytest.raises(ffmpeg.FfmpegMissingError, match="absents"):
        ffmpeg.check(ffmpeg.FfmpegTools("ffmpeg", "ffprobe"))


@pytest.mark.parametrize("version", ["4.3.9", "4.4", "7.1.5", "8.1.2", "9.0", "9.0.1"])
def test_old_ffmpeg_rejected(monkeypatch, version):
    capabilities(monkeypatch, version=version)
    with pytest.raises(ffmpeg.FfmpegMissingError, match="trop ancien"):
        ffmpeg.check(ffmpeg.FfmpegTools("ffmpeg", "ffprobe"))


@pytest.mark.parametrize("label", ["encoder", "probe"])
def test_mixed_versions_are_rejected(monkeypatch, label):
    responses = capabilities(monkeypatch)
    monkeypatch.setattr(
        ffmpeg,
        "_capabilities",
        lambda executable, option: (
            "ffmpeg version 9.0.1"
            if executable == ("ffmpeg" if label == "encoder" else "ffprobe")
            and option == "-version"
            else responses[option]
        ),
    )
    with pytest.raises(ffmpeg.FfmpegMissingError, match=r"9\.0\.2"):
        ffmpeg.check(ffmpeg.FfmpegTools("ffmpeg", "ffprobe"))


def test_unknown_version_is_not_assumed_safe(monkeypatch):
    capabilities(monkeypatch, version="N-custom")
    with pytest.raises(ffmpeg.FfmpegMissingError, match="non identifiable"):
        ffmpeg.check(ffmpeg.FfmpegTools("ffmpeg", "ffprobe"))


@pytest.mark.parametrize("version", ["9.0.2", "n9.0.2-1-gabcdef", "9.0.3", "9.1", "10.0"])
def test_supported_versions_keep_patch_precision(monkeypatch, version):
    capabilities(monkeypatch, version=version)
    assert ffmpeg.check(ffmpeg.FfmpegTools("ffmpeg", "ffprobe"))
