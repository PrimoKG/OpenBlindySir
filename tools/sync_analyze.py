#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy>=1.26"]
# ///
"""Acoustic sync analysis for OpenBlindySir (spec section 20.5).

Input: a WAV recording, made by one microphone, of several devices playing their
calibration clips (``tools/calibration_clip.py``) at the same time. Each device plays a
*voice*: Hann-windowed tone bursts every ``period`` seconds at a voice-specific frequency.

Algorithm
---------
1. The recording is mixed to mono (or one channel is selected).
2. For each voice frequency ``f``, a complex matched filter is applied: the recording is
   correlated with the analytic template ``w[k] * exp(2j*pi*f*k/fs)`` (same Hann window and
   length as the generated bursts). The magnitude of the result is a phase-insensitive
   envelope that peaks where a burst of that voice starts, and largely ignores the other
   voices (400 Hz apart by default) and broadband noise.
3. Bursts are detected as local maxima of the envelope, at least ``0.8 * period`` apart,
   above ``noise_floor + snr_db`` and within ``rel_db`` of the typical burst level of that
   voice (which rejects weak harmonics or echoes from other devices).
4. Each burst time is refined at full sample rate on the *rising edge* of the envelope (half
   of the peak, linearly interpolated), then converted to the burst start time with the
   template's own autocorrelation. The rising edge is less biased by room reverberation
   than the peak.
5. Runs: the recording is cut into runs (one per play of the clips) wherever no voice has a
   burst for more than ``--split-gap`` (default 2 s). Everything below is per run.
6. Per voice, every onset gets a burst index (first detected burst = 0) and a straight line
   ``t = a + b * n`` is fitted: ``b`` gives the clock drift of the device relative to the
   recorder, in ppm, and the residuals give the detection jitter.
7. Anchoring: all bursts look alike, so an offset is only defined modulo the period unless
   the voices are numbered from the same clip burst. With ``--anchor both`` (default) every
   voice must cover the same number of bursts (same first and last clip burst); otherwise the
   run is AMBIGUOUS (exit 2) instead of silently reporting an offset off by k x period.
   ``--anchor end`` numbers bursts from the last one ('T past' or rejoin plays, where devices
   start mid-clip); ``--anchor start`` from the first one.
8. Pairs of voices: onsets with the same absolute burst index are paired; offset =
   t(voice B) - t(voice A), positive when B is late, including whole periods (a device
   500 ms late reads +500 ms).
9. Coverage: a voice detected on fewer than ``--min-coverage`` (80 %) of the bursts of the
   run makes the run INCOMPLETE (exit 2), and so does, with ``--expect N``, a run with fewer
   than N well-detected voices (a device that did not play at all).
10. Verdict per run: p90 of the absolute pairwise offsets pooled over every pair of voices
    and every burst of the run, compared with ``--threshold-ms`` (default 60 ms, gate G1).

Sound travels about 2.9 ms per metre: place the devices at the same distance from the
microphone, or account for it.

Usage::

    uv run tools/sync_analyze.py recording.wav
    uv run tools/sync_analyze.py recording.wav --expect 3 --reference 0 --json -

Exit status: 0 every run PASS, 1 a run FAILs, 2 usage error, or a run AMBIGUOUS/INCOMPLETE,
or fewer than two voices detected.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# Keep identical to tools/calibration_clip.py.
DEFAULT_FREQS_HZ: tuple[float, ...] = (1400.0, 1800.0, 2200.0, 2600.0, 3000.0, 3400.0)
DEFAULT_PERIOD_S = 0.5
DEFAULT_BURST_MS = 10.0
DEFAULT_THRESHOLD_MS = 60.0
DEFAULT_SPLIT_GAP_S = 2.0
DEFAULT_MIN_COVERAGE = 0.8

_WAVE_FORMAT_PCM = 0x0001
_WAVE_FORMAT_IEEE_FLOAT = 0x0003
_WAVE_FORMAT_EXTENSIBLE = 0xFFFE


# --------------------------------------------------------------------------------------------
# WAV input
# --------------------------------------------------------------------------------------------


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """Read a WAV file as float64 samples of shape (frames, channels), plus the sample rate.

    Supports PCM 8/16/24/32-bit integers and IEEE float 32/64-bit, including
    WAVE_FORMAT_EXTENSIBLE headers. Other formats (compressed, RF64) raise ValueError:
    convert them first, e.g. ``ffmpeg -i rec.m4a -ac 1 -ar 48000 rec.wav``.
    """
    data = path.read_bytes()
    if len(data) < 12 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a RIFF/WAVE file")
    fmt: tuple[int, int, int, int] | None = None  # (tag, channels, rate, bits)
    payload: bytes | None = None
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        (size,) = struct.unpack_from("<I", data, pos + 4)
        body = data[pos + 8 : pos + 8 + size]
        if chunk_id == b"fmt ":
            tag, channels, rate = struct.unpack_from("<HHI", body, 0)
            (bits,) = struct.unpack_from("<H", body, 14)
            if tag == _WAVE_FORMAT_EXTENSIBLE and len(body) >= 26:
                (tag,) = struct.unpack_from("<H", body, 24)  # first 2 bytes of SubFormat GUID
            fmt = (tag, channels, rate, bits)
        elif chunk_id == b"data":
            payload = body
        pos += 8 + size + (size & 1)
    if fmt is None or payload is None:
        raise ValueError(f"{path}: missing fmt or data chunk")
    tag, channels, rate, bits = fmt
    width = bits // 8
    usable = len(payload) - len(payload) % (width * channels)
    raw = payload[:usable]
    if tag == _WAVE_FORMAT_PCM and bits == 8:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    elif tag == _WAVE_FORMAT_PCM and bits == 16:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    elif tag == _WAVE_FORMAT_PCM and bits == 24:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        ints = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        ints = np.where(ints >= 1 << 23, ints - (1 << 24), ints)
        samples = ints.astype(np.float64) / float(1 << 23)
    elif tag == _WAVE_FORMAT_PCM and bits == 32:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.float64) / float(1 << 31)
    elif tag == _WAVE_FORMAT_IEEE_FLOAT and bits in (32, 64):
        samples = np.frombuffer(raw, dtype="<f4" if bits == 32 else "<f8").astype(np.float64)
    else:
        raise ValueError(f"{path}: unsupported WAV format tag={tag:#x} bits={bits}")
    return samples.reshape(-1, channels), rate


def to_mono(frames: np.ndarray, channel: str = "mix") -> np.ndarray:
    """Select one channel (``"0"``, ``"1"``...) or average them all (``"mix"``)."""
    if frames.ndim == 1:
        return frames
    if channel == "mix":
        return frames.mean(axis=1)
    index = int(channel)
    if not 0 <= index < frames.shape[1]:
        raise ValueError(f"channel {index} out of range (file has {frames.shape[1]})")
    return frames[:, index]


# --------------------------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisConfig:
    """Analysis parameters (see the module docstring)."""

    freqs_hz: tuple[float, ...] = DEFAULT_FREQS_HZ
    period_s: float = DEFAULT_PERIOD_S
    burst_ms: float = DEFAULT_BURST_MS
    threshold_ms: float = DEFAULT_THRESHOLD_MS
    reference: int | None = None  # voice index; None = voice with the most detections
    snr_db: float = 12.0  # minimum burst level above the envelope noise floor
    rel_db: float = 12.0  # maximum level below the voice's median burst level
    min_bursts: int = 5  # a voice with fewer detections is reported as absent
    expect: int | None = None  # number of voices that must be well detected in every run
    anchor: str = "both"  # burst numbering: "both", "start" or "end"
    split_gap_s: float = DEFAULT_SPLIT_GAP_S  # silence that separates two runs; <= 0: one run
    min_coverage: float = DEFAULT_MIN_COVERAGE  # fraction of the run's bursts


def analytic_template(freq_hz: float, sample_rate: int, burst_ms: float) -> np.ndarray:
    """Complex template: the generator's Hann window times exp(2j*pi*f*k/fs)."""
    n = max(2, round(burst_ms * 1e-3 * sample_rate))
    k = np.arange(n, dtype=np.float64)
    window = np.sin(np.pi * (k + 0.5) / n) ** 2
    return window * np.exp(2j * np.pi * freq_hz * k / sample_rate)


