# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Sandbox probe for the Bridge (spec §11, gate G2: no file outside the root reachable).

Builds a temporary tree:
    <tmp>/root/      the library root given to the scanner
    <tmp>/outside/   files that must NEVER be listed nor opened
then creates escape attempts (symlinks, junction, swaps after scan, hard link, crafted
lookups, playlist files that make FFmpeg open other files, including (g2) an ffconcat
playlist reaching outside through a junction inside the root) and prints PASS/FAIL per case.
Known result: (g2) FAILS with the exact spec §10 template and passes with -format_whitelist.

Usage:
    uv run spikes/bridge/sandbox_probe.py [--ffmpeg PATH] [--ffprobe PATH] [--no-ffmpeg] [--keep]

Result legend: PASS (escape blocked), FAIL (escape possible: G2 broken), SKIP (cannot be set
up on this machine, reason given), INFO (known residual, not decidable by the Bridge).
Exit status 1 when at least one FAIL.
"""

from __future__ import annotations

import argparse
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge_common as bc  # noqa: E402

RESULTS: list[tuple[str, str, str]] = []


def record(case: str, verdict: str, detail: str) -> None:
    RESULTS.append((case, verdict, detail))
    print(f"[{verdict:<4}] {case:<46} {detail}")


def write_wav(path: str, freq: float, seconds: float = 10.0, rate: int = 8000) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frames = b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * freq * i / rate)))
        for i in range(int(seconds * rate))
    )
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)


def try_symlink(target: str, link: str, is_dir: bool = False) -> str | None:
    try:
        os.symlink(target, link, target_is_directory=is_dir)
        return None
    except OSError as exc:
        return f"symlink creation not permitted ({exc.__class__.__name__}, winerror={getattr(exc, 'winerror', None)})"


def make_junction(target: str, link: str) -> str | None:
    if not bc.IS_WINDOWS:
        return "junctions are Windows-only"
    try:
        import _winapi

        _winapi.CreateJunction(target, link)
        return None
    except Exception as exc:  # fall back to mklink
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True)
        if proc.returncode == 0:
            return None
        return f"junction creation failed ({exc.__class__.__name__})"


def listed_outside(root_real: str, tracks: dict[str, bc.Track]) -> list[str]:
    bad = []
    for t in tracks.values():
        real = os.path.realpath(os.path.join(root_real, t.fs_relpath))
        if not bc.is_within(real, root_real):
            bad.append(t.track_id)
    return bad


def expect_refused(case: str, root_real: str, tracks: dict, track_id: object) -> None:
    try:
        real = bc.resolve_for_open(root_real, tracks, track_id)
    except bc.JobError as exc:
        record(case, "PASS", f"refused {exc.code} ({exc.reason})")
        return
    where = "inside" if bc.is_within(real, root_real) else "OUTSIDE"
    record(case, "FAIL", f"lookup unexpectedly accepted (resolves {where} the root)")


def main() -> int:
    bc.setup_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ffmpeg", default=None)
    ap.add_argument("--ffprobe", default=None)
    ap.add_argument("--no-ffmpeg", action="store_true", help="skip the FFmpeg playlist cases")
    ap.add_argument("--keep", action="store_true", help="keep the temporary tree for inspection")
    args = ap.parse_args()

    base = tempfile.mkdtemp(prefix="obs-sandbox-probe-")
    root = os.path.join(base, "root")
    outside = os.path.join(base, "outside")
    print(f"=== sandbox_probe (spec §11, G2) — temp tree under {base}")
    print(f"platform: {sys.platform}, python {sys.version.split()[0]}")

    # Inside files.
    write_wav(os.path.join(root, "inside", "ok.wav"), 440)
    write_wav(os.path.join(root, "swapdir", "victim.wav"), 550)
    write_wav(os.path.join(root, "swapfile", "victim.wav"), 560)
    write_wav(os.path.join(root, "changed", "grows.wav"), 600)
    write_wav(os.path.join(root, ".hidden-dir", "hidden.wav"), 660)
    # Outside files.
    secret = os.path.join(outside, "secret.wav")
    write_wav(secret, 1234)
    write_wav(os.path.join(outside, "secret_dir", "secret2.wav"), 1300)
    write_wav(os.path.join(outside, "swap_target", "victim.wav"), 1400)  # same name as inside

    # (a) symlinks to outside (file and directory).
    sym_err = try_symlink(secret, os.path.join(root, "link_to_secret.wav"))
    sym_dir_err = try_symlink(os.path.join(outside, "secret_dir"), os.path.join(root, "link_dir"), True)
    # (b) junction to an outside directory.
    junc_err = make_junction(os.path.join(outside, "secret_dir"), os.path.join(root, "junction_dir"))
    # (d) hard link to an outside file (same volume, no privilege needed on NTFS).
    hard_err = None
    try:
        os.link(secret, os.path.join(root, "inside", "hardlink.wav"))
    except OSError as exc:
        hard_err = f"hard link failed ({exc.__class__.__name__})"

    root_real, tracks, st = bc.scan_library(root)
    by_rel = {t.relpath: t for t in tracks.values()}
    print(f"scan: {st.accepted} tracks, symlinks skipped {st.symlinks_skipped}, "
          f"junctions skipped {st.junctions_skipped}, dotfiles skipped {st.dotfiles_skipped}")

    # --- Scan-level cases -----------------------------------------------------------------
    bad = listed_outside(root_real, tracks)
    record("scan: nothing listed resolves outside root", "FAIL" if bad else "PASS",
           f"{len(tracks)} entries checked, {len(bad)} outside")
    if sym_err:
        record("(a) file symlink -> outside", "SKIP", sym_err)
        record("(a) dir symlink -> outside", "SKIP", sym_dir_err or "")
    else:
        ok = "link_to_secret.wav" not in by_rel and st.symlinks_skipped >= 1
        record("(a) file symlink -> outside", "PASS" if ok else "FAIL",
               f"not listed, symlinks_skipped={st.symlinks_skipped}")
        ok = not any(r.startswith("link_dir/") for r in by_rel)
        record("(a) dir symlink -> outside", "PASS" if ok and not sym_dir_err else "FAIL",
               "not traversed" if ok else "traversed!")
    if junc_err:
        record("(b) junction -> outside dir", "SKIP", junc_err)
    else:
        ok = not any(r.startswith("junction_dir/") for r in by_rel) and st.junctions_skipped >= 1
        record("(b) junction -> outside dir", "PASS" if ok else "FAIL",
               f"not traversed, junctions_skipped={st.junctions_skipped}, "
               f"os.walk would list {sum(len(f) for _d, _s, f in os.walk(os.path.join(root, 'junction_dir')))} file(s) there")
    ok = not any(r.startswith(".hidden-dir/") for r in by_rel)
    record("hidden directory content", "PASS" if ok else "FAIL", "not listed" if ok else "listed!")

    # --- Every listed entry opens and stays inside ----------------------------------------
    opened, escaped = 0, 0
    for t in tracks.values():
        try:
            real = bc.resolve_for_open(root_real, tracks, t.track_id)
            opened += 1
            escaped += not bc.is_within(real, root_real)
        except bc.JobError:
            pass
    record("open-check on every listed entry", "PASS" if escaped == 0 and opened == len(tracks) else "FAIL",
           f"{opened}/{len(tracks)} openable, {escaped} outside")

    # --- (c) swaps after scan (TOCTOU between scan and PREPARE) -----------------------------
    swap = by_rel.get("swapdir/victim.wav")
    if junc_err or swap is None:
        record("(c1) dir replaced by junction after scan", "SKIP", junc_err or "entry missing")
    else:
        os.rename(os.path.join(root, "swapdir"), os.path.join(base, "swapdir-moved"))
        make_junction(os.path.join(outside, "swap_target"), os.path.join(root, "swapdir"))
        # Make size/mtime identical so only the confinement check can catch it.
        target = os.path.join(outside, "swap_target", "victim.wav")
        os.utime(target, ns=(swap.mtime_ns, swap.mtime_ns))
        expect_refused("(c1) dir replaced by junction after scan", root_real, tracks, swap.track_id)
    swapf = by_rel.get("swapfile/victim.wav")
    if sym_err or swapf is None:
        record("(c2) file replaced by symlink after scan", "SKIP", sym_err or "entry missing")
    else:
        os.unlink(os.path.join(root, "swapfile", "victim.wav"))
        os.symlink(secret, os.path.join(root, "swapfile", "victim.wav"))
        expect_refused("(c2) file replaced by symlink after scan", root_real, tracks, swapf.track_id)
    grows = by_rel.get("changed/grows.wav")
    if grows:
        with open(os.path.join(root, "changed", "grows.wav"), "ab") as fh:
            fh.write(b"\0" * 1024)
        expect_refused("(c3) file modified after scan (size/mtime)", root_real, tracks, grows.track_id)

    # --- (d) hard link: indistinguishable from a regular file -------------------------------
    if hard_err:
        record("(d) hard link to outside file", "SKIP", hard_err)
    else:
        listed = "inside/hardlink.wav" in by_rel
        record("(d) hard link to outside file", "INFO",
               f"listed={listed}: a hard link IS a file of the root (same inode); needs local "
               "write access to the library -> accepted residual, document it")

    # --- (e) crafted lookups -----------------------------------------------------------------
    ok_id = by_rel["inside/ok.wav"].track_id
    try:
        bc.resolve_for_open(root_real, tracks, ok_id)
        record("(e) valid track_id (control)", "PASS", "opens")
    except bc.JobError as exc:
        record("(e) valid track_id (control)", "FAIL", exc.code)
    crafted = {
        "'..'": "..",
        "'../outside/secret.wav'": "../outside/secret.wav",
        "absolute path of outside file": secret,
        "absolute path of inside file": os.path.join(root, "inside", "ok.wav"),
        "relpath instead of id": "inside/ok.wav",
        "id of '../outside/secret.wav'": bc.make_track_id("../outside/secret.wav"),
        "unknown well-formed id": "t_0000000000000000",
        "upper-case valid id": ok_id.upper(),
        "valid id + trailing space": ok_id + " ",
        "valid id + '/..'": ok_id + "/..",
        "empty string": "",
        "None": None,
        "integer": 42,
        "list": [ok_id],
    }
    for label, value in crafted.items():
        expect_refused(f"(e) lookup {label}", root_real, tracks, value)

    # --- (f) root configured through a junction ----------------------------------------------
    if junc_err:
        record("(f) root given via a junction", "SKIP", junc_err)
    else:
        alias = os.path.join(base, "root-alias")
        make_junction(root, alias)
        r2, t2, _ = bc.scan_library(alias)
        same = sorted(t2) == sorted(bc.scan_library(root)[1])
        record("(f) root given via a junction", "PASS" if same and r2 == root_real else "FAIL",
               "resolved to the real root, same catalog" if same else "catalog differs")

    # --- (g) FFmpeg: playlist files that reference other files -----------------------------
    if args.no_ffmpeg:
        record("(g) ffmpeg playlist cases", "SKIP", "--no-ffmpeg")
    else:
        ffmpeg, ffprobe = bc.find_ffmpeg_pair(args.ffmpeg, args.ffprobe)
        playlists = {
            "HLS playlist as .mp3, absolute ref": (
                "evil-hls-abs.mp3",
                f"#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10.0,\n{secret}\n#EXT-X-ENDLIST\n"),
            "HLS playlist as .mp3, file: ref": (
                "evil-hls-fileproto.mp3",
                f"#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10.0,\nfile:{secret}\n#EXT-X-ENDLIST\n"),
            "HLS playlist as .mp3, ../ ref": (
                "evil-hls-rel.mp3",
                "#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10.0,\n../../outside/secret.wav\n#EXT-X-ENDLIST\n"),
            "ffconcat as .mp3, ../ ref": (
                "evil-concat.mp3", "ffconcat version 1.0\nfile '../../outside/secret.wav'\n"),
        }
        for name, content in playlists.values():
            with open(os.path.join(root, "playlists", name) if os.path.isdir(os.path.join(root, "playlists"))
                      else (os.makedirs(os.path.join(root, "playlists")) or os.path.join(root, "playlists", name)),
                      "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
        root_real, tracks, _ = bc.scan_library(root)
        by_rel = {t.relpath: t for t in tracks.values()}
        for label, (name, _content) in playlists.items():
            t = by_rel[f"playlists/{name}"]
            real = bc.resolve_for_open(root_real, tracks, t.track_id)  # passes: it IS inside
            for hardened in (False, True):
                work = tempfile.mkdtemp(prefix=bc.TEMP_PREFIX)
                variant = "hardened -format_whitelist" if hardened else "exact spec template"
                try:
                    res = bc.prepare_clip(ffmpeg, ffprobe, real, 0.5, 30.0, work, hardened=hardened)
                    record(f"(g) {label} [{variant}]", "FAIL",
                           f"ffmpeg produced {res['bytes']} B of audio read OUTSIDE the root "
                           f"(probe format={res['info'].format_name})")
                except bc.JobError as exc:
                    # Temp paths only here, so the FFmpeg reason can be shown (shortened).
                    why = next((ln.strip() for ln in exc.detail.splitlines() if ln.strip()), "")
                    why = why.replace(base, "<tmp>")[:110]
                    record(f"(g) {label} [{variant}]", "PASS",
                           f"refused {exc.code}; ffmpeg says: {why}")
                finally:
                    shutil.rmtree(work, ignore_errors=True)

        # (g2) The "safe" relative reference: a junction INSIDE the root (ignored by the scan,
        # so nothing is listed through it) plus a fake .mp3 that is an ffconcat playlist naming
        # 'jcat/long_secret.wav'. No '..', not absolute: the concat demuxer's safe mode accepts
        # it, -protocol_whitelist file does not stop it, and the junction is followed by the OS.
        # The outside file is 60 s long so the clip also passes the Bridge's output-duration
        # check: nothing downstream would notice. Expected with the exact §10 template: FAIL
        # (G2 criterion 2 not met); with -format_whitelist: PASS.
        if junc_err:
            record("(g2) ffconcat through an inner junction", "SKIP", junc_err)
        else:
            outside_long = os.path.join(base, "outside_long")
            write_wav(os.path.join(outside_long, "long_secret.wav"), 1500, seconds=60.0)
            make_junction(outside_long, os.path.join(root, "jcat"))
            concat_cases = {
                "with duration directive": (
                    "escape-concat.mp3", "ffconcat version 1.0\nfile jcat/long_secret.wav\nduration 60\n"),
                "without duration directive": (
                    "escape-concat-nodur.mp3", "ffconcat version 1.0\nfile jcat/long_secret.wav\n"),
            }
            for name, content in concat_cases.values():
                with open(os.path.join(root, name), "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(content)
            root_real, tracks, st2 = bc.scan_library(root)
            by_rel = {t.relpath: t for t in tracks.values()}
            listed_via_junction = [r for r in by_rel if r.startswith("jcat/")]
            print(f"(g2) scan: junctions skipped {st2.junctions_skipped}, entries under the junction "
                  f"listed: {len(listed_via_junction)}, playlists listed: "
                  f"{sum(n in by_rel for n, _c in concat_cases.values())}/{len(concat_cases)}")
            for label, (name, _content) in concat_cases.items():
                real = bc.resolve_for_open(root_real, tracks, by_rel[name].track_id)  # inside: passes
                for hardened in (False, True):
                    work = tempfile.mkdtemp(prefix=bc.TEMP_PREFIX)
                    variant = "hardened -format_whitelist" if hardened else "exact spec template"
                    case = f"(g2) ffconcat via inner junction, {label} [{variant}]"
                    try:
                        # prepare_clip includes the Bridge's output check: reaching here means
                        # the real Bridge would upload this clip.
                        res = bc.prepare_clip(ffmpeg, ffprobe, real, 0.5, 30.0, work, hardened=hardened)
                        record(case, "FAIL",
                               f"{res['bytes']} B clip ({res['out_duration']} s) of a file OUTSIDE the "
                               f"root, accepted by the output check (probe format={res['info'].format_name})")
                    except bc.JobError as exc:
                        why = next((ln.strip() for ln in exc.detail.splitlines() if ln.strip()), exc.reason)
                        why = why.replace(base, "<tmp>")[:110]
                        record(case, "PASS", f"refused {exc.code}; {why}")
                    finally:
                        shutil.rmtree(work, ignore_errors=True)

    # --- Cleanup (never descends into links) -------------------------------------------------
    still_there = os.path.isfile(secret) and os.path.isfile(os.path.join(outside, "secret_dir", "secret2.wav"))
    if args.keep:
        print(f"kept: {base}")
    else:
        bc.safe_rmtree(base)
    counts = {v: sum(1 for r in RESULTS if r[1] == v) for v in ("PASS", "FAIL", "SKIP", "INFO")}
    print(f"=== summary: {counts}  (outside files intact before cleanup: {still_there})")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
