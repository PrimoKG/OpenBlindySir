# Conversation requirements check — 10 October 2026

[Français](2026-10-10-conversation-check.md).

This pass reconciles the requests with implemented behavior and test evidence. It
complements the [fifteen latest video fixes](2026-10-10-video-fixes.en.md). Historical
reports retain their original versions and counts; they are not current release notes.

## Gaps corrected in this pass

- The offline pack generator required protocol 13 while the application uses 14.
  It now checks each image against the actual protocol constant and includes
  compatibility in its manifest. Four tests cover current, older, newer and malformed versions.
- The themed-night guides still advertised protocol 12/snapshot 9; corrected to 14/11.
- At 1280 × 720, library filters displaced the tracks. Search and sorting remain
  visible, while all detailed filters and theme shortcuts live in a collapsible
  panel with an active count. Controls use horizontal space and pagination no
  longer overlays tracks.
- Clear filters previously reset only theme criteria. It now also resets source,
  folder, format, availability, activation, quality and selected-source restriction.
  Sorting is preserved.
- The pack now includes both user guides and the current reports.
- Computer Use reproduced a freeze after saving metadata: the editor unmounted
  before clearing its parent's busy flag, blocking filters, activation and close.
  Cleanup now releases the flag. Two FR/EN regressions and the actual save → filter
  → disable → enable → clear → close workflow verify the fix.

## Coverage matrix

Covered means implemented and exercised by identified scenarios, not guaranteed
defect-free on every device. Earlier Computer Use checks from the same day are
explicitly attributed to the video-fixes report rather than claimed as new runs.

| Request | Status and evidence |
| --- | --- |
| Shared live finale | Covered: reveal, collective replay, awards, ranking changes and podium; French host/English player Computer Use game and engine/browser scenarios. |
| Friendly, exciting scoring | Covered: guided actions, point proposals first, collapsible diagnostics, fast pace and local audio/animation preferences. Enjoyment and suspense still need real-party feedback. |
| Laptop width and mobile layouts | Covered: responsive columns, reachable submission and readable answer cards; UI checks from 320 to 1920 px and laptop formats. Library visually checked at 1280 × 720. |
| Direct private listening | Covered independently of metadata editing, with a separate collective replay action; HTTP/audio/UI tests. |
| Missing-awards filter wording | Covered in French and English dictionaries and final review. |
| Revisit the last rounds | Covered: private selection differs from public presentation; tests prevent duplicate award waves; Computer Use revisits round 2 → 1. |
| Stop game and restart/end-session menu | Covered by a real Chrome immediate-finish scenario and Computer Use restart. |
| Adaptive scoring scroll | Covered: per-browser measurement, advance after the last visible reviewed player, manual pause and next player; multiple viewport tests. Two players are no longer squeezed into a thin scroll strip. |
| Ranking with at most five visible players | Covered: five-row cap, fewer on short screens, own-position action and tied-rank tests. |
| QR asks only for nickname | Covered against the real server in Chrome. Invitation links remain private session access links. |
| Browser cookie resume | Covered, including secure production cookies and persistence/restart tests. |
| Shared recovery code and host rotation | Covered by server tests; existing-seat recovery requires host approval to prevent impersonation. Approved device transfer exercised in real Chrome. |
| Enable/disable tracks | Covered without deleting files, with filters and batch operations. |
| Inline library metadata editor | Covered directly below the selected track; the finale uses a separate save/recalculate dialog. |
| Tags, genre, language, era and Linked to | Covered: structured metadata, combined filters, sorting and batch edits; source/folder/format/quality filters retained. |
| Pagination and two columns of ten | Covered when space permits; single column and smaller pages on smaller screens. UI and visual checks. |
| Private 15-second midpoint preview | Covered: measured midpoint, short-track bounds and no consumption; HTTP regression and real Chrome game scenario. |
| Cartoon theme night | Read-only check of deployed data: **211 enabled Génériques tracks with titles**, in a 300-track catalogue. Theme shortcut and transfer to next-game settings tested. No music file move needed in this pass. |
| Pop, rap, 2012, French and English | Covered by combinable filters/shortcuts, provided metadata is populated. Missing language, year or genre is not guessed. |
| Metadata reading and corrections | Covered: local embedded tags, caching/imports, explicit overrides, inherit/replace/clear and conflict handling. Embedded tags may still be factually incorrect. |
| Optional automatic scoring in one field | Covered: independent configured criteria, flexible order/spaces/accents, per-criterion points and preserved host corrections. |
| Exact user example | `Sapéscomme Ja m ais Maitre Gims 2015 ft niska   pilule bleue` is an explicit passing regression for title/artist/album/year in `server/tests/game/test_auto_scoring.py`. |
| Percentage threshold | Covered: default 90%, configurable per scoring policy; years and very short references remain exact. “validé”/“validée” passes at 90%, fails at 95%. |
| Drafts, missing references and recalculation | Covered: explicit proposal acceptance, ready-track checks, controlled collective exclusion, recalculation preserving manually changed criteria. See the fifteen video regressions. |
| Test/recover audio during finale | Covered: accessible test, user-gesture recovery, closed-context recreation and download retry; FR/EN audio tests and actual Computer Use gesture. Physical listening remains unverified. |
| Browser-local FR/EN switch | Covered: persistence, no input loss or audio interruption, both dictionaries and mixed-language host/player checks. |
| LAN HTTPS warnings | Local-CA approach retained with explicit client trust and bilingual instructions. TLS verified against that CA without bypassing verification. Unconfigured clients will still see browser warnings. |
| Local security audit | Application tests and exact-image/FFmpeg analysis, without Docker Scout inventory upload. Remaining dependency findings are stated below. |
| Easier installation | Prebuilt Docker pack, hashes/image identities, Windows assistant, start/stop, backup, update and rollback. Pack regenerated after generator fix. Docker remains required. |
| Signed native installer / official public release | **Not delivered**: future distribution work. This local pack is unsigned and this audit creates no official public release. |
| FR/EN documentation | Updated user/install/theme guides and bilingual report, compatibility 14/11/3; historical journals remain dated records. |
| Correct running container and preserved data | Image identity, served assets, health, TLS, volumes and data compared after restart; delivery details below. |

