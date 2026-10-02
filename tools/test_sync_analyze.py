"""Tests for tools/sync_analyze.py (and the calibration generator it pairs with).

Run: uv run --with numpy --with pytest pytest tools/test_sync_analyze.py
"""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import calibration_clip as cc
import sync_analyze as sa

N_BURSTS = len(cc.CalibrationSpec(freq_hz=1000).onset_samples())  # 58 with the defaults


def mix_voices(
    offsets_ms: dict[int, float],
    *,
    sample_rate: int = 48000,
    duration_s: float = 30.0,
    gains: dict[int, float] | None = None,
    drift_ppm: dict[int, float] | None = None,
    missing: dict[int, list[int]] | None = None,
    noise_rms: float = 0.0,
    seed: int = 1234,
) -> np.ndarray:
    """Simulated microphone recording: calibration voices at known offsets.

    Drift is simulated by stretching the burst period of a voice (a device whose clock runs
    slow plays its bursts slightly further apart).
    """
    gains = gains or {}
    drift_ppm = drift_ppm or {}
    missing = missing or {}
    length = duration_s + 1.0
    out = np.zeros(round(length * sample_rate))
    for voice, offset_ms in offsets_ms.items():
        factor = 1.0 + drift_ppm.get(voice, 0.0) * 1e-6
        spec = cc.CalibrationSpec(
            freq_hz=cc.DEFAULT_FREQS_HZ[voice],
            sample_rate=sample_rate,
            duration_s=duration_s,
            period_s=cc.DEFAULT_PERIOD_S * factor,
            lead_in_s=cc.DEFAULT_LEAD_IN_S * factor,
            amplitude=gains.get(voice, 0.5),
        )
        signal = cc.render(spec, delay_s=offset_ms * 1e-3, length_s=length)
        burst_len = spec.burst_samples
        for n in missing.get(voice, []):
            start = round((spec.lead_in_s + n * spec.period_s + offset_ms * 1e-3) * sample_rate)
            signal[max(0, start - 2) : start + burst_len + 2] = 0.0
        out += signal
    if noise_rms:
        out += np.random.default_rng(seed).normal(0.0, noise_rms, len(out))
    return out


def expected_p90(offsets_ms: dict[int, float]) -> float:
    """p90 of pooled pairwise |offset| when every pair has the same number of bursts."""
    values = []
    voices = sorted(offsets_ms)
    for i, a in enumerate(voices):
        for b in voices[i + 1 :]:
            values.extend([abs(offsets_ms[b] - offsets_ms[a])] * 50)
    return float(np.percentile(values, 90))


def only_run(result: sa.AnalysisResult) -> sa.RunResult:
    assert len(result.runs) == 1, [(r.start_s, r.end_s) for r in result.runs]
    return result.runs[0]


def stats_for(run: sa.RunResult | sa.AnalysisResult, a: int, b: int) -> sa.OffsetStats:
    if isinstance(run, sa.AnalysisResult):
        run = only_run(run)
    for s in run.vs_reference + run.pairs:
        if s.voice_a == a and s.voice_b == b:
            return s
    raise AssertionError(f"no stats for pair {a}-{b}")


def run_voice(run: sa.RunResult, index: int) -> sa.RunVoice:
    return next(rv for rv in run.voices if rv.index == index)


def test_known_offsets_with_noise_gains_missing_burst_and_drift() -> None:
    offsets = {0: 0.0, 1: 23.0, 2: -41.0, 3: 110.0}
    signal = mix_voices(
        offsets,
        gains={0: 0.6, 1: 0.15, 2: 0.4, 3: 0.05},  # up to 22 dB level difference
        drift_ppm={2: 40.0},  # 40 ppm over 29 s = 1.2 ms at the end
        missing={1: [10], 3: [3, 40]},
        noise_rms=0.01,
    )
    result = sa.analyze(signal, 48000, sa.AnalysisConfig(reference=0, expect=4))
    run = only_run(result)

    assert [v.present for v in result.voices] == [True, True, True, True, False, False]
    assert result.voices[0].count == N_BURSTS
    assert result.voices[1].count == N_BURSTS - 1
    assert result.voices[3].count == N_BURSTS - 2
    for voice, offset in offsets.items():
        if voice == 0:
            continue
        s = stats_for(run, 0, voice)
        # voice 2 drifts by up to 1.2 ms: its median offset moves by about 0.6 ms
        assert s.median_ms == pytest.approx(offset, abs=2.0), (voice, s)
    assert run_voice(run, 2).drift_ppm == pytest.approx(40.0, abs=15.0)
    for voice in (0, 1, 3):
        assert abs(run_voice(run, voice).drift_ppm) < 15.0
        assert run_voice(run, voice).jitter_ms < 0.5

    # pairwise: B relative to A
    assert stats_for(run, 2, 3).median_ms == pytest.approx(151.0, abs=2.0)
    assert stats_for(run, 1, 2).median_ms == pytest.approx(-64.0, abs=2.0)
    assert run.overall_p90_ms == pytest.approx(expected_p90(offsets), abs=2.0)
    assert run.burst_spread_p90_ms == pytest.approx(151.0, abs=2.0)
    assert run.status == "FAIL" and result.status == "FAIL"
    assert result.passed is False


