# OpenBlindySir
⚠️ Early development — API/protocol may change.

Current step: **V0.5** (`0.5.0.dev0`, protocol **14**, snapshots **11**).

Latest finale fixes, validation evidence and remaining device/release checks:
[October 10 finale simplification report](docs/audits/2026-10-10-finale-simplification.en.md)
([français](docs/audits/2026-10-10-finale-simplification.md)).
Separate Bridge credentials, private history and recovery/accessibility checks
are implemented in source. [V0.5 EN](docs/v0.5.en.md) / [V0.5 FR](docs/v0.5.md).
This development version does not freeze the protocol or announce a release.

OpenBlindySir is an open-source, self-hosted, remote-first multiplayer blind-test
application. Your music library stays on your own computer and is exposed to the
game only through the OpenBlindySir Bridge.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

It is built for **one private game at a time**, with friends playing on the same
local network or **remotely**: everyone listens in their own browser, usually with a voice chat on the
side, types a free-text answer, and chooses host scoring or optional automatic matching.

Prepare themed nights with combined genre, language, year, tag and universe filters,
live playable-track counts and reusable selections. [Themed nights EN](docs/themed-nights.en.md)
/ [Soirées à thème FR](docs/themed-nights.md).
Latest audit and fixes: [EN](docs/audits/2026-10-08-theme-autofix.en.md)
/ [FR](docs/audits/2026-10-08-theme-autofix.md).

## What it is not

- **Not a SaaS.** You run your own server; there is no hosted service.
- **Not a Kahoot clone.** Free-text answers, with optional automatic scoring and host corrections.
- **No rooms, no accounts.** One server process hosts one private game; players join
  with a nickname through a QR invitation or with the shared game password.
  A session code also supports joining and host-approved seat recovery.
- **Not a Spotify, YouTube or Deezer player.** It only plays files you already have
  on your own computer.
- **Not a music downloader.** It never fetches audio from any platform.

## How the Bridge works

```
  Players' browsers           Host PC or VPS + Caddy                 PC with the music
+-------------------+       +------------------------+           +-------------------------+
| Web UI            |       | OpenBlindySir Server   |           | OpenBlindySir Bridge    |
| (player or host)  |       |                        |           |                         |
|                   |<----->| whole game in RAM      |<----------| scans allowed folders   |
| fetches the clip, | HTTPS | clips held in RAM      | outbound  | FFmpeg: 20-30 s clip    |
| plays it in sync  |  WSS  | (temporary)            | WSS+HTTPS | no tags, no cover art   |
| at a set time     |       | official clock         |           | no inbound port         |
+-------------------+       +------------------------+           +------------+------------+
                                                                              | read-only
                                                                   +----------+----------+
                                                                   | your music folder   |
                                                                   | full files never    |
                                                                   | leave this PC       |
                                                                   +---------------------+
```

- The **OpenBlindySir Bridge** is a small command-line program that runs on the
  computer holding your music. It opens an **outbound** connection to your server
  (secure WebSocket for control, HTTPS for uploads): no open port, no port forwarding,
  no network share required by the Bridge. If the server runs on the same PC, the
  server's HTTPS endpoint must still be reachable by players.
- Each Bridge scans an authorized root and selected subfolders. Up to eight Bridges
  can share a game; the host can rescan sources without restarting the server.
- When a round needs a track, the server asks for it by ID. The Bridge cuts a short
  clip (typically 20–30 s) with FFmpeg, **without tags or cover art**, and uploads it.
- **Full files stay on the Bridge.** Game clips live temporarily in server RAM.
  Host-only full listening is optional and transfers short reencoded segments on demand.
- The Bridge **treats the server as untrusted**: a closed set of commands, no
  free-form paths or FFmpeg arguments, and every file access confined to the chosen
  folder.

## Architecture at a glance

| Component | Runs on | Role |
|---|---|---|
| **OpenBlindySir Server** | Your own PC or a VPS | Python (FastAPI). Serves the web UI and holds the whole game in RAM in a **single process**: players, rounds, answers, scores. It is authoritative for identity, game state, timing and scores. No database, no FFmpeg. |
| **Web UI** | Each player's browser | React + TypeScript. Downloads and decodes the clip, then starts playback at a time set by the server, using a synchronised clock. |
| **OpenBlindySir Bridge** | The PC with the music | Python CLI. Folder scanner, sandbox, FFmpeg clip jobs, outbound client. Knows nothing about the game rules. |

Game-night controls include shared instructions and scoring rules, teams and spectators,
QR invitations, automatic same-browser reconnection, a shared session code,
saved folder selections, pause/resume, detailed results and CSV/JSON exports.
The host library offers private 15-second previews from the middle of a track,
tags and **Linked to** categories, track disabling, and responsive pagination.
Private local snapshots preserve the session across restarts; audio remains in RAM only.
The host presents played tracks and closed answers during a shared grand finale.
Players follow confirmed points and provisional rankings live, with synchronized
excerpt replay. Private navigation, detailed timing and optional full listening
support the host’s scoring. One explicit validation freezes the scores and starts
the shared podium reveal, including ties.
The Bridge can normalize volume and avoid silent excerpts, with excluded files reported
to the host. See the [English user guide](docs/user-guide.en.md) / [guide français](docs/guide-utilisateur.md).

