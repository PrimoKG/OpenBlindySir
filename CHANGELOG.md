# Changelog

All notable changes to OpenBlindySir are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While
the version is 0.x, the API and protocol may change between minor versions.

## [Unreleased]

- 2026-10-10: protocol 14 / snapshot 11 / history 3. Background local tag discovery
  includes album, year and featuring before play; opt-in ready-only selection.
- Per-criterion manual protections during regrading, explicit missing-criterion
  neutralisation, draft score proposals and calibrated Indel similarity (matcher 2).
- Compact reference editor with save-and-regrade, two-player desktop cards,
  relative next-player navigation, clearer private/public round context, actionable
  incomplete-publication recap and audio-test feedback. FR/EN guides updated.

### V0.5 — development, 0.5.0.dev0

- Continuous server-driven rounds (2-second default), pause/resume intermissions,
  manual pace option and final-only scoring; compact host tools and tabbed modals.
- Search/sort/paginate the complete catalogue in a persistent modal; playing-host
  preflight browsing, explicit consumed/reserved/cancelled states and reserve reset.
- Weighted semantic title/artist/custom judgements, manual override, unchecked
  review navigation, absent-only zero batch, revision guards and correction reasons.
- Session-wide metadata corrections, immutable historical values, team-first podium,
  private replay capability hints/errors and readable responsive controls.
- Protocol 6 (6..6), snapshot 5 with formats 1–4 migration; history remains format 2.
- Docker launcher preserves local sources.override.yaml across recreation; FR/EN
  usage/install guides describe modal controls, pace, scoring and preserved state.

- UUID-bound private Bridge secrets, operator issuance/rotation, host revocation,
  per-owner capabilities/status and authentication rechecks after network waits.
- Online-only random choices and 45-second offline recovery; prepared clips
  continue, MC replacement stays explicit.
- Immutable completed records, host-only consultation/exports and durable
  deletion/purge; 50 games/90 days/16 MiB, no audio. Free old journals/assets on new game.
- Hide sources from playing hosts in STATE/library/diagnostics; cumulative
  catalogue and credential caps. New boundary/migration/crash regression tests.
- Skip links, phase announcements, dialog focus, named audio progress and
  keyboard/history/reflow/200%-text/reduced-motion verification.
- Software 0.5.0.dev0, protocol 6 (6..6), snapshot 5, history 2; legacy migrations,
  unknown-version refusal and cookies preserved on Bridge rotation.
- Docker/native commands, private credential profile, FR/EN guides, ADR 0015,
  threat model and Chromium/WebKit CI. No release published or protocol frozen.

### Security

- Serialize Bridge credential writes across CLI/host processes, reload while
  locked, roll back failed mutations and invalidate stale authentication caches.
  Issue private secrets without overwriting concurrent files; clean failed output
  and refuse reserved state paths.
- Limit successful join/leave churn, bound retained identities and clear removed
  identities on a new game while preserving completed records.
- Reject malformed Content-Length values without integer conversion, duplicate
  private JSON keys and invalid recovery types/indices before applying snapshots.
- Recheck session/host/phase permissions after HTTP bodies and WebSocket HELLO;
  bind streamed audio acceptance to its exact live Bridge connection and job.
- Bound Bridge/player message queues and Bridge incoming rates, stop failed writers, purge
  stale session work and cap reconnection exponents during long outages.
- Expire rate-limit/connection bookkeeping, bound transient log redaction,
  escape log control characters, limit recovery-code rotation and apply total
  HTTP body deadlines.
- Disable API caching and reject incomplete/trailing/multiple gzip catalogues.
- Cap simultaneous catalogue receives per identity and globally, before any
  decompression; preserve upload tokens for bounded retries on temporary 429.
- Reject linked configuration/root/snapshot ancestors; write private snapshots
  and backups atomically with exclusive random temporary files and Windows ACLs.
- Close release staging to expected artifacts and validate package/target names,
  portable archive paths, links, private backups, sizes and sidecar checksums
  before publication or smoke extraction.

### Added