def matched_envelope(signal: np.ndarray, template: np.ndarray, block: int = 1 << 18) -> np.ndarray:
    """``|y[n]|`` with ``y[n] = sum_k signal[n + k] * conj(template[k])`` (overlap-save FFT).

    A burst equal to the template starting at sample ``n0`` gives a peak at ``y[n0]``.
    Memory use is bounded by the block size, so long recordings are fine.
    """
    n_sig, n_tpl = len(signal), len(template)
    size = 1 << math.ceil(math.log2(block + n_tpl - 1))
    tpl_spec = np.conj(np.fft.fft(template, size))
    out = np.empty(n_sig, dtype=np.float64)
    padded = np.concatenate([signal, np.zeros(n_tpl - 1)])
    for start in range(0, n_sig, block):
        stop = min(start + block, n_sig)
        segment = padded[start : stop + n_tpl - 1]
        y = np.fft.ifft(np.fft.fft(segment, size) * tpl_spec)
        out[start:stop] = np.abs(y[: stop - start])
    return out


def rising_edge_lag(template: np.ndarray) -> float:
    """Lag (in samples, negative) at which the template autocorrelation magnitude first reaches
    half of its peak. A detected half-rise time minus this lag is the burst start."""
    ac = np.abs(np.correlate(template, template, mode="full"))  # index n-1 is lag 0
    zero = len(template) - 1
    half = 0.5 * ac[zero]
    i = zero
    while i > 0 and ac[i - 1] >= half:
        i -= 1
    # crossing between i-1 (below half) and i (at or above half)
    lo, hi = ac[i - 1], ac[i]
    frac = (half - lo) / (hi - lo) if hi != lo else 0.0
    return (i - 1 + frac) - zero


