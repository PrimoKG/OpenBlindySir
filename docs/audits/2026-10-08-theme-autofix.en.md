# Themed nights audit and fixes — 8 October 2026

[Français](2026-10-08-theme-autofix.md). This pass supplements the
[theme delivery](2026-10-08-themed-nights.en.md) and the
[earlier audit](2026-10-08-autofix.en.md).

## Reproduced problems and fixes

| Case | Observed effect | Fix |
|---|---|---|
| File-detected references | Search found a cached title or artist, but preview and selection excluded the track. | Shared metadata resolution for search, preview, pool and queued selection. Explicit corrections take priority; cleared references block fallback. Known references survive audio eviction. |
| Long labels | Metadata allowed 256 characters but filters allowed 128; choosing a suggested value could fail. | Common 256 Unicode character limit in HTTP, protocol, inputs and presets. Tests cover all four categories and emoji using two UTF-16 units. |
| Symbolic tags/search | Emoji-only tags normalized to an empty key and could match all tracks. | Symbolic keys remain distinct; symbol-only queries actually search for the symbol. |
| Non-Latin presets | Joining characters and emoji sequences accepted by the server were rejected during local restoration. | Aligned forbidden-control validation while retaining joining characters. Isolated surrogates remain rejected in the browser. |
| Incomplete years | Preparation sent invalid criteria and displayed a generic server error. | Local validation for integer four-digit years in order. No invalid request; specific FR/EN message and disabled saving. |
| Failed preview | A network error could block preparation until another filter changed. | Try again button retains criteria; cancellation and protection against stale responses remain active. |
| Genre/language sorting | Unclassified tracks could appear before known categories. | Unknowns sorted last in both directions. |
| Folder facets | Tags from other folders were offered despite a selected folder restriction. | Facets remain within the selected folder. |
| Docker test tool | Running without arguments used the installed session and could create players and change settings/scores. | Explicit mode required: `--profiles-only` validates without contacting the app; `--allow-test-session-mutation` is for a dedicated test installation. CI enables it explicitly on its demo stack. Temporary profile configuration uses private permissions. |

Worker snapshots also detach filter lists. Regression checks ensure role
revocation, phase change or session replacement during calculation reject the
private response and release the worker. Anonymous callers, ordinary players
and invalid origins remain denied.

## Compatibility and installed deployment

Protocol **12** updates server, Bridge and UI together, with regenerated types
and schema lock. Snapshot **9**, history **2** and metadata **3** remain unchanged.
Older states still load. Returning to protocol 11 requires its backup if newer
labels exceed 128 characters; see the [update guide](../themed-nights.en.md).

A private native format-2 backup and all checksums were verified before restart.
The corrected containers run on the LAN. Post-restoration comparison confirms
**300 tracks, 211 playable cartoon themes, two players and 12 archives**,
preserving scores, answers, cookies, shared access, metadata, settings, sources
and Bridge configuration. Read-only music mounts and certificate are unchanged;
HTTPS was verified against the local authority. No music file was moved or
modified. No private data enters Git or the pack.

During this pass, the previous Docker tool invocation did create four synthetic
seats and change the finished game settings. Checks confirmed unchanged scores,
answers and archives. The saved snapshot restored only the two real players and
their settings; primary and fallback snapshots were verified afterwards. Two
regressions prevent implicit invocation and any app contact in profiles-only
mode. Full gameplay tests use the isolated stack.

## Validation

- **1,196 distinct general Python tests passed**: the 1,194-test suite followed by
  two new Docker tool guard regressions (all five tests of that module rerun),
  including FFmpeg, persistence, permissions,
  imports, recovery and security. Two POSIX/symlink checks skipped on Windows.
- **11 server/Bridge integration tests passed** with synthetic files and isolated
  ports, for **1,207 distinct passing Python tests** in total.
- **55 web tests passed**; TypeScript, build, Biome, Ruff, formatting, Pyright and schema passed.
- **12 targeted browser scenarios passed**, Chromium and WebKit, FR and EN:
  combined themes, library transfer, network retry, long tags and invalid years.

Private, public and individually authenticated Bridge Compose profiles passed
without mutation. CI workflows also cover CLI/native installations and both browsers.
The first CI run found a POSIX-specific regression in temporary directory
protection: `0600` prevented directory traversal. The directory now uses `0700`,
the file `0600`, while Windows ACLs remain private. Checks verify owner readability
and exclusion of other users; a local unprivileged Linux run supplements Windows tests.

## Image security

Pinned local Grype scans verified immutable delivered images against database
**v6.1.10, built 7 October 2026 at 06:31:48 UTC**. An initial run used an older
local 5 October database; it was superseded by this scan using the newest
previously downloaded database. No inventory was transmitted and no volume mounted.

| Image / component | Critical | High | Medium | Low |
|---|---:|---:|---:|---:|
| Application | 0 | 55 | 50 | 10 |
| Bridge | 0 | 55 | 50 | 10 |
| Caddy | 0 | 8 | 14 | 8 |
| Compiled FFmpeg 9.0.2, verified source and owning image | 0 | 0 | 0 | 0 |

No high finding offers a fix in this database: 51 `wont-fix` and four `not-fixed`
per Python image, eight `unknown` for Caddy. They are not declared false positives
or resolved. The two previously documented Python medium findings suggest
Python 3.15/alpha outside the validated 3.12–3.14 range and remain open. No
Python/npm dependency changed in this pass. No FFmpeg match does not establish
the absence of vulnerabilities.

Verified images: application
`sha256:f7298b53656043fcebf3a53007f22b739adf8774d721f9052bab2f69560a292a`,
Bridge `sha256:1205454fd33a2babe93007bfb87a2d287d39adf96fcce9cc16efa5392e12b0f8`,
Caddy `sha256:b2877ff4fb23df45e83eb48e5dad0756b72b74468222f4cea6a1afc412506193`.

## Limits

Physical phones, acoustic playback and installation on a clean machine still
need manual validation. Unknown metadata is not invented. The production JS
bundle still exceeds 500 KiB; splitting it is a performance improvement without
a confirmed blocking regression in this pass. Base image findings still need
review; this unsigned local candidate does not establish unconditional public
release readiness. No inventory is sent to Docker Scout: scans only access
image exports, with no network, Docker socket, volumes or music files.

Private evidence: `.local/theme-autofix-20261008/`, `.local/theme-autofix-*.log`
and the private pre-restart backup.