## Validation of this pass

- 1,217 Python tests passed, two skipped; all 11 separately executed integration
  tests passed. 55 web unit tests, 121 final UI scenarios and five real-server
  Chrome games passed. The five games precede the last editor fix; all 121 UI
  scenarios follow it.
- Actual Computer Use at 1280 × 720: FR then EN library, preview, edit/save,
  filter, disable/re-enable, clear and close. [Synthetic screenshot](assets/2026-10-10-library-1280-fr.png).
  Mobile dimensions in this pass are automated; physical phone listening is not claimed.
- Candidate Linux images: two rounds, three simulated players, AAC and complete
  results; repeated through verified HTTPS/WSS with the corrected proxy.
  Both private and public Caddy configurations validated.
- Ruff, Pyright, Biome, TypeScript, protocol generation and build passed.
  Six Docker-context and distribution-pack tests passed after adding Go lock files.

### Deployed delivery

Protocol 14, snapshot 11, history 3. Verified Docker identities:

| Service | Image SHA-256 |
| --- | --- |
| Application | `2c14aac3ae5ec3ea55d5b58682b7137125c1a9e8565b499649e92cf1e3dfe992` |
| Bridge | `7ad31ac1c79bd4e5fc3727a45d337dab8be8fc651d62d2d19bddbf862263a083` |
| Caddy | `ef592848af939a06c37c0afb18f34f3747046ffcdaaa2d6e940583b772ac66e3` |

Containers restarted after private backup at
`.local/backup-conversation-20261010-023039`; rollback tags retained.
Comparison confirms four players, 15 archives, 300 tracks, scores, metadata,
cookies, access, configuration and mounts preserved. Bridge connected, TLS
verified and served HTML/JS/CSS identical to the tested build.

Local pack `.local/offline-pack-20261010-checked` regenerated with these images.
The PowerShell loader verified SHA-256 checksums, loaded images and confirmed
their identities. It did not start another session or modify active volumes.

## Security and publication limits

Only the public vulnerability database is downloaded. No volumes, passwords or
music catalogue are sent to an analysis service. A package finding is not proof
of exploitability; lack of a fix is not proof of safety.

The new scan also found 18 Go/x/net advisories in the official proxy image.
Rebuilding Caddy 2.11.7 with Go 1.26.9 and x/net 0.60.0 removes those matches
from the final scan. Sources, toolchain and dependencies are pinned; the shipped
proxy reports `v2.11.7-openblindysir.1`. Exact-image scans use the Grype database
built on October 9, 2026, without inventory upload.

| Image | Critical | High | Medium | Low | Negligible |
| --- | ---: | ---: | ---: | ---: | ---: |
| Application | 0 | 55 | 50 | 10 | 46 |
| Bridge | 0 | 55 | 50 | 10 | 46 |
| Corrected Caddy | 0 | 8 | 14 | 8 | 0 |

Counts represent package/advisory matches, not unique exploitable vulnerabilities.
For each Python image, 54 high findings are marked `wont-fix`, one `not-fixed`.
The two medium Python advisories marked fixed only list preliminary 3.15 releases;
the runtime was not forcibly migrated to an unstable version. The proxy's eight
high findings concern libcrypto/libssl packages, with unknown fix status. They
remain open; compiling Caddy without CGO does not establish whole-image safety.
Separately scanned FFmpeg 9.0.2, with verified source/version, has no matches in
this database. [Reproducible scan summary](2026-10-10-image-scan.json).

Physical iOS/Android checks after screen lock and Bluetooth output changes remain
necessary. Browser resizing does not replace them. The Windows assistant is not a
signed native installer. The JavaScript bundle still exceeds the 500 kB minified
warning threshold. This pass is not a general security certification or a claim
of universal device compatibility.
