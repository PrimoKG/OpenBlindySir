# Themed nights — delivery, 8 October 2026

[Français](2026-10-08-themed-nights.md).

Combined folder, genre, language, year, tag and universe filters now select actual
rounds, with a preview using the same matching engine. Shortcuts, browser-local
saved selections and transfer from library search prepare reusable nights.
Individual and bulk editing expose the new fields; sorting and pagination remain.
Unknown metadata is excluded from strict filters rather than guessed.
See [user workflow](../themed-nights.en.md).

Protocol is now 11, snapshot 9 and metadata exports version 3. Older snapshots
and JSON imports 1/2 migrate. Queries and choices are bounded; the preview is
host-only with Origin, role and epoch rechecks and search work limits. Confirmed
series titles containing a spaced hyphen are preserved for automatic scoring.
Theme settings cannot change during an active game.

## Local preparation and deployment

A real library of 232 cartoon themes and related files was reviewed: 211 enabled,
21 logically disabled, including eight exact copies and episodes, compilations,
excerpts, promotions or short files. Titles were cleaned, series linked and
answer variants added. Languages use explicit filename evidence; artist and year
were not invented. Artist was cleared to prevent an uploader becoming a scoring
reference. No music file was renamed, moved or edited.

The folder is an additive read-only mount. An empty mountpoint directory was
created in the existing music root because Docker cannot create a missing nested
mountpoint within a read-only parent. The catalogue now contains 300 tracks;
the next-game preparation selects 211 themes, title-only with 12-second clips.
The previous game remains finished; no new game started automatically.

A native private format-2 backup and checksums were verified before changes.
Server and Bridge were rebuilt and restarted. Post-restore checks confirm the
two player identities, 12 archives, scores, answers, browser cookies, access code,
Bridge configuration and HTTPS certificate are preserved. Earlier catalogue
entries remain. Archives are compared after schema validation to account for new
default fields. Anonymous access to the new preview remains refused. No music
files or private inventories are included in Git or Docker build contexts.

## Validation

- 1,190 distinct Python tests passed: 1,179 general and 11 integration tests,
  including restore, combined filters, catalogues, sources, privacy and FFmpeg.
  Two Unix/link permission checks are skipped on Windows.
- 53 web unit tests passed; type checking, build, Biome, Ruff, formatting,
  Pyright and schema generation were verified.
- Eight new FR/EN themed-night browser flows passed on Chromium/WebKit,
  with small desktop/mobile visual checks. Invalid year ranges remain local
  and do not trigger a search request.

Classification of an unfamiliar library requires verified metadata and host
corrections. Real-device acoustic checks remain necessary. This delivery is not
a signed public release and does not supersede the limitations of the
[previous audit](2026-10-08-autofix.en.md).
