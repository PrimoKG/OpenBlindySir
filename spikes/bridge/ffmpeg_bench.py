# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy>=1.26"]
# ///
"""FFmpeg bench for the Bridge pipeline (spec §10): ffprobe -> start point -> exact template.

For each selected track: open-time sandbox check, ffprobe (timeout 10 s), start point rule,
exact FFmpeg template (timeout 30 s) into a private temp dir, then verification of the
clip: magic bytes, exactly one AAC 48 kHz stereo stream, no video, no title/artist tag,
duration close to the requested one, moov before mdat. On the synthetic fixtures (linear
chirp), the real start position is recovered from the pitch to measure the seek error.

Usage:
    uv run spikes/bridge/ffmpeg_bench.py --fixtures [--ffmpeg PATH]          # all fixtures
    uv run spikes/bridge/ffmpeg_bench.py --catalog _out/catalog.json -n 50 --seed 1
    uv run spikes/bridge/ffmpeg_bench.py --root D:/Music -n 50 --seed 1

Never prints file names unless --verbose-paths.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge_common as bc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES_ROOT = os.path.join(HERE, "_fixtures", "library")
FIXTURES_MANIFEST = os.path.join(HERE, "_fixtures", "manifest.json")
DURATION_TOLERANCE_S = 0.25
FADE_TAIL_MAX_RATIO = 0.2


def fade_tail_ratio(ffmpeg: str, path: str) -> float | None:
    """RMS of the last 50 ms / RMS of the middle second. With the 1.5 s linear fade-out the
    tail is ~2 % of the level; ~1 means the clip ends abruptly. None if the middle is silent."""
    x = decode_mono(ffmpeg, path)
    rate = 48000
    if len(x) < 3 * rate:
        return None
    mid = x[len(x) // 2 - rate // 2: len(x) // 2 + rate // 2]
    tail = x[-int(0.05 * rate):]
    mid_rms = float(np.sqrt(np.mean(mid * mid)))
    if mid_rms < 1e-3:
        return None
    return float(np.sqrt(np.mean(tail * tail))) / mid_rms


def verify_clip(ffprobe: str, path: str, expected_duration: float, fmt: str,
                ffmpeg: str | None = None, strict_fade: bool = False) -> tuple[list[str], list[str], dict]:
    """Return (problems, warnings, info). A clip shorter than requested (source ends early,
    e.g. truncated file or estimated duration) is a warning, not a template violation.
    With ffmpeg given, the fade-out is checked (tail level): a problem on the constant-level
    synthetic chirps (strict_fade), a warning on real music (its level may vary)."""
    problems: list[str] = []
    warnings: list[str] = []
    with open(path, "rb") as fh:
        head = fh.read(12)
    if not bc.check_magic(head, fmt):
        problems.append("bad magic bytes")
    proc = bc.run_tool(bc.ffprobe_argv(ffprobe, path), bc.FFPROBE_TIMEOUT_S)
    info = bc.parse_probe(proc.stdout.decode("utf-8", "replace"))
    expected_codec = bc.OUTPUT_FORMATS[fmt]["codec_name"]
    if len(info.audio) != 1:
        problems.append(f"{len(info.audio)} audio streams")
    else:
        a = info.audio[0]
        if a.get("codec_name") != expected_codec:
            problems.append(f"codec {a.get('codec_name')}")
        if str(a.get("sample_rate")) != "48000":
            problems.append(f"rate {a.get('sample_rate')}")
        if a.get("channels") != 2:
            problems.append(f"channels {a.get('channels')}")
    if info.video:
        problems.append(f"{len(info.video)} video stream(s) (cover art leaked)")
    if info.other_streams:
        problems.append(f"{info.other_streams} other stream(s)")
    for key in ("title", "artist", "album"):
        if info.tag(key):
            problems.append(f"tag '{key}' present")
    if info.duration is None or info.duration > expected_duration + DURATION_TOLERANCE_S \
            or info.duration < 0.5 * expected_duration:
        problems.append(f"duration {info.duration} vs {expected_duration:.3f}")
    elif info.duration < expected_duration - DURATION_TOLERANCE_S:
        warnings.append(f"short clip {info.duration:.2f} s vs {expected_duration:.2f} s")
    moov = bc.moov_position(path) if fmt == "aac" else "n/a"
    if fmt == "aac" and moov != "start":
        problems.append(f"moov {moov}")
    residual = sorted(set(info.format_tags) | set(info.stream_tags))
    tail = fade_tail_ratio(ffmpeg, path) if ffmpeg else None
    if tail is not None and tail > FADE_TAIL_MAX_RATIO:
        (problems if strict_fade else warnings).append(f"no fade-out (tail/mid RMS {tail:.2f})")
    return problems, warnings, {"out_duration": info.duration, "moov": moov, "residual_tag_keys": residual,
                                "fade_tail_ratio": None if tail is None else round(tail, 3)}


def measure_seek_error(ffmpeg: str, path: str, start: float, f0: float, k: float) -> float | None:
    """Return (estimated source position - requested start) in ms, from the chirp pitch."""
    proc = subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", "file:" + path,
         "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
        capture_output=True, timeout=30, stdin=subprocess.DEVNULL,
    )
    x = np.frombuffer(proc.stdout, dtype=np.float32)
    rate = 48000.0
    lo, hi = int(0.5 * rate), int(3.5 * rate)
    if len(x) < hi:
        hi = len(x) - int(0.2 * rate)
    if hi - lo < int(0.5 * rate):
        return None
    seg = x[lo:hi].astype(np.float64)
    idx = np.nonzero((seg[:-1] < 0) & (seg[1:] >= 0))[0]
    if len(idx) < 20:
        return None
    # Sub-sample crossing times by linear interpolation.
    frac = -seg[idx] / (seg[idx + 1] - seg[idx])
    t = (lo + idx + frac) / rate
    periods = np.diff(t)
    mids = (t[1:] + t[:-1]) / 2
    freqs = 1.0 / periods
    slope, intercept = np.polyfit(mids, freqs, 1)
    if not (0.5 * k < slope < 1.5 * k):  # not our chirp (or broken decode)
        return None
    tc = 1.0
    f_at_tc = intercept + slope * tc
    source_pos = (f_at_tc - f0) / k
    return (source_pos - (start + tc)) * 1000.0


def decode_mono(ffmpeg: str, path: str, out_ss: float | None = None, out_t: float | None = None) -> np.ndarray:
    argv = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file",
            "-i", "file:" + path]
    if out_ss is not None:
        argv += ["-ss", f"{out_ss:.3f}"]  # output-side seek: decodes from the start, sample-exact
    if out_t is not None:
        argv += ["-t", f"{out_t:.3f}"]
    argv += ["-map", "0:a:0", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"]
    proc = subprocess.run(argv, capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
    return np.frombuffer(proc.stdout, dtype=np.float32).astype(np.float64)


def measure_seek_ref(ffmpeg: str, src: str, clip_path: str, start: float) -> float | None:
    """Seek error for ANY track (real music too): cross-correlate the clip with a reference
    decoded from the beginning of the source (output-side -ss). Returns ms or None."""
    rate = 48000
    ref_start = max(0.0, start - 1.0)
    ref = decode_mono(ffmpeg, src, out_ss=ref_start, out_t=4.5)
    clip = decode_mono(ffmpeg, clip_path)
    seg = clip[int(0.5 * rate):int(2.5 * rate)]
    if len(seg) < rate or len(ref) < len(seg) + rate // 10 or np.std(seg) < 1e-4:
        return None  # too short or silent: not measurable
    seg = seg - seg.mean()
    n = 1 << (len(ref) + len(seg)).bit_length()
    corr = np.fft.irfft(np.fft.rfft(ref, n) * np.conj(np.fft.rfft(seg, n)), n)
    valid = corr[: len(ref) - len(seg) + 1]
    lag = int(np.argmax(valid))
    window_energy = np.sqrt(np.convolve(ref * ref, np.ones(len(seg)), "valid"))[lag]
    score = valid[lag] / (np.linalg.norm(seg) * window_energy + 1e-12)
    if score < 0.5:
        return None  # no convincing match (e.g. noise-like content after lossy coding)
    expected = (start + 0.5 - ref_start) * rate
    return (lag - expected) / rate * 1000.0


def load_selection(args) -> tuple[str, dict[str, bc.Track], dict | None]:
    manifest = None
    if args.fixtures:
        root_real, tracks, _ = bc.scan_library(FIXTURES_ROOT)
        with open(args.manifest or FIXTURES_MANIFEST, encoding="utf-8") as fh:
            manifest = json.load(fh)
    elif args.catalog:
        root_real, tracks = bc.load_private_catalog(args.catalog)
    elif args.root:
        root_real, tracks, _ = bc.scan_library(args.root)
    else:
        raise SystemExit("give --fixtures, --catalog FILE or --root DIR")
    if args.manifest and manifest is None:
        with open(args.manifest, encoding="utf-8") as fh:
            manifest = json.load(fh)
    return root_real, tracks, manifest


def main() -> int:
    bc.setup_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--fixtures", action="store_true", help="scan the synthetic fixtures + manifest")
    src.add_argument("--catalog", help="local catalog from scan_bench.py --json-out")
    src.add_argument("--root", help="scan this root now")
    ap.add_argument("--manifest", help="fixtures manifest (expected outcomes + chirp)")
    ap.add_argument("-n", type=int, default=0, help="random sample size (0 = all)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--clip", type=float, default=30.0)
    ap.add_argument("--fraction", default="random", help="start_fraction, or 'random'")
    ap.add_argument("--format", choices=sorted(bc.OUTPUT_FORMATS), default="aac")
    ap.add_argument("--seek-ref", action="store_true",
                    help="measure seek error by cross-correlation with a reference decode (any track)")
    ap.add_argument("--hardened", action="store_true", help="add -format_whitelist (candidate hardening)")
    ap.add_argument("--no-duration-measure", action="store_true",
                    help="plain §10: trust ffprobe even when it estimated the duration from the bitrate")
    ap.add_argument("--ffmpeg")
    ap.add_argument("--ffprobe")
    ap.add_argument("--verbose-paths", action="store_true")
    ap.add_argument("--json-out", help="write per-job results (track_ids only, no names)")
    args = ap.parse_args()

    ffmpeg, ffprobe = bc.find_ffmpeg_pair(args.ffmpeg, args.ffprobe)
    version, encoders = bc.ffmpeg_info(ffmpeg)
    root_real, tracks, manifest = load_selection(args)
    expected_by_rel: dict[str, dict] = {}
    chirp = None
    if manifest:
        chirp = manifest.get("chirp")
        expected_by_rel = {e["fs_relpath"]: e for e in manifest["files"]}

    rng = random.Random(args.seed)
    ids = sorted(tracks)
    if args.n and args.n < len(ids):
        ids = rng.sample(ids, args.n)
    clip_req = args.clip

    print("=== ffmpeg_bench (spec §10) ===")
    print(f"ffmpeg  : {version}  | encoders: {sorted(encoders)}")
    print(f"tracks  : {len(ids)} of {len(tracks)} (seed {args.seed}), clip {clip_req} s, "
          f"format {args.format}, hardened={args.hardened}, cpu_count={os.cpu_count()}")
    golden_printed = False
    rows: list[dict] = []
    for track_id in ids:
        t = tracks[track_id]
        exp = expected_by_rel.get(t.fs_relpath.replace(os.sep, "/"))
        group = exp["format"] if exp else f"{t.ext}"
        frac = rng.random() if args.fraction == "random" else float(args.fraction)
        if args.fraction == "random" and exp and exp.get("start_fraction") is not None:
            frac = float(exp["start_fraction"])  # fixture that needs a given start (late start)
        frac, clip = bc.clamp_request(frac, clip_req)
        row: dict = {"track_id": track_id, "group": group, "ext": t.ext, "size": t.size,
                     "start_fraction": round(frac, 4), "expected": exp["expected"] if exp else None}
        work = tempfile.mkdtemp(prefix=bc.TEMP_PREFIX)
        t0 = time.perf_counter()
        try:
            real = bc.resolve_for_open(root_real, tracks, track_id)
            row["lookup_ms"] = (time.perf_counter() - t0) * 1000
            res = bc.prepare_clip(ffmpeg, ffprobe, real, frac, clip, work, args.format, args.hardened,
                                  measure_estimated=not args.no_duration_measure)
            info = res["info"]
            row["duration_estimated"] = info.duration_estimated
            if info.duration_probed is not None:
                row["duration_probed"] = round(info.duration_probed, 3)
            row.update(
                status="OK", codec_in=info.audio[0].get("codec_name"), format_in=info.format_name,
                track_duration=round(info.duration, 3), start=round(res["start"], 3),
                clip_duration=round(res["clip_duration"], 3), rule=res["rule"],
                probe_ms=res["probe_ms"], measure_ms=res["measure_ms"], encode_ms=res["encode_ms"],
                check_ms=res["verify_ms"], bytes=res["bytes"], reencoded=res["reencoded"],
                input_has_cover=bool(info.video), input_has_title=bool(info.tag("title")),
            )
            # Bridge-side cost: lookup + probe (incl. duration measure) + encode(s) + output check.
            row["prepare_ms"] = row["lookup_ms"] + row["probe_ms"] + row["encode_ms"] + row["check_ms"]
            if not golden_printed:
                print("golden argv: " + bc.golden_argv(res["argv"], real, res["out_path"]))
                golden_printed = True
            tv = time.perf_counter()
            problems, warnings, vinfo = verify_clip(ffprobe, res["out_path"], res["clip_duration"], args.format,
                                                    ffmpeg, strict_fade=bool(exp and exp.get("chirp")))
            row["verify_ms"] = (time.perf_counter() - tv) * 1000
            row.update(vinfo)
            if problems:
                row["status"] = bc.INVALID_OUTPUT
                row["problems"] = problems
            if warnings:
                row["warnings"] = warnings
            if chirp and exp and exp.get("chirp"):
                err = measure_seek_error(ffmpeg, res["out_path"], res["start"], chirp["f0"], chirp["k"])
                row["seek_err_ms"] = None if err is None else round(err, 1)
            if args.seek_ref:
                err = measure_seek_ref(ffmpeg, real, res["out_path"], res["start"])
                row["seek_ref_err_ms"] = None if err is None else round(err, 1)
        except bc.JobError as exc:
            row["status"] = exc.code
            row["reason"] = exc.reason
            if args.verbose_paths and exc.detail:
                row["detail"] = exc.detail.strip()[:300]
        finally:
            shutil.rmtree(work, ignore_errors=True)
        rows.append(row)
        line = (f"{track_id} {group:<18} {row['status']:<14} "
                f"probe {bc.fmt_ms(row.get('probe_ms')):>4} ms  encode {bc.fmt_ms(row.get('encode_ms')):>5} ms  "
                f"{row.get('bytes', 0):>7} B  start {row.get('start', '-')!s:>7} ({row.get('rule', '-')})")
        if row.get("duration_estimated"):
            line += (f"  EST-DUR {row.get('duration_probed', '?')} -> {row.get('track_duration', '?')} s"
                     f" (measure {bc.fmt_ms(row.get('measure_ms'))} ms)")
        if row.get("reencoded"):
            line += f"  REENC {row['clip_duration']} s"
        if "seek_err_ms" in row:
            line += f"  seek_err {row['seek_err_ms']} ms"
        if "seek_ref_err_ms" in row:
            line += f"  seek_ref {row['seek_ref_err_ms']} ms"
        if row.get("problems"):
            line += "  PROBLEMS: " + "; ".join(row["problems"])
        if row.get("warnings"):
            line += "  WARN: " + "; ".join(row["warnings"])
        if row.get("reason") and row["status"] != "OK":
            line += f"  ({row['reason']})"
        if args.verbose_paths:
            line += f"  <{t.relpath}>"
            if row.get("detail"):
                line += f"\n      ffmpeg: {row['detail']}"
        print(line)

    # ---------------------------------------------------------------- summary
    print("\n=== per input group (OK jobs) ===")
    print(f"{'group':<18} {'n':>3} {'probe p50/p95':>14} {'encode p50/p95':>15} "
          f"{'prepare p95':>11} {'verify p50':>10} {'KB/clip':>8} {'|seek err| max':>15}")
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["status"] == "OK":
            groups[r["group"]].append(r)
    for g in sorted(groups):
        rs = groups[g]
        pr = [r["probe_ms"] for r in rs]
        en = [r["encode_ms"] for r in rs]
        pp = [r["prepare_ms"] for r in rs]
        ve = [r["verify_ms"] for r in rs]
        se = [abs(r[key]) for r in rs for key in ("seek_err_ms", "seek_ref_err_ms")
              if r.get(key) is not None]
        print(f"{g:<18} {len(rs):>3} {bc.fmt_ms(bc.percentile(pr, 50)):>6}/{bc.fmt_ms(bc.percentile(pr, 95)):<7} "
              f"{bc.fmt_ms(bc.percentile(en, 50)):>7}/{bc.fmt_ms(bc.percentile(en, 95)):<7} "
              f"{bc.fmt_ms(bc.percentile(pp, 95)):>11} {bc.fmt_ms(bc.percentile(ve, 50)):>10} "
              f"{sum(r['bytes'] for r in rs) / len(rs) / 1024:>8.0f} "
              f"{(f'{max(se):.1f} ms' if se else '-'):>15}")
    print("\n=== per input group, ALL jobs (DECODE_ERROR rate: watch it on the real library) ===")
    print(f"{'group':<18} {'n':>4} {'OK':>4} {'DECODE_ERROR':>13} {'rate':>6} {'other failures':<28} "
          f"{'est. dur':>8} {'re-enc':>6}")
    all_groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        all_groups[r["group"]].append(r)
    for g in sorted(all_groups):
        rs = all_groups[g]
        n_ok = sum(r["status"] == "OK" for r in rs)
        n_dec = sum(r["status"] == bc.DECODE_ERROR for r in rs)
        others: dict[str, int] = defaultdict(int)
        for r in rs:
            if r["status"] not in ("OK", bc.DECODE_ERROR):
                others[r["status"]] += 1
        print(f"{g:<18} {len(rs):>4} {n_ok:>4} {n_dec:>13} {100 * n_dec / len(rs):>5.0f}% "
              f"{(', '.join(f'{k} {v}' for k, v in sorted(others.items())) or '-'):<28} "
              f"{sum(bool(r.get('duration_estimated')) for r in rs):>8} "
              f"{sum(bool(r.get('reencoded')) for r in rs):>6}")
    ok = [r for r in rows if r["status"] == "OK"]
    allp = [r["prepare_ms"] for r in ok]
    print(f"\nALL OK jobs: n={len(ok)}  prepare (lookup+probe+encode+output check) p50 {bc.fmt_ms(bc.percentile(allp, 50))} ms, "
          f"p95 {bc.fmt_ms(bc.percentile(allp, 95))} ms, max {bc.fmt_ms(max(allp) if allp else None)} ms")
    fails: dict[str, int] = defaultdict(int)
    for r in rows:
        if r["status"] != "OK":
            fails[r["status"]] += 1
    print("failures by code: " + (", ".join(f"{k} {v}" for k, v in sorted(fails.items())) or "none"))
    warned = [r for r in ok if r.get("warnings")]
    print(f"OK jobs with warnings (short clip / fade-out on real music): {len(warned)}; "
          f"re-encoded with the measured length: {sum(bool(r.get('reencoded')) for r in ok)}; "
          f"duration estimated by ffprobe then measured: {sum(bool(r.get('duration_estimated')) for r in rows)}")
    tails = [r["fade_tail_ratio"] for r in ok if r.get("fade_tail_ratio") is not None]
    print(f"fade-out tail/mid RMS: max {max(tails):.3f} over {len(tails)} clips" if tails
          else "fade-out tail/mid RMS: not measurable")
    residual = sorted({k for r in ok for k in r.get("residual_tag_keys", [])})
    print(f"residual tag keys in clips (not title/artist): {residual}")
    covers = sum(1 for r in ok if r.get("input_has_cover"))
    titled = sum(1 for r in ok if r.get("input_has_title"))
    print(f"inputs with cover art: {covers}, with a title tag: {titled}; "
          f"clips with video stream or title/artist: "
          f"{sum(1 for r in rows if any('video' in p or 'tag' in p for p in r.get('problems', [])))}")
    mismatches = []
    if manifest:
        for r in rows:
            exp = r.get("expected")
            if exp is None:
                continue
            if exp != r["status"]:
                mismatches.append(r)
        print(f"expectation mismatches vs manifest: {len(mismatches)}")
        for r in mismatches:
            print(f"  {r['track_id']} {r['group']}: expected {r['expected']}, got {r['status']}"
                  + (f" ({'; '.join(r.get('problems', []))})" if r.get("problems") else ""))
    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({"ffmpeg": version, "format": args.format, "hardened": args.hardened,
                       "duration_measure": not args.no_duration_measure, "rows": rows}, fh, indent=1)
        print(f"results: {os.path.abspath(args.json_out)}")
    leftovers = [d for d in os.listdir(tempfile.gettempdir()) if d.startswith(bc.TEMP_PREFIX)]
    print(f"temp dirs left behind ({bc.TEMP_PREFIX}*): {len(leftovers)}")
    return 1 if any(r["status"] == bc.INVALID_OUTPUT for r in rows) or mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
