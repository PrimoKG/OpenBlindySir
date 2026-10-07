# Plan delivery and verification — October 7, 2026

All eight implementation lots are delivered and the LAN stack has restarted. A01–A07 from the supplementary audit have regression coverage. Video findings informed scoring, finale and library changes. [Detailed French report](2026-10-07-implementation.md).

## Delivered behavior

1. Captured drafts configured for host judgement remain pending, with recognition evidence. Unknown numeric guesses become ambiguous. One input matches configured fields with a threshold per criterion and exact year. Hosts see the frozen scoring reference; later metadata changes and explicit regrading remain visible. Manual overrides are preserved.
2. Obsolete audio work is cancelled, stale results ignored and prefetch failures separated from current playback. Concurrent or closed connection attempts cannot create zombie sockets. Leaving a game releases audio, requests, subscriptions and listeners. A permanently closed context can be recreated on a user gesture. Audio tests remain reachable during the finale.
3. Desktop layouts place musical context, grading and ranking side by side when space permits. Each browser measures its own scoring batch and advances after the last visible player receives confirmed points. Manual pause preserves the preference. Ranking displays at most five rows; animation transforms and WebKit rounding no longer collapse or overfill it. Controls retain 44 px targets.
4. Private preparation and public presentation have separate states. Podium confirmation first offers to finish pending awards, with explicit publication of current scores still possible. Round activity resets on navigation. Finals without awards use suitable completion wording. Successful joins clear invitation fragments.
5. Guided reveal/listen/award/ranking/next sequence, optional fast pace, criteria/gains/corrections, rank changes and ties. Local sound/motion settings respect system reduced motion. Revision-checked undo restores values of the last confirmed correction and keeps the history.
6. Tracks lead the library; source management is advanced. Quality and selected-source filters prepare correction work. Inline editors, adaptive pages, tags, linked works, disabled tracks and private 15-second midpoint previews. Inheritance and explicit clearing differ; edit conflicts preserve drafts. Reimportable JSON chunks ≤1 MiB and ZIP packs ≤8 MiB/10,000 rows, with explicit continuation for large collections. ZIP import extracts no files and bounds decompressed content, allowing Stored/Deflate only.
7. Caddy proxy rebuilt with zlib 1.3.2-r1. Exact images, compiled FFmpeg and npm lock components scanned locally without inventory transmission. Precompiled Linux/amd64 candidate pack, image manifest, SHA-256 checks, verified loading, Windows assistant, private backups, update and explicit rollback. Guided LAN CA trust, never silently installed. PowerShell 5.1/7 checksum and French text compatibility fixed.
8. FR/EN dictionaries and documentation updated, engine/HTTP/browser/integration regressions executed, and protocol 10/snapshot 8 migration verified. No official public release or signed native installer was created.

## Evidence

- **1,138 Python tests passed**, two Windows skips (POSIX permissions, symlink creation); **11 separate integrations passed**, including real games, reconnects, Bridge failures, removed files and stopping during a round.
- **52 Web tests passed**. TypeScript, build, Biome, Ruff/format, Pyright with the project interpreter, and generated schema/types checks passed.
- **100 Chromium scenarios passed** in the full run; real games, QR/cookies/transfer, library and recognition were rerun after later changes, followed by the affected final ranking cases.
- Final cross-browser selection: **16 passed** (9 Chromium, 7 WebKit), **2 WebKit audio skips** because Windows WebKit has no `AudioContext`. WebKit library checks layout and media error/retry behavior; actual playback is covered in Chromium. No acoustic or physical iPhone validation is claimed.
- Responsive phone/short desktop/large-list, FR/EN, keyboard and zoom checks. Dedicated three-person ranking regression during animated position changes.
- Candidate pack actually generated and reloaded after checksums and image identity verification. PowerShell scripts parsed, launcher executed, assistant backup executed with private ACL. .NET checksum calculation avoids child-process module-loading failures.

Initial failures led to fixes for accessible editor labels, target size, duplicate Results headings, frozen-reference fixtures, animation measurement and fractional WebKit overflow. Audio constructor failures in Windows WebKit were confirmed from traces and recorded as an environment limitation.

Initial GitHub macOS jobs also exposed an older preinstalled FFmpeg and a missing Vorbis encoder in the standard formula. Apple Silicon/Intel CI now builds the same SHA-256-verified FFmpeg 9.0.2 source as Linux, including fixture encoders and portable checksum verification. The security minimum and affected tests remain intact. Remote matrices cover both macOS architectures with Python 3.12–3.14 and native archives; they do not replace physical-device checks.

## Deployment and retained state

All three services run the exact scanned images and verified Web build. HTTPS validated with the existing local CA; served HTML/JS/CSS match the build. Anonymous host-tool access is denied. Mounts, configuration, secrets, identities, cookies, shared access, answers, score journal, metadata and **12 archives** were retained. Snapshot **7 → 8** verified; monotonic clocks are rebased and archives gain an empty optional `cleared_fields` property.

Bridge rescanning changed the catalog from 69 to **68 files**: one stale entry has no physical file in the retained mounts, including Unicode-normalized comparison. No musical file was modified. Persisted metadata and historical results remain intact. Private backups/proofs stay in ignored `.local`; temporary test stacks were stopped and the preexisting development stack was preserved. Rollback to protocol 9 requires its format-7 backup, never a format-8 snapshot.

## Local security scan

Pinned Grype scanner, DB **v6.1.10 built October 7 at 06:31:48 UTC**. Scans use `--network none`; only prior advisory DB retrieval uses networking. No inventory, music, volume or secret was uploaded to Docker Scout or another scanning service.

| Image | Critical | High | Medium | Low | Negligible |
| --- | ---: | ---: | ---: | ---: | ---: |
| Server | 0 | 55 | 50 | 10 | 46 |
| Bridge | 0 | 55 | 50 | 10 | 46 |
| Caddy proxy | 0 | 8 | 14 | 8 | 0 |

These are package/advisory matches, not proven exploitation paths; shared images have overlapping findings. zlib update removed High `CVE-2026-85091`; no zlib matches remain. The FFmpeg 9.0.2 supplement, bound to the exact image and bundled source hash, has no matches in this DB.

Offline npm lock scans cover **32 production components** and **100 development components**, with no advisory matches in this DB. No connected `npm audit` inventory upload was used. Neither this nor the FFmpeg result proves the absence of unknown vulnerabilities.

Remaining High findings do not list compatible fixed versions in this DB. Two Medium Python findings list fixes in another branch: `CVE-2025-15367` (3.15.0a6) and `CVE-2026-12345` (3.15.0). Production uses **3.13.16** and the project requires `<3.15`; those listed versions cannot be directly applied as branch updates. Findings remain open, without arbitrary false-positive classification. Metadata import rejects Bzip2/LZMA. See the [official Python 3.13.16 release](https://www.python.org/downloads/release/python-31316/) for the runtime version; local evidence establishes the reported matches.

Exact image identities are listed in the French report and the pack manifest.

## Public-release reservations

No new role bypass was demonstrated by these checks; this is not an exhaustive pentest. **Official public release remains conditional** on High finding triage, physical Safari/iPhone/Android interruption and recovery tests, and manual assistant validation on a clean installation. Destructive rollback and cross-installation update were not exercised end to end on live data. Their integrity, volume/image identity checks and prerequisite backup do not replace that test.

The pack is an **unsigned local candidate**, tested for Linux/amd64. Other architectures, signatures and native installers remain distribution steps. Checksums establish integrity, not author identity when shipped with the download. No global PowerShell execution-policy change or silent CA installation is requested.