@dataclass
class VoiceResult:
    """Detection result for one voice."""

    index: int
    freq_hz: float
    onsets_s: list[float] = field(default_factory=list)
    level_db: float | None = None  # median burst envelope level, dB relative to full scale
    snr_db: float | None = None  # median burst level above the noise floor
    present: bool = False  # at least min_bursts detections (drift and offsets: see runs)

    @property
    def count(self) -> int:
        return len(self.onsets_s)


@dataclass
class Candidates:
    """Raw burst candidates of one voice, before the level filters."""

    onsets_s: np.ndarray  # refined burst start times
    peaks: np.ndarray  # sample index of each envelope peak
    levels: np.ndarray  # envelope peak values
    noise: float  # envelope noise floor (median of the 1 ms frame maxima)
    norm: float  # envelope peak of a full-scale (amplitude 1) burst of this voice


def find_candidates(
    signal: np.ndarray, sample_rate: int, freq_hz: float, config: AnalysisConfig
) -> Candidates:
    """Matched filter, peak picking above the noise floor and rising-edge refinement."""
    template = analytic_template(freq_hz, sample_rate, config.burst_ms)
    env = matched_envelope(signal, template)
    norm = float(np.sum(np.abs(template) ** 2)) / 2
    empty = Candidates(np.empty(0), np.empty(0, dtype=int), np.empty(0), 0.0, norm)
    hop = max(1, round(sample_rate * 1e-3))  # 1 ms grid for peak picking
    n_frames = len(env) // hop
    if n_frames < 3:
        return empty
    frames = env[: n_frames * hop].reshape(n_frames, hop).max(axis=1)
    noise = float(np.median(frames)) + 1e-12
    half_win = max(1, round(0.4 * config.period_s / 1e-3))
    padded = np.pad(frames, half_win, mode="constant", constant_values=-1.0)
    local_max = np.lib.stride_tricks.sliding_window_view(padded, 2 * half_win + 1).max(axis=1)
    min_level = noise * 10 ** (config.snr_db / 20)
    picked = np.flatnonzero((frames >= local_max) & (frames > min_level))
    if len(picked):  # plateaus can yield neighbouring equal maxima: keep the first
        picked = picked[np.concatenate([[True], np.diff(picked) > half_win])]

    lag = rising_edge_lag(template)
    span = len(template)
    onsets, peaks, levels = [], [], []
    for frame in picked:
        lo = max(0, frame * hop - hop)
        hi = min(len(env), frame * hop + 2 * hop)
        peak_i = lo + int(np.argmax(env[lo:hi]))
        half = 0.5 * env[peak_i]
        i = peak_i
        limit = max(1, peak_i - 2 * span)
        while i > limit and env[i - 1] >= half:
            i -= 1
        below, above = env[i - 1], env[i]
        frac = (half - below) / (above - below) if above != below else 0.0
        onsets.append(((i - 1) + frac - lag) / sample_rate)
        peaks.append(peak_i)
        levels.append(float(env[peak_i]))
    return Candidates(
        np.asarray(onsets), np.asarray(peaks, dtype=int), np.asarray(levels), noise, norm
    )


def leakage_ratio(freq_src: float, freq_dst: float, sample_rate: int, burst_ms: float) -> float:
    """Envelope peak produced by a burst of ``freq_src`` in the matched filter of ``freq_dst``,
    relative to the peak it produces in its own filter."""
    n = max(2, round(burst_ms * 1e-3 * sample_rate))
    k = np.arange(n, dtype=np.float64)
    burst = np.sin(np.pi * (k + 0.5) / n) ** 2 * np.sin(2 * np.pi * freq_src * k / sample_rate)
    own = np.abs(np.correlate(burst, analytic_template(freq_src, sample_rate, burst_ms), "full"))
    other = np.abs(np.correlate(burst, analytic_template(freq_dst, sample_rate, burst_ms), "full"))
    return float(other.max() / own.max())