**Protocol 14:** update the server, Bridge and web UI together.

Full Docker Compose hosting is available: server plus built web UI, the official
Caddy image, and a Bridge image containing FFmpeg. Windows and Unix launchers
initialize the private configuration, start the services and open `/host` in your
default browser. There are no rooms: one server is one game night.

**PC hosting is available without Docker or a VPS.** The PC launcher starts the
server and Caddy with HTTPS. Use a LAN address for a local game, a private VPN
address for distant friends, or a public domain with TCP ports 80/443 forwarded
to your PC. See the [hosting guide](docs/deployment.md) for certificates, firewall
configuration and exact commands.

## Scoring and shared finale

- Manual scoring remains the default. Optional automatic scoring compares each
  requested criterion with frozen track references, at a default 90% similarity
  threshold. Years and very short references require exact matches.
- Players type a free-text answer and lock it in. The server timestamps each
  submission **on its own clock** when it arrives and records the order; clients
  cannot send their own timing.
- While a round is open, players only see an anonymous "n/m have answered" counter,
  hidden when fewer than three players are expected. No player sees who has answered,
  or how fast, before the reveal.
- In the mandatory end-of-game review, the host sees every played round and its
  answers in order, checks uncertain matches and can adjust any points (+N, 0, −N).
- **Speed is measured and shown, never automatically converted into points.** This is
  a deliberate, permanent design choice.
- Draft points and final corrections survive reconnection and snapshots. One explicit
  validation publishes all results and freezes the event journal. Early endings keep
  answers; played cancelled rounds remain visible and excluded from scoring.

## Quickstart

### Docker (recommended for installation isolation)

Install Docker with Compose and start its Linux engine. Download this repository
as a ZIP or clone it, then run from its root on Windows:

```powershell
.\tools\docker-host.ps1 init -Address 192.168.1.42:8443 -MusicDir 'D:\Music'
.\tools\docker-host.ps1 start
```

On Linux/macOS:

```sh
sh tools/docker-host.sh init --address 192.168.1.42:8443 --music-dir '/path/Music'
sh tools/docker-host.sh start
```

Replace the example IP and folder with your own. Python, Node.js, Caddy and FFmpeg
are built into the images; players need only a browser. Follow the
[Docker guide](docs/docker.md) for private certificate trust, VPN/public access,
stopping the services and sharing the exact images. No published release is required.

### Native installation

