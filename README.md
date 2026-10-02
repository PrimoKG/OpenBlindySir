# OpenBlindySir
⚠️ Early development — API/protocol may change.

OpenBlindySir is an open-source, self-hosted, remote-first multiplayer blind-test
application. Your music library stays on your own computer and is exposed to the
game only through the OpenBlindySir Bridge.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

It is built for **one private game at a time**, with friends playing on the same
local network or **remotely**: everyone listens in their own browser, usually with a voice chat on the
side, types a free-text answer, and the host does the scoring.

## What it is not

- **Not a SaaS.** You run your own server; there is no hosted service.
- **Not a Kahoot clone.** No multiple-choice quizzes, no automatic points.
- **No rooms, no accounts.** One server process hosts one private game; players join
  with a shared password and a nickname.
- **Not a Spotify, YouTube or Deezer player.** It only plays files you already have
  on your own computer.
- **Not a music downloader.** It never fetches audio from any platform.

## How the Bridge works

```
  Players' browsers           Host PC or VPS + Caddy                 PC with the music
+-------------------+       +------------------------+           +-------------------------+
| Web UI            |       | OpenBlindySir Server   |           | OpenBlindySir Bridge    |
| (player or host)  |       |                        |           |                         |
|                   |<----->| whole game in RAM      |<----------| scans one folder        |
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
- It scans **one folder you choose** and sends the server a lightweight catalogue
  (opaque track IDs, relative paths, sizes).
- When a round needs a track, the server asks for it by ID. The Bridge cuts a short
  clip (typically 20–30 s) with FFmpeg, **without tags or cover art**, and uploads it.
- **Full files never leave your PC.** Clips live only in the server's RAM, a few at a
  time, and are discarded as the game moves on.
- The Bridge **treats the server as untrusted**: a closed set of commands, no
  free-form paths or FFmpeg arguments, and every file access confined to the chosen
  folder.

## Architecture at a glance

| Component | Runs on | Role |
|---|---|---|
| **OpenBlindySir Server** | Your own PC or a VPS | Python (FastAPI). Serves the web UI and holds the whole game in RAM in a **single process**: players, rounds, answers, scores. It is authoritative for identity, game state, timing and scores. No database, no FFmpeg. |
| **Web UI** | Each player's browser | React + TypeScript. Downloads and decodes the clip, then starts playback at a time set by the server, using a synchronised clock. |
| **OpenBlindySir Bridge** | The PC with the music | Python CLI. Folder scanner, sandbox, FFmpeg clip jobs, outbound client. Knows nothing about the game rules. |

Deployment (planned): one application image plus the official
[Caddy](https://caddyserver.com/) image in Docker Compose, for automatic HTTPS.
Caddy is optional if you already run a reverse proxy. There are no rooms: one server
is one game night.

**PC hosting is available without Docker or a VPS.** The PC launcher starts the
server and Caddy with HTTPS. Use a LAN address for a local game, a private VPN
address for distant friends, or a public domain with TCP ports 80/443 forwarded
to your PC. See the [hosting guide](docs/deployment.md) for certificates, firewall
configuration and exact commands.

## Human scoring

- The server never knows the right answer and never judges an answer.
- Players type a free-text answer and lock it in. The server timestamps each
  submission **on its own clock** when it arrives and records the order; clients
  cannot send their own timing.
- While a round is open, players only see an anonymous "n/m have answered" counter,
  hidden when fewer than three players are expected. No player sees who has answered,
  or how fast, before the reveal.
- During review, the host sees the answers in order, with times to the tenth of a
  second, and awards points by hand (+N, 0, −N) with whatever rules the group likes.
- **Speed is measured and shown, never automatically converted into points.** This is
  a deliberate, permanent design choice.
- Before the final results, a mandatory final score review lets the host check and
  adjust every score. Scores are derived from an event log, so corrections are
  traceable and reversible.

## Quickstart

Install Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 22+,
[Caddy](https://caddyserver.com/docs/install) and FFmpeg (for the Bridge).
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
[user guide](docs/guide-utilisateur.md) explains joining, testing sound, answering,
manual scoring and the final score review.

## Status

**Early development.** A playable source checkout is available and complete games
are tested locally and in CI with synthetic clips. No release has been published.
Real mobile devices, acoustic synchronisation and the maintainer's music library
still require validation; the API and protocol may change until v1.0.

Roadmap:

| Version | Theme | Highlights |
|---|---|---|
| **v0.1** | A real game night | First playable version: password join, host playing or hosting as MC, synchronised playback, free-text answers, server-side timing, manual scoring, mandatory final score review, Bridge CLI with a demo mode, Docker + Caddy. French UI. Validated by an actual game night with friends. |
| **v0.2** | Comfort and robustness | Pause, manual latency offset, silence detection and loudness normalisation, crash recovery (to be confirmed), join lock, results export, English UI. |
| **v0.3** | Distribution | Bridge installable with `uvx openblindysir-bridge`, prebuilt Bridge binaries, first-run wizard, troubleshooting and reverse-proxy guides. |
| **v1.0** | Stable | Frozen protocol, multiple Bridges with one secret each, history across game nights, accessibility pass, security review, "early development" banner removed. |

Real progress is recorded in [docs/DEVLOG.md](docs/DEVLOG.md).

## Documentation

- [User guide](docs/guide-utilisateur.md) — players, playing host and MC (French)
- [Hosting on your PC](docs/deployment.md) — LAN, private VPN and Internet (French)
- [UX notes](docs/UX.md) — interface grammar and local verification
- [docs/architecture.md](docs/architecture.md) — canonical design specification
- [docs/protocol.md](docs/protocol.md) — network protocol
- [docs/sync.md](docs/sync.md) — audio synchronisation
- [docs/bridge-security.md](docs/bridge-security.md) — Bridge threat model and sandbox
- [docs/adr/](docs/adr/) — architecture decision records

The design documents and the current user guides are written in **French**, matching
the v0.1 web UI. This public README is in **English**. The development preview also
includes English UI strings through `?lang=en`.

## Security

Please report vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).
Do not open public issues for security problems.

## Music & rights

- **You bring your own files.** OpenBlindySir ships software only: no music, no
  samples, no commercial content, neither in the repository nor in the Docker image.
- **Your files stay on your computer.** The only exception is short, temporary clips
  held in RAM on your own server during a game.
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