def select_bursts(
    candidates: list[Candidates],
    sample_rate: int,
    config: AnalysisConfig,
    leak_margin_db: float = 10.0,
) -> list[np.ndarray]:
    """Keep the real bursts of each voice.

    1. Leakage: a candidate of voice v is dropped when another voice u has a candidate within
       two burst lengths whose level, multiplied by the u->v leakage ratio (plus a margin),
       explains it. This removes ghosts of loud voices in the filters of absent voices.
    2. Level: candidates more than ``rel_db`` below the median level of the voice are dropped
       (weak echoes, harmonics, intermodulation).
    Returns a boolean mask per voice.
    """
    window = 2 * max(2, round(config.burst_ms * 1e-3 * sample_rate))
    margin = 10 ** (leak_margin_db / 20)
    masks = [np.ones(len(c.levels), dtype=bool) for c in candidates]
    for v, cv in enumerate(candidates):
        for u, cu in enumerate(candidates):
            if u == v or len(cu.peaks) == 0 or len(cv.peaks) == 0:
                continue
            # level seen in filter v / level seen in filter u, for a burst of voice u
            ratio = leakage_ratio(
                config.freqs_hz[u], config.freqs_hz[v], sample_rate, config.burst_ms
            )
            idx = np.clip(np.searchsorted(cu.peaks, cv.peaks), 0, len(cu.peaks) - 1)
            for j, peak in enumerate(cv.peaks):
                for cand in (idx[j] - 1, idx[j]):
                    if (
                        0 <= cand < len(cu.peaks)
                        and abs(cu.peaks[cand] - peak) <= window
                        and cv.levels[j] < cu.levels[cand] * ratio * margin
                    ):
                        masks[v][j] = False
    for c, mask in zip(candidates, masks, strict=True):
        if mask.any():
            typical = float(np.median(c.levels[mask]))
            mask &= c.levels >= typical * 10 ** (-config.rel_db / 20)
    return masks


def grid_indices(onsets: np.ndarray, period_s: float) -> tuple[np.ndarray, np.ndarray]:
    """Burst index of each onset, relative to the first detected burst (index 0).

    The grid phase is the median residual, so one off-grid first detection does not shift the
    whole grid. When two onsets round to the same index, the one closest to the grid is kept.
    Returns (kept onsets, their indices), sorted by time.
    """
    if len(onsets) == 0:
        return onsets, np.empty(0, dtype=int)
    t0 = onsets[0]
    raw = (onsets - t0) / period_s
    phase = float(np.median(raw - np.round(raw)))
    n = np.round(raw - phase).astype(int)
    residual = np.abs(raw - phase - n)
    order = np.lexsort((residual, n))  # by index, then closest to the grid first
    first_of_index = np.concatenate([[True], np.diff(n[order]) != 0])
    keep = np.sort(order[first_of_index])
    n = n[keep]
    return onsets[keep], n - n[0]


def fit_drift(
    onsets: np.ndarray, indices: np.ndarray, period_s: float
) -> tuple[float | None, float | None]:
    """Fit ``t = a + b * n`` (two passes, outliers > 3 x RMS removed). Returns (ppm, jitter ms).

    Must be applied to one run (one play of the clip): ``indices`` come from ``grid_indices``.
    """
    if len(onsets) < 3:
        return None, None
    n = indices.astype(np.float64)
    keep = np.ones(len(onsets), dtype=bool)
    slope = period_s
    residuals = np.zeros(len(onsets))
    for _ in range(2):
        if keep.sum() < 3 or np.ptp(n[keep]) == 0:
            return None, None
        slope, intercept = np.polyfit(n[keep], onsets[keep], 1)
        residuals = onsets - (intercept + slope * n)
        rms = float(np.sqrt(np.mean(residuals[keep] ** 2)))
        keep = np.abs(residuals) <= max(3 * rms, 0.5e-3)
    rms = float(np.sqrt(np.mean(residuals[keep] ** 2)))
    return (slope / period_s - 1.0) * 1e6, rms * 1e3


def split_runs(onset_lists: list[np.ndarray], gap_s: float) -> list[tuple[float, float]]:
    """Time spans of the runs (plays): the union of every voice's onsets is cut wherever no
    voice has a burst for more than ``gap_s``. ``gap_s <= 0`` keeps a single run."""
    union = np.sort(np.concatenate(onset_lists)) if onset_lists else np.empty(0)
    if len(union) == 0:
        return []
    if gap_s <= 0:
        return [(float(union[0]), float(union[-1]))]
    cuts = np.flatnonzero(np.diff(union) > gap_s)
    starts = np.concatenate([[0], cuts + 1])
    stops = np.concatenate([cuts, [len(union) - 1]])
    return [(float(union[a]), float(union[b])) for a, b in zip(starts, stops, strict=True)]


# --------------------------------------------------------------------------------------------
# Pairing and statistics
# --------------------------------------------------------------------------------------------


@dataclass
class OffsetStats:
    """Statistics of the offsets between two voices (B relative to A), in milliseconds."""

    voice_a: int
    voice_b: int
    count: int
    median_ms: float
    mean_ms: float
    std_ms: float
    p90_abs_ms: float
    max_abs_ms: float