def test_all_zero_offsets_pass() -> None:
    offsets = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}
    signal = mix_voices(offsets, noise_rms=0.02)
    result = sa.analyze(signal, 48000, sa.AnalysisConfig(expect=6))
    run = only_run(result)
    assert all(v.present for v in result.voices)
    assert run.overall_p90_ms is not None and run.overall_p90_ms < 1.0
    assert run.overall_max_ms is not None and run.overall_max_ms < 2.0
    assert len(run.pairs) == 15
    assert not run.warnings and not run.problems
    assert result.passed is True


def test_overlapping_bursts_of_adjacent_voices() -> None:
    # 3 ms apart: the matched-filter responses of voices 0 and 1 overlap almost entirely
    offsets = {0: 0.0, 1: 3.0, 2: -5.0}
    result = sa.analyze(mix_voices(offsets, noise_rms=0.005), 48000, sa.AnalysisConfig(reference=0))
    assert stats_for(result, 0, 1).median_ms == pytest.approx(3.0, abs=0.5)
    assert stats_for(result, 0, 2).median_ms == pytest.approx(-5.0, abs=0.5)


def test_other_sample_rate_and_threshold() -> None:
    offsets = {0: 0.0, 1: 35.0, 2: 70.0}
    signal = mix_voices(offsets, sample_rate=44100, duration_s=15.0, noise_rms=0.01)
    result = sa.analyze(signal, 44100, sa.AnalysisConfig(threshold_ms=80.0))
    assert stats_for(result, 0, 2).median_ms == pytest.approx(70.0, abs=2.0)
    assert only_run(result).overall_p90_ms == pytest.approx(expected_p90(offsets), abs=2.0)
    assert result.passed is True
    strict = sa.analyze(signal, 44100, sa.AnalysisConfig(threshold_ms=60.0))
    assert strict.passed is False


def test_single_voice_is_not_a_pass() -> None:
    result = sa.analyze(mix_voices({0: 0.0}), 48000, sa.AnalysisConfig())
    assert only_run(result).overall_p90_ms is None
    assert result.status == "NO_DATA"
    assert result.passed is False
    assert sa.exit_code(result) == 2


def test_noise_only_detects_nothing() -> None:
    noise = np.random.default_rng(7).normal(0.0, 0.1, 48000 * 10)
    result = sa.analyze(noise, 48000, sa.AnalysisConfig())
    assert not any(v.present for v in result.voices)
    assert result.runs == [] and result.status == "NO_DATA"


def _write_wav(path: Path, frames: np.ndarray, rate: int, width: int) -> None:
    scale = float(1 << (8 * width - 1)) - 1
    ints = np.round(frames * scale).astype(np.int64)
    if width == 2:
        raw = ints.astype("<i2").tobytes()
    else:  # 24-bit little endian
        u = (ints & 0xFFFFFF).astype(np.uint32)
        raw = np.stack([u & 0xFF, (u >> 8) & 0xFF, (u >> 16) & 0xFF], axis=-1).astype(np.uint8)
        raw = raw.tobytes()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(frames.shape[1])
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(raw)


@pytest.mark.parametrize("width", [2, 3])
def test_cli_on_stereo_wav(tmp_path: Path, width: int, capsys: pytest.CaptureFixture[str]) -> None:
    offsets = {0: 0.0, 1: -12.0, 4: 25.0}
    mono = mix_voices(offsets, duration_s=12.0, noise_rms=0.005)
    stereo = np.stack([mono, 0.5 * mono], axis=1)
    path = tmp_path / f"rec{width}.wav"
    _write_wav(path, stereo, 48000, width)

    frames, rate = sa.read_wav(path)
    assert rate == 48000 and frames.shape == stereo.shape

    out_json = tmp_path / "out.json"
    code = sa.main([str(path), "--reference", "0", "--expect", "3", "--json", str(out_json)])
    report = capsys.readouterr().out
    assert code == 0
    assert "RESULT: PASS" in report
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert len(data["runs"]) == 1 and data["runs"][0]["passed"] is True
    by_pair = {(s["voice_a"], s["voice_b"]): s for s in data["runs"][0]["vs_reference"]}
    assert by_pair[(0, 1)]["median_ms"] == pytest.approx(-12.0, abs=2.0)
    assert by_pair[(0, 4)]["median_ms"] == pytest.approx(25.0, abs=2.0)
    assert data["passed"] is True

    assert sa.main([str(path), "--threshold-ms", "20"]) == 1
    assert sa.main([str(path), "--expect", "4"]) == 2  # a fourth device did not play


