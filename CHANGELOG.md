# Changelog

All notable changes to OpenBlindySir are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While
the version is 0.x, the API and protocol may change between minor versions.

## [Unreleased]

### Added

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

- Protocol 2: server, Bridge and web UI must be updated together.
- Host review reveals the current track privately, supports title/artist corrections and
  separates unchecked rows from explicit zero scores. Numeric drafts wait for server echoes.
- Settings can be saved and started atomically; exhausted pools expose recovery actions.
- Host controls use page scrolling, answer deadlines remain distinct from clip progress,
  and final confirmations show actual resulting scores.
- A warmer, consistent game interface for joining, audio setup, answers, host review
  and results, with clearer actions and layouts for phones and computers.
- Host settings, connection details and diagnostics are grouped behind accessible
  disclosures so the current round stays central.

### Fixed

- Exhausted-session launches and one-track repeat games no longer remain in preparation.
- Host role permissions match the displayed commands and scoring publication rejects
  unchecked rows unless the host explicitly confirms them.
- A new Bridge process no longer deletes temporary audio belonging to a live Bridge.
- Host access now asks for elevation again after ending a session and joining a new one.
- Clip completion is shown during the remaining answer time, including after an early stop.