def offset_stats(voice_a: int, voice_b: int, offsets_s: np.ndarray) -> OffsetStats:
    ms = offsets_s * 1e3
    absolute = np.abs(ms)
    return OffsetStats(
        voice_a=voice_a,
        voice_b=voice_b,
        count=len(ms),
        median_ms=float(np.median(ms)),
        mean_ms=float(np.mean(ms)),
        std_ms=float(np.std(ms)),
        p90_abs_ms=float(np.percentile(absolute, 90)),
        max_abs_ms=float(np.max(absolute)),
    )


@dataclass
class RunVoice:
    """One voice inside one run."""

    index: int
    freq_hz: float
    count: int
    first_s: float
    last_s: float
    span: int  # index of the last detected burst (first detected burst = 0)
    base: int | None  # absolute index of the first detected burst; None when ambiguous
    coverage: float  # count / (span of the run + 1)
    drift_ppm: float | None  # device clock vs recorder clock (>0: device plays slower)
    jitter_ms: float | None  # RMS residual of the onset line fit
    low_coverage: bool
    onsets_s: list[float] = field(default_factory=list)
    burst_index: list[int] = field(default_factory=list)  # absolute index, empty if ambiguous


@dataclass
class RunResult:
    """Analysis of one run (one play of the calibration clips)."""

    index: int
    start_s: float
    end_s: float
    anchor: str
    voices: list[RunVoice]  # voices present in this run
    absent: list[int]  # voice indices not present in this run
    reference: int | None
    pairs: list[OffsetStats]
    vs_reference: list[OffsetStats]
    overall_count: int
    overall_p90_ms: float | None
    overall_max_ms: float | None
    burst_spread_p90_ms: float | None  # p90 of (latest - earliest) per burst, all voices
    status: str  # PASS, FAIL, AMBIGUOUS, INCOMPLETE
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


@dataclass
class AnalysisResult:
    """Complete analysis output (JSON-serialisable through ``to_dict``)."""

    sample_rate: int
    duration_s: float
    config: AnalysisConfig
    voices: list[VoiceResult]  # detection over the whole recording
    runs: list[RunResult]
    status: str  # FAIL if a run fails, else the first non-PASS run status, NO_DATA, or PASS
    origin_s: float = 0.0  # position of the analysed signal in the file (--start)

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["config"]["freqs_hz"] = list(self.config.freqs_hz)
        out["passed"] = self.passed
        for run, src in zip(out["runs"], self.runs, strict=True):
            run["passed"] = src.passed
        return out


def _pair(a: RunVoice, b: RunVoice) -> np.ndarray:
    """Offsets t_b - t_a (seconds) of the bursts with the same absolute index."""
    ia = dict(zip(a.burst_index, a.onsets_s, strict=True))
    common = [(ia[k], t) for k, t in zip(b.burst_index, b.onsets_s, strict=True) if k in ia]
    return np.asarray([tb - ta for ta, tb in common])


