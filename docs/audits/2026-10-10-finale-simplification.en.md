# Simpler finale and filename references — October 10, 2026

## Result

Answer cards now focus on the answer. Pending cards offer Found/Missed for one
criterion, All correct/All incorrect for several. Partial credit is available
under Score each item. Reviewed cards display their score and collapse controls
under Edit points. Details contains automatic evidence, timing and manual totals.
Advanced scrolling controls appear only when the list actually overflows.

The persistent bar offers one contextual primary action. Duplicate shortcuts,
pace settings and secondary commands leave the main flow. Finale options keeps
stop, fast pacing and early publication. All rounds groups search and private
round selection. Finish-scoring navigation first targets the selected round’s
incomplete answer. Shared replay and live standings remain directly available.

Without musical references, the server locally extracts title, artist and
featuring from structured filenames such as
`Travis Scott - FE!N (feat. Playboi Carti).mp3`. Publication labels, extensions
and track numbers are removed; Live/Remix versions and internal title hyphens
remain. A bare title supplies no invented artist. Generic identifiers and UUIDs
are rejected. Explicit corrections, imports and tags retain priority; explicit
clears are respected. Album/year are never guessed and files are not modified.
Preparation, ready-only selection, automatic scoring and reveal use the resolved
references. Existing played rounds keep frozen references: intentionally update
them through correction and Save and regrade.

## Verification

- Python: 1,238 passed, 2 skipped, 11 integration tests outside the selection.
- Frontend: 55 unit tests; TypeScript/Vite build passed; Biome, Ruff and Pyright
  clean; generated protocol contract current (14).
- Chrome: 127 interface tests and 5 real server/Bridge game scenarios passed.
  Six new FR/EN cases at 390, 1,093 and 1,280 px cover the two choices, single
  primary action and collapsed details. Both full 1,280/320 px games passed on
  rerun after fixing a test that accidentally closed an already open disclosure
  (`open=""`).
- Computer Use: isolated real stack, three synthetic untagged WAVs, separate
  FR host/EN player sessions, two rounds, scoring and publication through results.
  All three filenames supply title/artist during preparation. Locked answers and
  captured drafts remain distinct; confirmations reach the player live. Actual
  manual viewport: 786 × 884 px. IAB viewport override had no effect; other sizes
  were checked with automated Chrome tests.
- Candidate Linux image: two-round game with three simulated connections, AAC,
  verified HTTPS/WSS certificates, non-root read-only containers.
- Deployment: private stopped-volume backup and rollback images, followed by
  restart. Real session preserved: 4 players, 16 archives and 300 tracks. Scores,
  metadata, cookies, access, configuration, mounts and TLS authority retained.
  Served bundle matches the local build; Bridge connected.

Verified app image:
`sha256:0508f3fd4f075e63cffb3c5acba59f9856afc9758a8afe5a282cafa665857d3c`.
Bridge and Caddy retain the preceding delivery’s images.

## Demonstration screenshots

![FR host scoring: two choices, collapsed details, one primary action](assets/2026-10-10-finale-friendly-fr.png)

![Shared finale for the EN player](assets/2026-10-10-finale-player-en.png)

## Limits

Ambiguous filenames cannot guarantee correct references: the host should correct
reversed artist/title order or inaccurate filenames. Physical-phone audio and
suspension still require device checks. Automated checks cannot guarantee zero
bugs. This pass does not repeat the image CVE audit; the
[preceding security findings](2026-10-10-conversation-check.en.md) still apply.
This local candidate is not a signed public release announcement.