def test_float_wav_reader(tmp_path: Path) -> None:
    import struct

    samples = np.array([0.0, 0.5, -0.25, 1.0], dtype="<f4")
    data = samples.tobytes()
    fmt = struct.pack("<HHIIHH", 3, 1, 8000, 8000 * 4, 4, 32)
    blob = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data"
    blob += struct.pack("<I", len(data)) + data
    path = tmp_path / "f.wav"
    path.write_bytes(b"RIFF" + struct.pack("<I", len(blob)) + blob)
    frames, rate = sa.read_wav(path)
    assert rate == 8000
    assert frames[:, 0].tolist() == pytest.approx([0.0, 0.5, -0.25, 1.0])


def test_constants_match_generator() -> None:
    assert sa.DEFAULT_FREQS_HZ == cc.DEFAULT_FREQS_HZ
    assert sa.DEFAULT_PERIOD_S == cc.DEFAULT_PERIOD_S
    assert sa.DEFAULT_BURST_MS == cc.DEFAULT_BURST_MS


def test_generator_onsets_are_exact_samples() -> None:
    spec = cc.CalibrationSpec(freq_hz=1400.0)
    onsets = spec.onset_samples()
    assert onsets[:3] == [48000, 72000, 96000]
    assert len(onsets) == 58  # 1.0 s .. 29.5 s
    signal = cc.render(spec)
    assert np.all(signal[: onsets[0]] == 0.0)
    assert np.any(signal[onsets[0] : onsets[0] + spec.burst_samples] != 0.0)


# --------------------------------------------------------------------------------------------
# Regressions: offsets of half a period or more, several runs, missing or quiet devices
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("late_ms", [480.0, -480.0, 260.0, -260.0, 250.0, 500.0, 760.0])
def test_offsets_beyond_half_period_are_not_aliased(late_ms: float) -> None:
    """Pairing by absolute burst index: 480 ms must read +480 (not -20), 260 must read +260
    (not -240), and 250 must not mix signs."""
    offsets = {0: 0.0, 1: late_ms, 2: 10.0}
    config = sa.AnalysisConfig(reference=0, expect=3)
    result = sa.analyze(mix_voices(offsets, noise_rms=0.005), 48000, config)
    run = only_run(result)
    s = stats_for(run, 0, 1)
    assert s.count == N_BURSTS
    assert s.median_ms == pytest.approx(late_ms, abs=0.5)
    assert s.max_abs_ms == pytest.approx(abs(late_ms), abs=0.5)  # same sign on every burst
    assert s.std_ms < 0.5
    assert stats_for(run, 0, 2).median_ms == pytest.approx(10.0, abs=0.5)
    assert result.status == "FAIL" and sa.exit_code(result) == 1


def test_cli_one_period_late_device_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "late.wav"
    mono = mix_voices({0: 0.0, 1: 480.0, 2: 10.0}, duration_s=12.0, noise_rms=0.005)
    _write_wav(path, mono[:, None], 48000, 2)
    code = sa.main([str(path), "--reference", "0", "--expect", "3"])
    report = capsys.readouterr().out
    assert code == 1
    assert "+480.0" in report and "RESULT: FAIL" in report


def test_missing_first_burst_is_ambiguous_not_silently_wrong() -> None:
    # voice 1 misses its first burst: from the bursts alone it could be 520 ms late instead
    # of 20 ms, so the default anchor must refuse to guess
    signal = mix_voices({0: 0.0, 1: 20.0, 2: 0.0}, missing={1: [0]}, noise_rms=0.005)
    result = sa.analyze(signal, 48000, sa.AnalysisConfig(reference=0))
    run = only_run(result)
    assert run.status == "AMBIGUOUS"
    assert run.pairs == [] and run.overall_p90_ms is None
    assert sa.exit_code(result) == 2
    # the operator knows the clips ran to the end: anchor on the last burst
    end = sa.analyze(signal, 48000, sa.AnalysisConfig(reference=0, anchor="end"))
    assert stats_for(end, 0, 1).median_ms == pytest.approx(20.0, abs=0.5)
    assert end.passed is True