Install Python 3.12–3.14, [uv](https://docs.astral.sh/uv/), Node.js 22+,
[Caddy](https://caddyserver.com/docs/install) and FFmpeg/ffprobe **9.0.2 or newer**
(for the Bridge). The Docker Bridge includes the required audio build.
From a clone of this repository:

```sh
uv sync --locked
npm --prefix web ci
npm --prefix web run build
uv run python tools/host_pc.py init --address 192.168.1.42:8443
uv run python tools/host_pc.py run
```

Replace the example address with your PC's LAN address. Before inviting players,
follow the [hosting guide](docs/deployment.md) to trust the private certificate and
start the Bridge. Then open the printed `/host` URL. The
[English user guide](docs/user-guide.en.md) / [guide français](docs/guide-utilisateur.md) explains joining, testing sound, answering,
manual scoring and the final score review.

## Status

The development Bridge can be built as a standalone wheel/sdist or native PyInstaller
onedir archive. It has a masked setup wizard, private configuration/backups,
`check-config`, `doctor`, version and FFmpeg capability checks. After PyPI
publication, use `uvx openblindysir-bridge init` then `uvx openblindysir-bridge run`.
See [Bridge installation](docs/bridge-installation.en.md); a source checkout uses
`uv run` today. Native release checks target Windows x64, Linux x64 and macOS
Intel/Apple Silicon; runner execution and unsigned-binary alerts need validation
before publishing. The MC can reserve tracks for unprepared numbered rounds,
see the confirmed choice, and explicitly launch or replace a failed selection.

**Early development.** A playable source checkout is available and complete games
have passed local automated tests with synthetic clips; CI is configured to run
the game suites on pushed changes. No release has been published.
Real-device, accessibility and acoustic checks remain, along with unresolved
system-package security alerts documented in the
[latest local audit](docs/audits/2026-10-08-autofix.en.md).
The API and protocol may change until v1.0.

Roadmap:

| Version | Theme | Highlights |
|---|---|---|
| **v0.1** | A real game night | First playable version: password join, host playing or hosting as MC, synchronised playback, free-text answers, server-side timing, manual scoring, mandatory final score review, Bridge CLI with a demo mode, Docker + Caddy. French UI. Validated by an actual game night with friends. |
| **v0.2** | Comfort and robustness | Implemented in source: global review/private replay, audio from video, dynamic multi-Bridge sources, search/metadata, pause, manual latency, silence/loudness, snapshots, join lock/recovery codes, exports, FR/EN, teams/spectators, folder balancing and live MC answers. Real-device/acoustic validation remains. |
| **v0.3** | Distribution | Implemented in source: standalone uvx package, masked wizard/private backups, safe diagnostics, MC manual selection, native onedir build/checksums and validation/tag-only OIDC release workflows. PyPI setup, all-platform runner execution, signing/real-device checks remain before publication. |
| **v0.5** | Private sources and durable nights | Implemented: UUID-bound revocable credentials, per-Bridge status/capabilities, offline recovery, host history with deletion and 50-game/90-day/16-MiB retention, protocol 14/snapshot 11 migrations, keyboard/reflow/security checks. Screen readers, real devices and all native runners remain manual validation. |
| **v1.0** | Stable | Future release decision, supported compatibility policy, platform/accessibility acceptance and removal of the early-development banner after validation. Protocol is not frozen in V0.5. |

Real progress is recorded in [docs/DEVLOG.md](docs/DEVLOG.md).

## Documentation

- [V0.5 FR](docs/v0.5.md) / [V0.5 EN](docs/v0.5.en.md) — individual credentials, history/privacy, compatibility and backup

- [Installer le Bridge](docs/bridge-installation.md) / [Bridge installation](docs/bridge-installation.en.md) — uvx, native archives, FFmpeg, setup and version policy
- [Dépannage](docs/troubleshooting.md) / [English operations](docs/operations.en.md) — connection, catalogue, extraction and browser audio
- [Mise à jour et sauvegarde](docs/operations.md) — proxy, compatibility and rollback
- [Release procedure](docs/releasing.md) — native matrix, checksums, provenance and PyPI configuration

- [Guide utilisateur](docs/guide-utilisateur.md) / [User guide](docs/user-guide.en.md) — players, playing host and MC
- [Sources and metadata](docs/media-and-metadata.md) — formats, sizes, private imports (French)
- [V0.2 technical notes](docs/v0.2.en.md) — protocol, recovery, sources and replay (English)
- [Full Docker hosting](docs/docker.md) — all services, browser launchers and image sharing (French)
- [Hosting on your PC](docs/deployment.md) — LAN, private VPN and Internet (French)
- [UX notes](docs/UX.md) — interface grammar and local verification
- [docs/architecture.md](docs/architecture.md) — canonical design specification
- [docs/protocol.md](docs/protocol.md) — network protocol
- [docs/sync.md](docs/sync.md) — audio synchronisation
- [docs/bridge-security.md](docs/bridge-security.md) — Bridge threat model and sandbox
- [docs/adr/](docs/adr/) — architecture decision records

This README is in **English**. User and Bridge installation guides are available
in **French and English**; the hosting and design references are mainly French.
The web UI offers an **FR / EN switch in every header**. Switching is immediate,
without reloading the game, and the choice is saved separately in each browser.

## Security

Please report vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).
Do not open public issues for security problems.

The [latest local audit](docs/audits/2026-10-08-autofix.en.md) records the fixes,
regression tests, exact deployed app image and remaining system advisories. Earlier
reports retain their original scope and date. This is not a blanket assurance for
other images or native installations.

## Music & rights

- **You bring your own files.** OpenBlindySir ships software only: no music, no
  samples, no commercial content, neither in the repository nor in the Docker image.
- **Your files stay on your computer.** The only exception is short, temporary clips
  held in RAM on your own server for gameplay and private previews. Optional
  host-only full listening also uses short reencoded segments, never the source file.
- **You are responsible** for the content you use and for complying with the law
  that applies to you.
- **No music is provided** with the project.
- **No downloading from commercial platforms.** OpenBlindySir does not stream or
  download audio from Spotify, YouTube, Deezer or any other service.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) first, and
open an issue before starting any significant change. Everyone taking part is expected
to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

OpenBlindySir is released under the [MIT License](LICENSE).

Precompiled offline validation pack: [French guide](docs/offline-pack.md) / [English guide](docs/offline-pack.en.md). Windows assistant supports setup, start, stop, status, certificate approval guidance, backup, update and explicit rollback. The pack is unsigned and not a public release.

### Latest correction pass — 10 October 2026

The [complete requirements check (FR)](docs/audits/2026-10-10-conversation-check.md)
and [English report](docs/audits/2026-10-10-conversation-check.en.md) distinguish
verified features from remaining release limitations. This follow-up fixes the
offline pack's protocol check and keeps library tracks visible on small laptops,
with collapsible detailed filters and a complete filter reset.

Background musical references, ready-only automatic games, per-criterion corrections
and a simpler finale are documented in the [English scoring guide](docs/automatic-scoring.en.md)
and [French guide](docs/notation-automatique.md). Protocol 14 / snapshot 11;
update server, web and Bridge together, with a stopped-volume backup for rollback.
