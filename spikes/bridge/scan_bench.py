# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Scan a library root per spec §11 and print statistics, never file names.

Usage:
    uv run spikes/bridge/scan_bench.py ROOT [--repeat 3] [--no-scan-realpath]
                                            [--json-out FILE] [--verbose-paths]

--json-out writes a LOCAL catalog (real paths, for ffmpeg_bench.py). It contains your file
names: keep it in spikes/bridge/_out/ (gitignored) and never share it.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge_common as bc  # noqa: E402


def main() -> int:
    bc.setup_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root")
    ap.add_argument("--repeat", type=int, default=1, help="scan N times (warm cache timings)")
    ap.add_argument("--no-scan-realpath", action="store_true",
                    help="skip the scan-time realpath confinement (to measure its cost)")
    ap.add_argument("--json-out", help="save the local catalog (contains real paths)")
    ap.add_argument("--verbose-paths", action="store_true", help="debug: print relpaths")
    args = ap.parse_args()

    times = []
    for _ in range(max(1, args.repeat)):
        root_real, tracks, st = bc.scan_library(args.root, check_realpath=not args.no_scan_realpath)
        times.append(st.elapsed_s)
    raw, gz, chash = bc.catalog_payload(tracks)

    print("=== scan_bench (spec §11) ===")
    print(f"files accepted     : {st.accepted}  (files seen {st.files_seen}, dirs {st.dirs})")
    print(f"total size         : {bc.human_bytes(st.total_bytes)}  ({st.total_bytes} B)")
    timing = ", ".join(f"{t:.3f}" for t in times)
    print(f"scan time          : {times[0]:.3f} s first"
          + (f", median {statistics.median(times):.3f} s over {len(times)} [{timing}]" if len(times) > 1 else ""))
    print(f"  of which realpath: {st.realpath_s:.3f} s (last run)"
          + ("  [disabled]" if args.no_scan_realpath else ""))
    print("per extension      : " + ", ".join(f"{e} {n}" for e, n in sorted(st.ext_hist.items())))
    print("skipped            : "
          f"symlinks {st.symlinks_skipped}, junctions {st.junctions_skipped}, "
          f"dotfiles {st.dotfiles_skipped}, hidden-attr {st.hidden_attr_skipped}, "
          f"system-attr {st.system_attr_skipped}, non-whitelisted {st.ext_skipped}, "
          f"other-type {st.other_type_skipped}, outside-root {st.outside_root_refused}, "
          f"errors {st.errors}")
    print(f"NFD->NFC normalized: {st.nfc_normalized}   NFC collisions dropped: {st.nfc_collisions}")
    print(f"other reparse pts  : {st.reparse_other} (kept, e.g. cloud placeholders)")
    print(f"empty files listed : {st.empty_files}")
    print(f"catalog JSON       : raw {bc.human_bytes(len(raw))} ({len(raw)} B), "
          f"gzip {bc.human_bytes(len(gz))} ({len(gz)} B), "
          f"{len(raw) / max(1, st.accepted):.0f} B/track raw")
    print(f"catalog_hash       : {chash}")
    if args.verbose_paths:
        for t in sorted(tracks.values(), key=lambda t: t.relpath):
            print(f"  {t.track_id}  {t.relpath}")
    if args.json_out:
        bc.save_private_catalog(args.json_out, root_real, tracks)
        print(f"local catalog saved (contains real paths, do not share): {os.path.abspath(args.json_out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