def test_t_past_play_with_end_anchor() -> None:
    # "T already past": devices join mid-clip at different bursts but stay on the grid
    offsets = {0: 0.0, 1: 15.0, 2: -30.0}
    signal = mix_voices(offsets, missing={0: list(range(6)), 1: list(range(9)), 2: list(range(7))})
    both = sa.analyze(signal, 48000, sa.AnalysisConfig(reference=0))
    assert only_run(both).status == "AMBIGUOUS"
    result = sa.analyze(signal, 48000, sa.AnalysisConfig(reference=0, anchor="end", expect=3))
    run = only_run(result)
    assert stats_for(run, 0, 1).median_ms == pytest.approx(15.0, abs=0.5)
    assert stats_for(run, 0, 2).median_ms == pytest.approx(-30.0, abs=0.5)
    assert stats_for(run, 0, 1).count == N_BURSTS - 9
    assert result.passed is True


def test_two_runs_in_one_recording_are_split() -> None:
    first = mix_voices({0: 0.0, 1: 20.0, 2: -15.0}, noise_rms=0.005, seed=1)
    second = mix_voices({0: 0.0, 1: 35.0, 2: 80.0}, drift_ppm={2: 60.0}, noise_rms=0.005, seed=2)
    signal = np.concatenate([first, np.zeros(round(5.23 * 48000)), second])
    result = sa.analyze(signal, 48000, sa.AnalysisConfig(reference=0, expect=3))
    assert len(result.runs) == 2
    r1, r2 = result.runs
    assert r1.end_s < r2.start_s
    assert stats_for(r1, 0, 1).median_ms == pytest.approx(20.0, abs=0.5)
    assert stats_for(r1, 0, 2).median_ms == pytest.approx(-15.0, abs=0.5)
    assert stats_for(r2, 0, 1).median_ms == pytest.approx(35.0, abs=0.5)
    assert stats_for(r2, 0, 2).median_ms == pytest.approx(80.0, abs=2.0)
    for run in (r1, r2):
        for rv in run.voices:
            assert rv.count == N_BURSTS
            assert rv.jitter_ms < 0.5
            expected_ppm = 60.0 if (run is r2 and rv.index == 2) else 0.0
            assert rv.drift_ppm == pytest.approx(expected_ppm, abs=15.0)
    assert r1.status == "PASS" and r2.status == "FAIL"
    assert result.status == "FAIL" and sa.exit_code(result) == 1


def test_poorly_detected_voice_makes_the_run_incomplete() -> None:
    # voice 1 is heard on only 19 of 58 bursts (its first and last bursts are missing too)
    missing = [n for n in range(N_BURSTS) if n % 3 != 1]
    signal = mix_voices({0: 0.0, 1: 20.0, 2: 0.0}, missing={1: missing}, noise_rms=0.005)
    result = sa.analyze(signal, 48000, sa.AnalysisConfig(reference=0))
    run = only_run(result)
    rv = run_voice(run, 1)
    assert rv.low_coverage and rv.count == 19
    assert any("voice 1 detected on 19/58" in w for w in run.warnings)
    assert run.status == "INCOMPLETE" and sa.exit_code(result) == 2
    assert stats_for(run, 0, 2).median_ms == pytest.approx(0.0, abs=0.5)  # others still shown


def test_expect_catches_a_device_that_did_not_play() -> None:
    signal = mix_voices({0: 0.0, 1: 20.0}, noise_rms=0.005)
    assert sa.analyze(signal, 48000, sa.AnalysisConfig()).passed is True
    result = sa.analyze(signal, 48000, sa.AnalysisConfig(expect=3))
    assert only_run(result).status == "INCOMPLETE"
    assert sa.exit_code(result) == 2


def test_grid_indices_dedupe_and_offgrid_first() -> None:
    # 1.2: off-grid first detection (kept: a device re-scheduled mid-run must show up as a
    # large offset, not vanish); 2.04: second detection of burst 2 (dropped)
    onsets = np.array([1.2, 1.5, 2.0, 2.04, 3.0, 3.5])
    kept, n = sa.grid_indices(onsets, 0.5)
    assert kept.tolist() == pytest.approx([1.2, 1.5, 2.0, 3.0, 3.5])
    assert n.tolist() == [0, 1, 2, 4, 5]
