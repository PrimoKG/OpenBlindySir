# Contributing to OpenBlindySir

Thanks for your interest in OpenBlindySir. The project is in early development and is
maintained by a single developer, so its scope is deliberately small and its tooling
is being set up step by step. This guide describes how contributions work today and
what is planned.

## Before you start

- **Open an issue before any significant pull request**: a new feature, a protocol
  change, a new dependency, or a change spanning several components. Small fixes
  (typos, documentation, obvious bugs) can go straight to a pull request.
- Use GitHub Discussions for questions and ideas, and issues for bugs and concrete
  proposals.
- The design is described in [docs/architecture.md](docs/architecture.md) and the
  decision records in [docs/adr/](docs/adr/). These internal design documents are
  written in French.

## Scope

OpenBlindySir is a self-hosted blind test for one private game among friends. The
following are **out of scope** and pull requests adding them will be declined:

- **User accounts**, **rooms**, or several simultaneous games on one server.
- **Streaming or downloading audio** from Spotify, YouTube, Deezer or any other
  platform. Audio only ever comes from the user's own files, through the Bridge.
- **Automatic speed scoring**: no speed-based points or bonuses, no pre-filled
  scales, no "apply 3/2/1" buttons. Answer times are measured and shown; points are
  always awarded by the host.

## Development environment

For a complete isolated runtime, use the [Docker guide](docs/docker.md); Python,
Node.js and FFmpeg stay in containers. For source development or native hosting,
use the prerequisites below and the [native hosting guide](docs/deployment.md).

Prerequisites:

- **Python 3.12 or later** and **[uv](https://docs.astral.sh/uv/)**: a uv workspace
  with three packages, `openblindysir-protocol`, `openblindysir-server` and
  `openblindysir-bridge`.
- **Node.js** (current LTS) and npm, for the web UI in `web/`.
- **FFmpeg** (`ffmpeg` and `ffprobe` on `PATH`), needed **only for the Bridge** and its
  tests. The server never uses FFmpeg.
- **Docker** (optional), to build and test the image.

Local development, without Docker:

```sh
DEV_MODE=1 uv run openblindysir-server serve # development mode, never in production
npm run dev                              # in web/, proxies /api and the WebSocket
uv run openblindysir-bridge --demo       # synthetic tracks, no real music needed
```

The Bridge `--demo` mode generates synthetic tracks (tones, beeps, clicks), so you can
develop and test without any copyrighted content.

## Tests and checks

Checks to run before significant commits (also exercised in CI):

| Area | Checks |
|---|---|
| Server and protocol | `pytest`, `ruff check`, `ruff format --check`, `pyright` |
| Web UI | Biome, `tsc --noEmit`, Vitest |
| Bridge | `pytest` for the Bridge (Windows path, junction and sandbox tests also run in CI) |
| Protocol | TypeScript types regenerated from the Python models, with no diff |
| End to end | Playwright (Chromium) |
| Docker | `docker build` |

Tests only use sounds generated at run time (sine waves, clicks, silence through
FFmpeg `lavfi`). `main` must never be knowingly broken.

## Code style

- **Python**: ruff for linting and formatting, pyright for type checking.
- **TypeScript**: Biome for linting and formatting. `dangerouslySetInnerHTML` is not
  allowed.
- Code, identifiers, comments, log event names and protocol error codes are in
  **English**. UI text goes through the i18n dictionary (French in v0.1).
- Domain names carry no brand: `Player`, `Round`, `Session`, `Bridge`, `ScoreEvent`.
  The `openblindysir` slug is reserved for package, CLI, image and logger names.

## Commits

Commits follow [Conventional Commits](https://www.conventionalcommits.org/) and are
written **in English**.

```
<type>(<scope>): <summary>
```

- **Types**: `feat`, `fix`, `test`, `docs`, `refactor`, `perf`, `build`, `ci`, `chore`
- **Scopes**: `protocol`, `server`, `web`, `bridge`, `docker`, `ci`, `docs`, `deps`,
  `tools`

Examples:

```
feat(server): record server-side answer timing
feat(bridge): add sandboxed library scanner
test(server): cover reconnect and scoring transitions
docs: document bridge threat model
```

One commit is one logical unit of work: no "wip" or "update" commits, and no commit
per line changed.

## Branches and pull requests

- Work on a dedicated branch (for example `feat/game-core`) and open a pull request
  against `main`.
- Pull requests are merged once CI is green, using rebase-merge to keep a linear
  history.
- If your change is visible to users, add an entry under `[Unreleased]` in
  [CHANGELOG.md](CHANGELOG.md).

## Never commit

- **Real audio files** of any kind: music, clips, excerpts, commercial cover art.
- **Secrets**: `.env` files, tokens, cookies, `BLIND_PASSWORD`, `HOST_PASSWORD`,
  `BRIDGE_SECRET`, certificates and private keys.
- Personal Bridge configuration, and logs that contain secrets.

`.env.example` contains placeholder values only. The `.gitignore`, the repository
hygiene check (`tools/check_repo_hygiene.py`, run locally now, and in CI once it is set
up) and GitHub push protection (enabled once the repository is published) are there to
catch mistakes, but they do not replace checking your own diff.

Test passwords and secrets in fixtures, tests and CI files must start with `example`
(for instance `example-host-password-1`) so that the hygiene check recognises them as
placeholders. A line may instead carry the comment `# hygiene: allow`, which is reserved
for documented false positives: never use it to keep a real value.

## Project records

| File | Audience | Content |
|---|---|---|
| `docs/architecture.md` | Contributors | The **current** design, updated when a decision changes. |
| `docs/DEVLOG.md` | Maintainer | What **actually happened**: goals, decisions, failures, tests actually run. Append-only, never rewritten. |
| `CHANGELOG.md` | Users | User-facing changes per release (Added, Changed, Fixed, Security). No internal details. |
| `docs/adr/NNNN-*.md` | Contributors | **Structural** decisions only. A superseded ADR is kept and linked to its replacement. |

The specification, DEVLOG and ADRs are written in French; public files such as this
one are in English.

## Licensing

Contributions follow the **inbound = outbound** rule: by submitting a contribution,
you agree that it is licensed under the [MIT License](LICENSE), like the rest of the
project. Only submit work you have the right to license this way.

## Code of Conduct

Everyone taking part in the project is expected to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).