def analyze_run(
    index: int,
    span_s: tuple[float, float],
    detected: list[np.ndarray],
    config: AnalysisConfig,
) -> RunResult:
    """Pair the voices of one run burst by burst, on absolute burst indices."""
    lo, hi = span_s[0] - 1e-6, span_s[1] + 1e-6
    period = config.period_s
    voices: list[RunVoice] = []
    absent: list[int] = []
    for v, onsets in enumerate(detected):
        inside = onsets[(onsets >= lo) & (onsets <= hi)]
        if len(inside) < config.min_bursts:
            absent.append(v)
            continue
        kept, n = grid_indices(inside, period)
        drift, jitter = fit_drift(kept, n, period)
        voices.append(
            RunVoice(
                index=v,
                freq_hz=config.freqs_hz[v],
                count=len(kept),
                first_s=float(kept[0]),
                last_s=float(kept[-1]),
                span=int(n[-1]),
                base=None,
                coverage=len(kept) / (int(n[-1]) + 1),
                drift_ppm=drift,
                jitter_ms=jitter,
                low_coverage=False,
                onsets_s=[float(t) for t in kept],
                burst_index=[int(k) for k in n],
            )
        )
    problems: list[str] = []
    warnings: list[str] = []

    # Coverage: a device that never played, or barely reached the microphone, must not let
    # the remaining voices pass on their own.
    max_span = max((rv.span for rv in voices), default=0)
    run_bursts = max_span + 1
    for rv in voices:
        rv.coverage = rv.count / run_bursts
        if rv.coverage < config.min_coverage:
            rv.low_coverage = True
            warnings.append(
                f"WARNING: voice {rv.index} detected on {rv.count}/{run_bursts} bursts "
                f"({rv.coverage:.0%} < {config.min_coverage:.0%}): device too quiet, "
                "masked or stopped; its drift/offsets are unreliable"
            )
    good = [rv for rv in voices if not rv.low_coverage]
    if len(good) < len(voices):
        problems.append(
            f"INCOMPLETE: poorly detected voice(s) {[v.index for v in voices if v.low_coverage]}"
            " (raise the volume, move the device closer, or re-record)"
        )
    if config.expect is not None and len(good) < config.expect:
        problems.append(
            f"INCOMPLETE: {len(good)} well-detected voice(s) {[rv.index for rv in good]}, "
            f"{config.expect} expected (--expect)"
        )

    # Burst anchoring: the bursts all look alike, so an offset is only known modulo the period
    # unless every voice's bursts are numbered from the same clip burst. "start": the first
    # detected burst of every voice is the same clip burst; "end": the last one is; "both"
    # (default): both must hold, i.e. every well-detected voice spans the same number of
    # bursts. A low-coverage voice that does not is left out of the pairing.
    good_spans = {rv.span for rv in good}
    if config.anchor == "both" and len(good_spans) > 1:
        detail = ", ".join(f"v{rv.index} spans {rv.span + 1} bursts" for rv in voices)
        problems.append(
            "AMBIGUOUS: the voices do not cover the same bursts (first/last bursts differ by a "
            f"whole number of periods): {detail}. Offsets may be off by k x "
            f"{period * 1e3:g} ms. Causes: a device started or ended a whole period late, "
            "a first/last burst was missed, a 'T past' or rejoin play (devices start mid-clip: "
            "use --anchor end), or a recording that misses the start or end of the clips."
        )
    for rv in voices:
        if config.anchor == "end":
            rv.base = max_span - rv.span
        elif config.anchor == "start" or (len(good_spans) == 1 and rv.span in good_spans):
            rv.base = 0
        elif not good_spans and len({v.span for v in voices}) == 1:
            rv.base = 0  # only low-coverage voices, but consistent
        else:
            if len(good_spans) <= 1:
                warnings.append(
                    f"WARNING: voice {rv.index} left out of the pairing: its first or last "
                    "burst was not detected, its burst numbering is unknown"
                )
            rv.burst_index = []
            continue
        rv.burst_index = [k + rv.base for k in rv.burst_index]
    if len(voices) < 2:
        problems.append("INCOMPLETE: fewer than two voices in this run, nothing to compare")
    paired = [rv for rv in voices if rv.burst_index]

    reference: int | None = None
    candidates = paired or voices
    if candidates:
        if config.reference is not None:
            if any(rv.index == config.reference for rv in candidates):
                reference = config.reference
            else:
                warnings.append(
                    f"WARNING: reference voice {config.reference} not usable in this run"
                )
        if reference is None:
            reference = max(candidates, key=lambda rv: (rv.count, -rv.index)).index

    pairs: list[OffsetStats] = []
    vs_reference: list[OffsetStats] = []
    pooled: list[np.ndarray] = []
    spreads: list[float] = []
    if len(paired) >= 2:
        for i, va in enumerate(paired):
            for vb in paired[i + 1 :]:
                offsets = _pair(va, vb)
                if len(offsets):
                    pairs.append(offset_stats(va.index, vb.index, offsets))
                    pooled.append(np.abs(offsets) * 1e3)
        ref = next(rv for rv in paired if rv.index == reference)
        for rv in paired:
            if rv.index != reference:
                offsets = _pair(ref, rv)
                if len(offsets):
                    vs_reference.append(offset_stats(ref.index, rv.index, offsets))
        by_burst: dict[int, list[float]] = {}
        for rv in paired:
            for k, t in zip(rv.burst_index, rv.onsets_s, strict=True):
                by_burst.setdefault(k, []).append(t)
        spreads = [(max(ts) - min(ts)) * 1e3 for ts in by_burst.values() if len(ts) >= 2]

    all_abs = np.concatenate(pooled) if pooled else np.empty(0)
    p90 = float(np.percentile(all_abs, 90)) if len(all_abs) else None
    if p90 is not None and p90 > config.threshold_ms:
        status = "FAIL"  # a failure on the voices present is a failure whatever else happened
    elif problems:
        status = problems[0].split(":", 1)[0]
    else:
        status = "PASS" if p90 is not None else "INCOMPLETE"
    return RunResult(
        index=index,
        start_s=span_s[0],
        end_s=span_s[1],
        anchor=config.anchor,
        voices=voices,
        absent=absent,
        reference=reference,
        pairs=pairs,
        vs_reference=vs_reference,
        overall_count=len(all_abs),
        overall_p90_ms=p90,
        overall_max_ms=float(np.max(all_abs)) if len(all_abs) else None,
        burst_spread_p90_ms=float(np.percentile(spreads, 90)) if spreads else None,
        status=status,
        problems=problems,
        warnings=warnings,
    )


