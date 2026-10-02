#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy>=1.26"]
# ///
"""Calibration clip generator for the OpenBlindySir acoustic sync measurement.

Each device taking part in a measurement plays its own *voice*: a clip made of short
Hann-windowed tone bursts, one burst every ``period`` seconds, at a frequency specific to
that voice. A single microphone records every device at once, and
``tools/sync_analyze.py`` separates the voices by frequency and measures their offsets.

Clip layout (all values exact, in samples, at the chosen sample rate)::

    burst n starts at  lead_in + n * period   (n = 0, 1, ...)
    burst length       burst_ms (default 10 ms), window w[k] = sin^2(pi * (k + 0.5) / L)
    burst content      amplitude * w[k] * sin(2 * pi * freq * k / fs), same on every channel

With the defaults (48 kHz, lead-in 1.0 s, period 0.5 s) every onset falls on an integer
sample (48000 + 24000 n), so the onsets in the generated WAV are sample-accurate. Encoding
to AAC or Opus may shift the whole clip by the encoder delay if the decoder does not honour
the container's priming information; that shift is the same for every voice of a given
format/decoder pair and is measured separately (decoder offset).

Default voice frequencies are 1400, 1800, 2200, 2600, 3000 and 3400 Hz: 400 Hz apart, and
no 2nd or 3rd harmonic of a voice lands closer than 200 Hz to another voice, so speaker
distortion does not create ghost bursts in a neighbouring voice.

Keep ``DEFAULT_FREQS_HZ``, ``DEFAULT_PERIOD_S`` and ``DEFAULT_BURST_MS`` identical in
``tools/sync_analyze.py``.

Usage::

    uv run tools/calibration_clip.py --voice 0 -o calib_v0.wav
    uv run tools/calibration_clip.py --voice 2 -o calib_v2.m4a --ffmpeg /path/to/ffmpeg
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DEFAULT_FREQS_HZ: tuple[float, ...] = (1400.0, 1800.0, 2200.0, 2600.0, 3000.0, 3400.0)
DEFAULT_PERIOD_S = 0.5
DEFAULT_BURST_MS = 10.0
DEFAULT_LEAD_IN_S = 1.0
DEFAULT_DURATION_S = 30.0
DEFAULT_SAMPLE_RATE = 48000
DEFAULT_AMPLITUDE = 0.8


@dataclass(frozen=True)
class CalibrationSpec:
    """Parameters of one calibration voice."""

    freq_hz: float
    sample_rate: int = DEFAULT_SAMPLE_RATE
    duration_s: float = DEFAULT_DURATION_S
    period_s: float = DEFAULT_PERIOD_S
    burst_ms: float = DEFAULT_BURST_MS
    lead_in_s: float = DEFAULT_LEAD_IN_S
    amplitude: float = DEFAULT_AMPLITUDE

    @property
    def burst_samples(self) -> int:
        return max(2, round(self.burst_ms * 1e-3 * self.sample_rate))

    def onset_samples(self) -> list[int]:
        """Start sample of every burst that fits entirely in the clip."""
        total = round(self.duration_s * self.sample_rate)
        onsets: list[int] = []
        n = 0
        while True:
            start = round((self.lead_in_s + n * self.period_s) * self.sample_rate)
            if start + self.burst_samples > total:
                return onsets
            onsets.append(start)
            n += 1


def hann_burst(freq_hz: float, sample_rate: int, burst_samples: int) -> np.ndarray:
    """One Hann-windowed sine burst (float64, peak <= 1)."""
    k = np.arange(burst_samples, dtype=np.float64)
    window = np.sin(np.pi * (k + 0.5) / burst_samples) ** 2
    return window * np.sin(2.0 * np.pi * freq_hz * k / sample_rate)


def render(
    spec: CalibrationSpec, delay_s: float = 0.0, length_s: float | None = None
) -> np.ndarray:
    """Render the mono calibration signal of one voice.

    ``delay_s`` shifts every burst (may be fractional in samples: the burst is then
    synthesised at the exact fractional position), ``length_s`` overrides the output length.
    Used by the generator (delay 0) and by tests that need voices at known offsets.
    """
    fs = spec.sample_rate
    total = round((length_s if length_s is not None else spec.duration_s) * fs)
    out = np.zeros(total, dtype=np.float64)
    n_burst = spec.burst_samples
    k = np.arange(n_burst, dtype=np.float64)
    for onset in spec.onset_samples():
        exact = onset + delay_s * fs
        start = int(np.floor(exact))
        frac = exact - start
        t = k - frac  # sample positions relative to the exact onset
        window = np.where(
            (t >= -0.5) & (t < n_burst - 0.5), np.sin(np.pi * (t + 0.5) / n_burst) ** 2, 0.0
        )
        burst = spec.amplitude * window * np.sin(2.0 * np.pi * spec.freq_hz * t / fs)
        lo, hi = max(start, 0), min(start + n_burst, total)
        if lo < hi:
            out[lo:hi] += burst[lo - start : hi - start]
    return out


def write_wav(path: Path, signal: np.ndarray, sample_rate: int, channels: int = 2) -> None:
    """Write a 16-bit PCM WAV (signal is mono float in [-1, 1], duplicated on each channel)."""
    pcm = np.clip(np.round(signal * 32767.0), -32768, 32767).astype("<i2")
    frames = np.repeat(pcm[:, None], channels, axis=1) if channels > 1 else pcm[:, None]
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(frames.tobytes())


def find_tool(explicit: str | None, env_var: str, name: str) -> str:
    """Resolve an executable: explicit option, then environment variable, then PATH."""
    for candidate in (explicit, os.environ.get(env_var)):
        if candidate:
            return candidate
    found = shutil.which(name)
    if found is None:
        raise FileNotFoundError(f"{name} not found: pass --{name} PATH or set {env_var}")
    return found


def encode_aac(ffmpeg: str, wav_path: Path, out_path: Path) -> None:
    """Encode to AAC-LC 128 kbps 48 kHz stereo .m4a with the spec section 10 flags (no fade)."""
    cmd = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-threads",
        "1",
        "-protocol_whitelist",
        "file",
        "-i",
        "file:" + str(wav_path.resolve()),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-y",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, timeout=60)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--voice", type=int, default=0, help="voice index (default 0)")
    parser.add_argument(
        "--freqs",
        default=",".join(f"{f:g}" for f in DEFAULT_FREQS_HZ),
        help="comma-separated voice frequencies in Hz",
    )
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION_S)
    parser.add_argument("--period", type=float, default=DEFAULT_PERIOD_S)
    parser.add_argument("--burst-ms", type=float, default=DEFAULT_BURST_MS)
    parser.add_argument("--lead-in", type=float, default=DEFAULT_LEAD_IN_S)
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    parser.add_argument(
        "-o", "--output", type=Path, required=True, help="output .wav, or .m4a (AAC, needs ffmpeg)"
    )
    parser.add_argument("--ffmpeg", default=None, help="ffmpeg binary (else $FFMPEG, else PATH)")
    args = parser.parse_args(argv)

    freqs = [float(f) for f in args.freqs.split(",") if f.strip()]
    if not 0 <= args.voice < len(freqs):
        parser.error(f"--voice must be in [0, {len(freqs) - 1}]")
    spec = CalibrationSpec(
        freq_hz=freqs[args.voice],
        sample_rate=args.sample_rate,
        duration_s=args.duration,
        period_s=args.period,
        burst_ms=args.burst_ms,
        lead_in_s=args.lead_in,
    )
    signal = render(spec)
    out: Path = args.output
    if out.suffix.lower() == ".wav":
        write_wav(out, signal, spec.sample_rate)
    elif out.suffix.lower() == ".m4a":
        ffmpeg = find_tool(args.ffmpeg, "FFMPEG", "ffmpeg")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "calib.wav"
            write_wav(src, signal, spec.sample_rate)
            encode_aac(ffmpeg, src, out)
    else:
        parser.error("output must end in .wav or .m4a")
    print(f"{out}: voice {args.voice}, {spec.freq_hz:g} Hz, {len(spec.onset_samples())} bursts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
