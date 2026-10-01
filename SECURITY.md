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

This summarises the intended design. OpenBlindySir is in early development: nothing is
implemented or released yet (see the README [Status](README.md#status) section).

- **The server is authoritative.** Identity, roles, game state, official time,
  accepted answers, answer order and scores are decided by the server only. Host
  permissions are checked server-side on every command, and answer times come from the
  server's clock, never from the client.
- **No spoilers before the reveal.** Each client receives a view filtered for its
  role, audio URLs are random and opaque, and clips carry no tags or cover art.
- **Sessions.** A shared game password gives an `HttpOnly`, `Secure`,
  `SameSite=Strict` `__Host-` cookie whose token is stored hashed. Logins are
  rate-limited, origins are checked, a strict CSP is applied, and the server refuses to
  start with missing or weak secrets.
- **The Bridge treats the server as untrusted.** It only makes outbound connections,
  always verifies TLS, and accepts a closed protocol of four message types, of which
  only one (`PREPARE`) requests any work. Tracks are referenced by opaque ID, never by
  path, and the server cannot pass any FFmpeg argument.
- **Bridge sandbox.** One allowed folder; symbolic links and junctions are not
  followed; the real path is checked again before every file is opened; jobs are
  bounded by a queue limit and timeouts. Do not run the Bridge as an administrator or
  root.
- **No secrets in logs.** Secrets are masked, never placed in URLs, and file names are
  not logged by default.
- **Container hardening.** The application runs as a non-root user, on a read-only
  filesystem, with `no-new-privileges`.

Known and accepted limits: the server learns the folder structure and file names of the
shared library from the catalogue; a determined player can hear the next clip a few
seconds early; large-scale DDoS protection is out of scope.

The detailed Bridge threat model is in
[docs/bridge-security.md](docs/bridge-security.md), and the full threat table in
[docs/architecture.md](docs/architecture.md). Both are written in French.