def analyze(signal: np.ndarray, sample_rate: int, config: AnalysisConfig) -> AnalysisResult:
    """Run the full analysis on a mono float signal."""
    if config.anchor not in ("both", "start", "end"):
        raise ValueError(f"anchor must be both, start or end (got {config.anchor!r})")
    candidates = [find_candidates(signal, sample_rate, f, config) for f in config.freqs_hz]
    masks = select_bursts(candidates, sample_rate, config)
    voices: list[VoiceResult] = []
    detected: list[np.ndarray] = []
    for index, (freq, cand, mask) in enumerate(
        zip(config.freqs_hz, candidates, masks, strict=True)
    ):
        onsets = np.sort(cand.onsets_s[mask])
        detected.append(onsets)
        voice = VoiceResult(index=index, freq_hz=freq, onsets_s=[float(t) for t in onsets])
        if len(onsets):
            level = float(np.median(cand.levels[mask]))
            voice.level_db = 20 * math.log10(level / cand.norm + 1e-12)
            voice.snr_db = 20 * math.log10(level / cand.noise)
        voice.present = len(onsets) >= config.min_bursts
        voices.append(voice)

    present = [d for d, v in zip(detected, voices, strict=True) if v.present]
    spans = split_runs(present, config.split_gap_s)
    runs: list[RunResult] = []
    for span in spans:
        run = analyze_run(len(runs) + 1, span, detected, config)
        if run.voices:  # stray detections between plays do not make a run
            runs.append(run)
    if any(r.status == "FAIL" for r in runs):
        status = "FAIL"
    elif not any(len(r.voices) >= 2 for r in runs):
        status = "NO_DATA"
    else:
        status = next((r.status for r in runs if r.status != "PASS"), "PASS")
    return AnalysisResult(
        sample_rate=sample_rate,
        duration_s=len(signal) / sample_rate,
        config=config,
        voices=voices,
        runs=runs,
        status=status,
    )


# --------------------------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------------------------


def _fmt(value: float | None, spec: str = "+.1f") -> str:
    return "-" if value is None else format(value, spec)


def format_report(result: AnalysisResult) -> str:
    """Human-readable report."""
    cfg = result.config
    o = result.origin_s  # times are printed as positions in the file
    lines = [
        (
            f"Recording: {result.duration_s:.1f} s at {result.sample_rate} Hz, period "
            f"{cfg.period_s * 1e3:g} ms, burst {cfg.burst_ms:g} ms, "
            f"threshold {cfg.threshold_ms:g} ms, anchor {cfg.anchor}, "
            f"expect {cfg.expect if cfg.expect is not None else '-'}"
        ),
        "",
        "Voices (whole recording)",
        f"  {'voice':>5} {'freq Hz':>8} {'bursts':>6} {'level dB':>8} {'SNR dB':>7}  status",
    ]
    for v in result.voices:
        lines.append(
            f"  {v.index:>5} {v.freq_hz:>8g} {v.count:>6} {_fmt(v.level_db, '.1f'):>8} "
            f"{_fmt(v.snr_db, '.1f'):>7}  {'detected' if v.present else 'absent'}"
        )
    if cfg.expect is None:
        lines.append(
            "  note: pass --expect N (number of devices that played) so that a silent or "
            "missing device cannot pass unnoticed"
        )

    def table(title: str, rows: list[OffsetStats]) -> None:
        lines.extend(["", title])
        if not rows:
            lines.append("  (none)")
            return
        lines.append(
            f"  {'A':>3} {'B':>3} {'n':>4} {'median':>8} {'mean':>8} {'std':>6} "
            f"{'p90|d|':>7} {'max|d|':>7}   (ms, offset = t_B - t_A, >0: B late)"
        )
        for s in rows:
            lines.append(
                f"  {s.voice_a:>3} {s.voice_b:>3} {s.count:>4} {s.median_ms:>+8.1f} "
                f"{s.mean_ms:>+8.1f} {s.std_ms:>6.1f} {s.p90_abs_ms:>7.1f} {s.max_abs_ms:>7.1f}"
            )

    for run in result.runs:
        lines.extend(
            [
                "",
                (
                    f"=== Run {run.index}: {run.start_s + o:.2f} s - {run.end_s + o:.2f} s "
                    f"(alone: --start {max(0.0, run.start_s + o - 1):.0f} "
                    f"--end {run.end_s + o + 1:.0f})"
                ),
                (
                    f"  {'voice':>5} {'bursts':>6} {'cover':>6} {'first s':>8} {'last s':>8} "
                    f"{'1st idx':>7} {'drift ppm':>9} {'jitter ms':>9}  status"
                ),
            ]
        )
        for rv in run.voices:
            status = "reference" if rv.index == run.reference else "ok"
            if rv.low_coverage:
                status += ", LOW COVERAGE"
            lines.append(
                f"  {rv.index:>5} {rv.count:>6} {rv.coverage:>6.0%} {rv.first_s + o:>8.3f} "
                f"{rv.last_s + o:>8.3f} {_fmt(rv.base, 'd'):>7} {_fmt(rv.drift_ppm, '+.0f'):>9} "
                f"{_fmt(rv.jitter_ms, '.2f'):>9}  {status}"
            )
        if run.absent:
            lines.append(f"  absent in this run: voices {run.absent}")
        table(f"Offsets versus reference voice {run.reference}", run.vs_reference)
        table("All pairs", run.pairs)
        lines.append("")
        lines.extend(run.warnings)
        lines.extend(run.problems)
        if run.overall_p90_ms is not None:
            lines.append(
                f"Run {run.index}: {run.overall_count} pairwise offsets, p90 |offset| = "
                f"{run.overall_p90_ms:.1f} ms, max = {run.overall_max_ms:.1f} ms, "
                f"per-burst spread p90 = {_fmt(run.burst_spread_p90_ms, '.1f')} ms"
            )
            sign = "<=" if run.overall_p90_ms <= cfg.threshold_ms else ">"
            lines.append(
                f"RUN {run.index}: {run.status} (p90 {run.overall_p90_ms:.1f} ms {sign} "
                f"{cfg.threshold_ms:g} ms)"
            )
        else:
            lines.append(f"RUN {run.index}: {run.status}")

    lines.append("")
    if not result.runs:
        lines.append("RESULT: NO_DATA - fewer than two voices detected, nothing to compare")
    else:
        verdicts = ", ".join(f"run {r.index} {r.status}" for r in result.runs)
        lines.append(f"RESULT: {result.status} ({len(result.runs)} run(s): {verdicts})")
    return "\n".join(lines)