- V0.3 standalone Bridge wheels/sdists with local versions/licenses, exact protocol
  dependency and isolated uvx support for CPython 3.12–3.14.
- Masked terminal setup/configure wizard, explicit save/private backups, Windows
  ACL/Unix 600 atomic configuration, local/configuration/registration diagnostics,
  safe JSON reports and FFmpeg capability checks with stable exit codes.
- MC manual choices for numbered unprepared rounds, private revision confirmation,
  reservations/repeat/source checks, explicit launch and recoverable selection failures.
- Native PyInstaller onedir builds for Windows/Linux x64 and macOS Intel/arm64,
  separate FFmpeg, dependency licenses, manifests/checksums and extracted-archive smokes.
- Validation on supported Python/platform matrices and separate tag-only release
  with artifact provenance checks and PyPI OIDC (maintainer publisher setup required).
- French/English Bridge installation, deployment/troubleshooting and backup/rollback
  guides, plus architecture decisions for distribution and manual MC selection.

- Audio-only extraction from safe video containers, including MP4, MOV, MKV and AVI.
- Global end-of-game review with durable signed scores, all answers and timings,
  explicit final confirmation, and private on-demand excerpt/full-track listening.
- Dynamic folders under each Bridge's authorized root, up to eight simultaneous
  Bridges, library search/filters and optional validated JSON musical metadata.
- Local audio latency adjustment, one-use player recovery codes, join locking,
  live MC answers and optional balanced random selection across folders.
- French and English V0.2 guides, migration notes and security decisions.
- Shared answer instructions and manual scoring rules, teams and spectators, QR invitations,
  browser-local saved selections, game history, detailed recaps and CSV/JSON exports.
- Synchronized pause/resume for playback and answer deadlines, excluding paused time from
  answer timing; private atomic session snapshots with corruption fallback and restart recovery.
- Optional Bridge loudness normalization and bounded silence avoidance, plus host-only
  diagnostics for excluded files and usable/fresh track counts before starting.
- Complete Docker Compose hosting for server/web UI, HTTPS and Bridge/FFmpeg, with
  private and public profiles, read-only music mounts and Windows/Unix browser launchers.
- Docker installation and image-sharing guide; native installation remains available.

- Native PC hosting launcher with private LAN/VPN and public HTTPS profiles,
  plus French user and hosting guides. A VPS is optional.
- Project documentation: README, design specification, contribution guidelines,
  security policy and code of conduct.
- MIT license.

### Changed

- V0.3 introduced protocol 4 and snapshot format 3; V0.5 now uses 5 and 4.
  Snapshots 1/2 remain readable; downgrade requires a pre-migration backup.
- Global host review reveals played tracks privately, supports metadata corrections and
  separates unchecked rows from explicit zero scores. Numeric drafts wait for server echoes.
- Settings can be saved and started atomically; exhausted pools expose recovery actions.
- Host controls use page scrolling, answer deadlines remain distinct from clip progress,
  and final confirmations show actual resulting scores.
- A warmer, consistent game interface for joining, audio setup, answers, host review
  and results, with clearer actions and layouts for phones and computers.
- Host settings, connection details and diagnostics are grouped behind accessible
  disclosures so the current round stays central.

### Fixed

- Private replay releases transfers on Bridge loss and rejected uploads; failed seeks
  retry the requested position and release the previous browser clip.
- Final correction shortcuts/resets and numeric scores wait for server confirmation
  before further edits or publication.
- Source edits wait for completed scans; slow scans/catalog uploads leave heartbeat
  and audio cancellation responsive, with bounded queues and reconnect cleanup.
- An old connection's catalogue upload cannot overwrite a reconnected Bridge.
- Exhausted-session launches and one-track repeat games no longer remain in preparation.
- Host role permissions match the displayed commands and scoring publication rejects
  unchecked rows unless the host explicitly confirms them.
- A new Bridge process no longer deletes temporary audio belonging to a live Bridge.
- Host access now asks for elevation again after ending a session and joining a new one.
- Clip completion is shown during the remaining answer time, including after an early stop.
