# Video workflow fixes — 10 October 2026

[Français and detailed F01–F15 mapping](2026-10-10-video-fixes.md)

The delivery addresses preparation, automatic scoring and the host's finale
workflow observed in the 9 October recording.

- The Bridge reads title, artist, album, year and featuring locally before play,
  with two concurrent probes, a five-second per-file limit and a size/mtime cache.
  Explicit corrections and cleared fields take precedence. Ready-only selection
  excludes tracks lacking references for the requested criteria.
- Normalised Indel similarity accepts “validé” against “validée” at 90% (92.3%
  similarity), but not at 95%. Short names and years retain exact matching rules.
- Recognised drafts show proposed points. The host explicitly accepts them.
- **Save and recalculate this round** updates references and automatic decisions;
  **Save without recalculating scores** preserves scores. The editor closes after
  server acknowledgement. Manual changes are protected per criterion; manually
  entered totals and legacy whole-answer overrides stay protected.
- Missing-reference criteria can be excluded for everyone in the round, after
  confirmation, and restored later. Revision checks prevent stale changes.
- Two players fit in side-by-side desktop cards without an inner scrollbar.
  Scoring controls precede explanations. Next-player navigation follows the active
  card; automatic scrolling clearly reports its paused state.
- Private correction and public presentation are explicitly separated. The final
  publication recap links to outstanding rounds. Audio testing remains accessible.

## Actual browser validation

Computer Use ran against a real isolated server and demo Bridge, using separate
host/French and player/English browser sessions. The supported in-app browser
resolved the previous Windows automation blockage without weakening security.

The checked journey included preparation, missing-reference preflight, two rounds,
submitted and captured answers, reference editing and recalculation, accepting a
two-point proposal, collective exclusions, live scores, re-presenting an earlier
round without double-counting, a complete tied podium, a new game and cookie resume.
The final score was three points each. A 390 × 844 viewport checked mobile layout.

![English podium from the synthetic test](assets/2026-10-10-player-podium-en.png)

## Compatibility and limits

Protocol **14**, snapshot **11**, history **3**, software **0.5.0.dev0**. Update all
components together and back up stopped volumes. Older images require restoring
their compatible pre-upgrade backup.

Untagged tracks still require host-confirmed references or an import. Embedded tags
may be wrong; reading them does not certify their accuracy. Filenames never become
automatic answers. No external metadata lookup or private-media upload is involved.
Excluding criteria preserves manually entered totals, which the host should review.

Browser audio tests verify decoding/scheduling and recovery controls, not physical
speaker output. Physical iOS/Android checks after screen lock and Bluetooth output
changes remain required before claiming universal device support.

## Validation results

1,213 Python tests passed (two Windows-specific skips), plus 11 integration
scenarios. All 55 web unit tests, 117 UI scenarios and five real browser game
journeys passed on installed Chrome. Ruff, Pyright, Biome, TypeScript, protocol
schema generation and the production build passed. A Linux Docker smoke game
completed two synthetic AAC rounds using non-root, read-only containers.

A UI check caught a 28 px secondary target; it is now 44 px. Full games retain
their normal three-minute test allowance. The build still reports its existing
500 kB JavaScript chunk warning (approximately 159 kB compressed).

## Verified deployment

Stopped-volume private backup: `.local/backup-repair-20261010-014434`.
Previous images retained as `before-repair-20261010`. App, Bridge and proxy were
recreated; app/proxy healthy, Bridge online. TLS validated against the existing
local CA. Served HTML, JavaScript and CSS match the tested local build.

Snapshot migration from 10 to 11 verified. Four players, 15 archives, 300 tracks,
scores, answers, manual metadata, cookies, access, configuration and mounts were
preserved. New embedded tags may enrich the catalog without replacing host edits.
The session remains on final results.

Running images:

- `app`: `sha256:5d543519a83e0e5e6ad62b8759798c8c235ce62b60d7690158ff63312f3c4655`
- `bridge`: `sha256:7ad31ac1c79bd4e5fc3727a45d337dab8be8fc651d62d2d19bddbf862263a083`
- `caddy`: `sha256:b2877ff4fb23df45e83eb48e5dad0756b72b74468222f4cea6a1afc412506193`
