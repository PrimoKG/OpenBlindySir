# Install the Bridge — V0.5 — development

[Français](bridge-installation.md). Run the Bridge on the music device. It connects
outbound to your self-hosted server. Complete sources remain local; only short
reencoded clips are transferred. Host the server/web UI with [Docker](docker.md)
or the [PC launcher](deployment.md).

**Publication status:** this repository builds packages and archives; these changes
do not publish a release. PyPI commands below require publication first. From a
checkout, run `uv sync --locked` and replace `uvx` with `uv run`.

## Requirements and platforms

The Python package supports CPython **3.12–3.14** on Windows, Linux and macOS.
The binary CI targets Windows 10/11 x64 (Windows 2025 runner), Linux x64 glibc ≥2.35
(Ubuntu 22.04), and macOS 15+ separately for Intel x64 and Apple Silicon arm64.
No Alpine/musl binary, cross compilation or other native architectures. All four
runner checks must pass before publishing. Local Windows testing alone cannot
validate macOS, antivirus, Gatekeeper or SmartScreen.

Archives use PyInstaller **onedir**, include Python, and are unsigned/not notarized.
**FFmpeg and ffprobe are separate prerequisites.** Only the Docker Bridge includes
FFmpeg. Install using `winget install --id Gyan.FFmpeg --exact` (Windows),
[`brew install ffmpeg`](https://formulae.brew.sh/formula/ffmpeg) (macOS), or
`sudo apt update` then `sudo apt install ffmpeg` (Debian/Ubuntu). For other systems
use your official package manager or [FFmpeg downloads](https://ffmpeg.org/download.html).
Reopen the terminal after installation.

## uvx and guided setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) then run:

First obtain a **private identity file issued for this Bridge** from the host
([server-side issuance](#distinct-v05-identity)). Keep it outside shared checkouts
and extracted archives, accessible only to your account. Replace
`IDENTITY_PATH.toml` below with its actual path. From the unpublished checkout,
use `uv run` instead of `uvx` after `uv sync --locked`.

```sh
uvx openblindysir-bridge --version
uvx openblindysir-bridge check-ffmpeg
uvx openblindysir-bridge init --credentials IDENTITY_PATH.toml
uvx openblindysir-bridge run --credentials IDENTITY_PATH.toml
```

The French terminal wizard asks for the base server URL (HTTPS, no `/host`, query
or credentials), the local music root, the Bridge secret and a 1–24 character
display name. **Press Enter at the secret and name prompts** to retain the issued
identity. With `--credentials`, its UUID, name and secret determine the identity
at launch. Never enter a game or host password there. HTTP is permitted only to localhost. Secret
input is masked and requires an interactive terminal. `configure` aliases `init`.

Saving requires explicit confirmation and keeps a private `config.toml.bak-…`
backup. A second confirmation authorizes FFmpeg checks, scanning names and
authenticated registration/catalog upload. No complete source or batch conversion
is sent. The summary reports configuration, tools, file count and connection.
Zero tracks means an empty catalogue; file decoding is checked later per job.
The registration test closes afterward; `run` stays connected. Setup and connection
diagnostics should run **outside a game**, since they replace the same Bridge UUID's
existing connection.

The legacy setup without `--credentials` accepts the host's bootstrap
**BRIDGE_SECRET** for only one UUID. Multiple devices require separate identity
files and UUIDs; sharing the bootstrap does not authorize additional Bridges.

The FFmpeg check requires both tools ≥4.4, configured input demuxers, AAC encoder,
M4A output and loudnorm/afade/silencedetect filters. Opus/WebM is optional. Tool
discovery uses PATH and a sibling ffprobe. Use `--ffmpeg`/`--ffprobe` or the
`OPENBLINDYSIR_BRIDGE_FFMPEG`/`FFPROBE` environment variables for explicit locations.

## Durable configuration and safe diagnostics

Windows: `%APPDATA%\OpenBlindySir\bridge\config.toml`. macOS:
`~/Library/Application Support/OpenBlindySir/bridge/config.toml` (existing legacy
`~/.config/openblindysir/bridge/config.toml` stays in use). Linux:
`$XDG_CONFIG_HOME/openblindysir/bridge/config.toml`, defaulting to `~/.config`.
New files and backups use Unix mode 600 or Windows ACL restricted to the current
account. Preserve this private configuration to keep the Bridge UUID. Independent
Bridges need separate configurations; do not clone their identity.

```sh
uvx openblindysir-bridge --help
uvx openblindysir-bridge check-config --credentials IDENTITY_PATH.toml
uvx openblindysir-bridge doctor --credentials IDENTITY_PATH.toml
uvx openblindysir-bridge doctor --connect --credentials IDENTITY_PATH.toml
uvx openblindysir-bridge doctor --json --credentials IDENTITY_PATH.toml
```

Configuration validation does not write, scan or connect. Doctor checks tools;
only `--connect` scans/registers after an announcement. JSON excludes URL, UUID,
name, paths and secrets. For local settings, CLI overrides environment overrides
file. **Exception:** `--credentials` or `OPENBLINDYSIR_BRIDGE_CREDENTIALS_FILE`
provides UUID, name and secret with priority over all other identity settings.
`--config` selects another private file. Automation can supply the identity path
through `CREDENTIALS_FILE`, the URL through `SERVER` and the root through `DIR`,
all prefixed with `OPENBLINDYSIR_BRIDGE_`. Keep `--credentials` on diagnostics and
each launch, or set that environment variable persistently. Avoid placing secrets
in command-line arguments/history.

Exit codes: 0 success, 2 usage/configuration/access, 3 FFmpeg, 4 connection
diagnostic failure, 130 cancellation. `run` reconnects on transient failures;
Ctrl+C stops it. A permanent registration rejection terminates with an error.

## Native archive

Download the matching official release and check its commit and `SHA256SUMS`:
PowerShell `Get-FileHash` with `-Algorithm SHA256`, Linux `sha256sum -c SHA256SUMS`,
macOS `shasum -a 256 -c SHA256SUMS`. Checksums do not authenticate unknown sources.
Extract **the entire directory**, including `_internal`, then open a terminal there.

Windows:

```powershell
.\openblindysir-bridge.exe --version
.\openblindysir-bridge.exe init --credentials IDENTITY_PATH.toml
.\openblindysir-bridge.exe run --credentials IDENTITY_PATH.toml
```

Linux/macOS:

```sh
chmod u+x ./openblindysir-bridge
./openblindysir-bridge --version
./openblindysir-bridge init --credentials IDENTITY_PATH.toml
./openblindysir-bridge run --credentials IDENTITY_PATH.toml
```

The binary and uvx share the same CLI and configuration. Included files:
README.txt, VERSION, LICENSE, THIRD_PARTY_NOTICES.txt, notices/ and release.json
with per-file checksums and provenance. If unsigned software is blocked, verify
origin/hash and report the exact security alert privately without credentials.
Do not disable antivirus or bypass an unexplained warning. Use uvx when needed.
Unix execution also requires a filesystem allowing execution.

## Updating

V0.5 requires **protocol 6**, admitted range 6 to 6, on all components. Protocols 2/3/4/5 are refused;
the Bridge package pins its protocol package to the exact same version. Pin a
published release by replacing `VERSION` below with the published version matching
the server:

```sh
uvx --from openblindysir-bridge==VERSION openblindysir-bridge --version
uvx --from openblindysir-bridge==VERSION openblindysir-bridge run --credentials IDENTITY_PATH.toml
```

Keep the configuration outside the uv cache/archive. Back up server state before
upgrading; rerun version/doctor and registration outside a game. See
[operations](operations.md), [English troubleshooting/deployment](operations.en.md)
and the [release procedure](releasing.md).

## Distinct V0.5 identity

From the unpublished checkout, the host issues a private TOML file with
`uv run openblindysir-server bridge-credential --bridge-id UUID --name 'Music PC' --output .local/private/pc.toml`.
Use a private parent directory and a new output filename, then transfer it privately
to that owner. Issuance never overwrites an existing file. For rotation, retain the
UUID, issue to a new filename, transfer the new identity and restart that Bridge
using its path. Other Bridges retain their identities. Registry modifications are
locked; if another command is modifying it, retry after that command ends. Use
local storage supporting locks and hard links; do not remove
`bridge-credentials.lock` while the application is running. On the music device:
`uv run openblindysir-bridge run --config .local/bridge/config.toml --credentials .local/private/pc.toml`.
Configure the URL and root locally with `configure`. The identity file overrides
UUID, name and secret from CLI/environment/configuration, while leaving local choices
intact. Rotation retains the UUID; separate instances need distinct UUIDs.
The legacy bootstrap secret can authenticate only one UUID.
See [V0.5](v0.5.en.md) for Docker commands, revocation and permissions. Protocol errors
report the required range without copying arbitrary remote close text.
This is a development version: no release, signing or protocol freeze.