def exit_code(result: AnalysisResult) -> int:
    """0: every run PASS; 1: a run FAILs; 2: ambiguous, incomplete or no data."""
    if result.status == "PASS":
        return 0
    if any(r.status == "FAIL" for r in result.runs):
        return 1
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure playback offsets between devices from a microphone recording."
    )
    parser.add_argument("recording", type=Path, help="WAV file (mono or multichannel)")
    parser.add_argument(
        "--freqs",
        default=",".join(f"{f:g}" for f in DEFAULT_FREQS_HZ),
        help="comma-separated voice frequencies in Hz (voice index = position)",
    )
    parser.add_argument("--period", type=float, default=DEFAULT_PERIOD_S, help="burst period, s")
    parser.add_argument("--burst-ms", type=float, default=DEFAULT_BURST_MS)
    parser.add_argument(
        "--reference",
        type=int,
        default=None,
        help="reference voice index (default: voice with most bursts)",
    )
    parser.add_argument("--threshold-ms", type=float, default=DEFAULT_THRESHOLD_MS)
    parser.add_argument(
        "--expect",
        type=int,
        default=None,
        help="number of devices that played: a run with fewer well-detected voices is "
        "INCOMPLETE (exit 2)",
    )
    parser.add_argument(
        "--anchor",
        choices=("both", "start", "end"),
        default="both",
        help="burst numbering: 'both' (default) requires every voice to cover the same "
        "bursts; 'end' for 'T past' or rejoin plays (devices start mid-clip); 'start' when "
        "the recording stopped before the end of the clips",
    )
    parser.add_argument(
        "--split-gap",
        type=float,
        default=DEFAULT_SPLIT_GAP_S,
        help="split the recording into runs on silences longer than this (s); 0: one run",
    )
    parser.add_argument("--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE)
    parser.add_argument("--channel", default="mix", help="'mix' (default) or a channel index")
    parser.add_argument("--start", type=float, default=0.0, help="ignore audio before (s)")
    parser.add_argument("--end", type=float, default=None, help="ignore audio after (s)")
    parser.add_argument("--snr-db", type=float, default=12.0)
    parser.add_argument("--rel-db", type=float, default=12.0)
    parser.add_argument("--min-bursts", type=int, default=5)
    parser.add_argument(
        "--json",
        metavar="PATH",
        default=None,
        help="also write the full result as JSON ('-' for stdout only)",
    )
    args = parser.parse_args(argv)

    try:
        frames, rate = read_wav(args.recording)
        signal = to_mono(frames, args.channel)
        freqs = tuple(float(f) for f in args.freqs.split(",") if f.strip())
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    lo = max(0, round(args.start * rate))
    hi = len(signal) if args.end is None else min(len(signal), round(args.end * rate))
    signal = signal[lo:hi]
    config = AnalysisConfig(
        freqs_hz=freqs,
        period_s=args.period,
        burst_ms=args.burst_ms,
        threshold_ms=args.threshold_ms,
        reference=args.reference,
        snr_db=args.snr_db,
        rel_db=args.rel_db,
        min_bursts=args.min_bursts,
        expect=args.expect,
        anchor=args.anchor,
        split_gap_s=args.split_gap,
        min_coverage=args.min_coverage,
    )
    result = analyze(signal, rate, config)
    result.origin_s = lo / rate
    if args.json == "-":
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_report(result))
        if args.json:
            Path(args.json).write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return exit_code(result)


if __name__ == "__main__":
    sys.exit(main())
