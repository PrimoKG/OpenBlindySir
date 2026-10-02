#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy>=1.26"]
# ///
"""Dry run of the acoustic measurement without devices: decode the generated calibration
clips (AAC, as served) with ffmpeg, mix them with known offsets, gains, a crude room echo
and noise, and write a WAV that tools/sync_analyze.py should analyse back to those offsets.

    uv run spikes/audio-sync/make_fake_recording.py --offsets 0,23,-41,110 -o fake.wav
    (add --ffmpeg PATH or set FFMPEG when ffmpeg is not on PATH)
    uv run tools/sync_analyze.py fake.wav --reference 0 --expect 4
    (--runs 3 chains three plays separated by --gap seconds, like a real session)

Requires the server to have generated _generated/clips/calib_v*.m4a at least once.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RATE = 44100  # deliberately not 48 kHz, like many phone recorders


def decode(ffmpeg: str, path: Path) -> np.ndarray:
    cmd = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-f",
        "f32le",
        "-ac",
        "1",
        "-ar",
        str(RATE),
        "-",
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True, timeout=60).stdout
    return np.frombuffer(raw, dtype="<f4").astype(np.float64)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--offsets", default="0,23,-41,110", help="ms per voice, voice index = position"
    )
    parser.add_argument("--gains-db", default=None, help="dB per voice (default 0,-6,-12,-18,...)")
    parser.add_argument("--noise-db", type=float, default=-40.0, help="white noise level, dBFS RMS")
    parser.add_argument(
        "--echo", action="store_true", help="add two room reflections (7 and 19 ms)"
    )
    parser.add_argument("--runs", type=int, default=1, help="number of plays in the file")
    parser.add_argument("--gap", type=float, default=5.0, help="silence between plays, s")
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--ffmpeg", default=None, help="ffmpeg binary (else $FFMPEG, else PATH)")
    args = parser.parse_args()

    ffmpeg = args.ffmpeg or os.environ.get("FFMPEG") or shutil.which("ffmpeg")
    if not ffmpeg:
        print("error: ffmpeg not found", file=sys.stderr)
        return 2
    offsets = [float(x) for x in args.offsets.split(",")]
    gains = (
        [float(x) for x in args.gains_db.split(",")]
        if args.gains_db
        else [-6.0 * i for i in range(len(offsets))]
    )
    pad = round(0.5 * RATE)
    run_len = round((31.5 + args.gap) * RATE)
    mix = np.zeros(run_len * args.runs + pad)
    for voice, (offset_ms, gain_db) in enumerate(zip(offsets, gains, strict=True)):
        clip = decode(ffmpeg, HERE / "_generated" / "clips" / f"calib_v{voice}.m4a")
        for run in range(args.runs):
            start = pad + run * run_len + round(offset_ms * 1e-3 * RATE)
            mix[start : start + len(clip)] += clip * 10 ** (gain_db / 20)
    if args.echo:
        for delay_ms, g in ((7.0, 0.5), (19.0, 0.3)):
            d = round(delay_ms * 1e-3 * RATE)
            mix[d:] += g * mix[:-d].copy()
    mix += np.random.default_rng(1).normal(0.0, 10 ** (args.noise_db / 20), len(mix))
    mix /= max(1.0, float(np.max(np.abs(mix))) / 0.9)
    pcm = np.round(mix * 32767).astype("<i2")
    with wave.open(str(args.output), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    print(
        f"{args.output}: {len(offsets)} voices, offsets {offsets} ms, gains {gains} dB, "
        f"noise {args.noise_db} dBFS, echo={args.echo}, {RATE} Hz, {args.runs} run(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
