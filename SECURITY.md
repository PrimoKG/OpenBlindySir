# Security Policy

## Reporting a vulnerability

**Please do not report security vulnerabilities through public issues, discussions or
pull requests.**

Use GitHub Private Vulnerability Reporting instead: open the repository's
**Security** tab and click **Report a vulnerability**. The report stays private
between you and the maintainer until a fix is available.

Helpful details:

- the affected component (Server, Bridge, web UI, Docker image or Compose files);
- the version or commit;
- steps to reproduce, or a proof of concept;
- the impact as you understand it.

Please do not include real secrets or copyrighted audio in a report.

## Supported versions

Only the **latest minor release** receives security fixes. Before the first release,
fixes land on `main`.

| Version | Supported |
|---|---|
| Latest minor release | Yes |
| Older releases | No |

## Response

OpenBlindySir is maintained by a single developer on a **best-effort** basis. There is
no guaranteed response time, but every report will be read, acknowledged and
investigated, and the fix coordinated with you before any public disclosure. Reporters
are credited in the advisory if they wish.

## Threat model in brief

These controls are implemented in the current V0.5 development checkout (protocol 5).
Release publication and platform acceptance remain separate validation steps.

- **The server is authoritative.** Identity, roles, game state, official time,
  accepted answers, answer order and scores are decided by the server only. Host
  permissions are checked server-side on every command, after streamed mutation
  bodies and after the WebSocket handshake. Answer times come from the server's clock.
- **No spoilers before the reveal.** Each client receives a view filtered for its
  role, audio URLs are random and opaque, and clips carry no tags or cover art.
- **Sessions.** A shared game password gives an `HttpOnly`, `Secure`,
  `SameSite=Strict` `__Host-` cookie whose token is stored hashed. Logins are
  rate-limited, origins are checked, a strict CSP is applied, and the server refuses to
  start with missing or weak secrets.
- **Distinct Bridge identity.** Each UUID has its own credential; the private registry
  stores hashes and durable revocations. A legacy bootstrap binds to only its first
  UUID. Rotation/revocation closes only that owner's connection. Credentials and
  job/connection ownership are rechecked after streamed catalogue/audio bodies.
  Limits: 64 identities, eight connections and 200,000 stored tracks in total.
  Registry changes use a nonblocking OS file lock and reread the authoritative
  file while locked; competing CLI/host writes fail for retry. Failed writes
  invalidate cached credentials and restore the prior in-memory state. Private
  issuance never overwrites a concurrent file and removes unused output on failure.
- **Private history.** Final records freeze names, settings, answers, timings and
  scores without audio. Host-only HTTP access enforces playing-host anti-spoiler
  permissions; the same rules hide source details in state, library and diagnostics.
  Retention is 50 games, 90 days and 16 MiB. Confirmed deletion rewrites both managed
  snapshots; exported files and external backups require separate deletion.
  Unknown snapshot/history formats stop startup without choosing older data.
- **The Bridge treats the server as untrusted.** It only makes outbound connections,
  always verifies TLS, and accepts exactly `WELCOME`, `PREPARE`, `CANCEL`, `PING`
  and `SCAN_SOURCES`. Source scans only select folders under the local root.
  Tracks are referenced by opaque ID, never by
  path, and the server cannot pass any FFmpeg argument.
- **Bridge sandbox.** One allowed folder; symbolic links and junctions are not
  followed; the real path is checked again before every file is opened; jobs are
  bounded by a queue limit and timeouts. Do not run the Bridge as an administrator or
  root.
- **No secrets in logs.** Secrets are masked, never placed in URLs, and file names are
  not logged by default. Deployment secrets stay registered; the supplementary
  transient-token redaction registry is bounded to 4,096 recent values.
- **Bounded network work.** Bridge send queues hold at most 64 messages and overflow
  closes the connection. Bridge input is limited to a burst of 40 and 20 messages/s.
  HTTP bodies have byte caps and total deadlines (15 s JSON, 60 s uploads). Gzip
  catalogues must contain exactly one complete stream. Audio uploads recheck the
  originating connection, job, expiry and asset state after receiving the body.
  Catalogue receiving is limited to one transfer per Bridge identity and eight
  globally, including disconnected/replaced connections still receiving a body.
  All join requests, including successful joins, are capped at 60/IP/minute and
  600/server/minute. At most 1,000 identities (including removed players needed
  by current results) remain in session state; a new game discards removed identities
  after archiving. Invalid/oversized Content-Length values are handled without
  unbounded integer conversion.
- **Private state.** All `/api/` HTTP responses use `Cache-Control: no-store, private`.
  Recovery-code rotation is capped at 5/player/minute and 60/server/minute.
  Configuration/snapshot paths refuse symbolic links and junction ancestors.
  Snapshot files and backups are restricted before writing (Unix 600, private
  Windows ACL) and replaced atomically using exclusive random temporary files.
  Registry/snapshot JSON rejects duplicate keys, malformed types and invalid
  Unicode. Snapshot round indices, score-event sequence and recovery data are
  checked before applying state; known-format corruption can use a validated backup.
- **Release gates.** Staging uses a closed artifact list, with package/version/target
  identity, provenance and hash checks. Archives reject private config/backups,
  links, traversal, Windows device names, duplicate case/Unicode paths and excessive
  declared uncompressed sizes. Smoke extraction validates the whole archive first.
- **Container hardening.** The application runs as a non-root user, on a read-only
  filesystem, with `no-new-privileges`.

Known and accepted limits: the server learns the folder structure and file names of the
shared library from the catalogue; a determined player can hear the next clip a few
seconds early; large-scale DDoS protection is out of scope.

The filesystem checks retain a local TOCTOU window: run with ordinary user privileges
and keep the configured folders under the owner's control. Dependency audits report
known advisories for the checked versions, not proof that software has no flaws.

The detailed Bridge threat model is in
[docs/bridge-security.md](docs/bridge-security.md), and the full threat table in
[docs/architecture.md](docs/architecture.md). Both are written in French.

Operational identity, migration, private diagnostics and backup instructions:
[V0.5 English](docs/v0.5.en.md), [français](docs/v0.5.md) and
[ADR 0015](docs/adr/0015-v05-private-bridges-history-compatibility.md).
This development work does not publish a release or freeze the protocol.
