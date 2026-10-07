# Deployment, troubleshooting and recovery — V0.5 — development

[Français](operations.md). The [Bridge installation guide](bridge-installation.en.md)
covers uvx/native archives and FFmpeg. Existing [Docker](docker.md) and
[PC launcher](deployment.md) guides retain exact commands and configurations.

## Host on LAN, VPN or Internet

Clone/download the server repository and run the existing Docker launcher:

```powershell
.\tools\docker-host.ps1 init -Address 192.168.1.42:8443 -MusicDir 'D:\Music'
.\tools\docker-host.ps1 start
```

Linux/macOS:

```sh
sh tools/docker-host.sh init --address 192.168.1.42:8443 --music-dir '/path/Music'
sh tools/docker-host.sh start
```

Replace address/folder. LAN uses the server's stable LAN address and private
firewall TCP 8443. VPN uses its VPN address and an interface-specific firewall
rule, with all participants on that VPN. For Internet use `-Mode public -Address
blind.example.com` (POSIX `--mode public --address blind.example.com`), point DNS
A/AAAA to the accessible server and forward/allow TCP 80/443 for Caddy. CGNAT or
double NAT may require a reachable VPN or VPS. Never expose internal port 8000.

Private LAN/VPN certificates require trusting the host's public Caddy root in
each browser. The launcher exports `.local/docker/root.crt`; never share its keys
or Caddy storage. Python Bridge on another PC uses `SSL_CERT_FILE` pointing to
this root. Public HTTPS uses ordinary trusted certificates. Do not disable TLS.
The Bridge needs outbound HTTPS/WSS only; localhost refers to the same device.

A native server checkout uses `uv sync --locked`, `npm --prefix web ci`,
`npm --prefix web run build`, `uv run python tools/host_pc.py init --address
192.168.1.42:8443`, then `uv run python tools/host_pc.py run`. It needs Caddy and
Node separately; FFmpeg is needed only on the music device. Init refuses to
overwrite the private environment. Give players BLIND_PASSWORD, keep HOST_PASSWORD
and BRIDGE_SECRET private. Launch the matching Bridge separately.

One server process owns one private session. An existing reverse proxy must
serve `/`, API, WebSocket upgrade and uploads on the same HTTPS origin, without
subpath rewriting or private caching. Trust forwarded headers only from the
actual proxy address. Use the supplied Caddy configurations in `deploy/` as the
reference; preserve application size/time/concurrency limits.

## Diagnose a problem

Run `--version`, `check-config`, `check-ffmpeg`, `doctor`; only `doctor --connect`
scans names and registers (outside a game). The test closes afterward: use `run`
to stay connected. `doctor --json` is copyable without paths, URL, UUID or secrets.

| Symptom | Action |
|---|---|
| Exit 2 | Re-run interactive init: HTTPS base URL, readable real root without links/junctions, correct Bridge secret ≥32 characters, name ≤24 characters. Check private configuration permissions. |
| Exit 3 | Install both FFmpeg/ffprobe ≥4.4, reopen terminal, correct PATH/explicit tool locations. AAC/M4A, configured demuxers and audio filters are mandatory. |
| `network`, reconnecting | Check URL from the music device, DNS/VPN/firewall/proxy and WebSocket forwarding. No inbound Bridge port needed. |
| `certificate` | Correct address, system time and trusted CA; configure SSL_CERT_FILE for private Python TLS. |
| `authentication` | Check the private credential's UUID/secret and revocation; never use game/host passwords. See V0.5 identity-file precedence. |
| `protocol` | Update server, Bridge and web UI to protocol **10** together; reload old web tabs. |
| `catalogue` | Check proxy upload limits, server private diagnostics and duplicate Bridge identity; retry outside a game. |
| Empty catalogue | Check accessible root/mount, scanned subfolders, extensions, then selected game sources. Scan does not decode all files. |
| Missing/unreadable/no-audio source | Rescan and select a replacement. Only first audio stream of video files is used. |
| Manual choice locked | Its excerpt was already requested. Choose a future unprepared round or use current round recovery controls. |
| Binary blocked | Extract whole directory, verify platform/hash/origin and exact alert. Do not disable antivirus; use uvx if unresolved. |

Docker only sees mounted folders. The web UI cannot expose an unmounted host
path. Add a read-only mount under `/music` in a private Compose override, recreate
**only the Bridge**, then scan/select that subfolder. An added file inside an
existing mount only needs rescan. See [exact override example](docker.md#sources-dynamiques-et-réécoute).
Hidden files, links/junctions, unsupported extensions and NFC/ID collisions are
ignored/diagnosed. Limits: depth 32, 200,000 files, 64 scan folders, 8 Bridges.
Missing measured duration/tags is expected until a preparation/private listen.

Manual MC failure keeps the explicit selection and offers replacement, random
fallback, skip or end; it never silently chooses a different song. A manual round
waits for explicit launch even with auto-start enabled. Players receive no future
library details. Pending edits block launching until the server acknowledges them.
Repeats/source rules still apply; manual picks bypass random folder balancing.

Silence avoidance is bounded; inspect the first audio stream locally and try a
known source. Normalization adds CPU work; temporarily toggle these settings for
comparison. For browser audio: click the test, confirm hearing it, check device
volume/output, keep tab active, avoid sleep/background throttling. Bluetooth delay
can be compensated locally for subsequent clips; it never changes score/timing.
AAC is the default. Automated WebKit is not physical Safari/iOS validation.

## Upgrade, backup and rollback

Stop outside a game, export validated results, record version and Compose options.
Privately back up native `.env`, `STATE_DIR` (default `.local/state`), Bridge config
and backups, Caddy config/storage. For Docker preserve environment/overrides and
the actual project volumes `app_data`, `bridge_data`, `caddy_data`, `caddy_config`.
Use `docker compose --env-file .local/docker/hosting.env config --volumes` and
`docker volume ls` to identify them. Back up stopped volumes using your Docker
backup tooling; do not assume Docker Desktop's internal filesystem path.
**Never use `down -v` to preserve a session.**

Update to the verified server revision, rebuild with the locked Python/npm files
or matching Docker profiles, keep secrets and state, replace the whole Bridge
archive or pin the Python release, and reload browser tabs. Check version, local
doctor and registration outside a game, then test synthetic audio.

V0.5 uses software `0.5.0.dev0`, protocol 10 and admitted range 10 to 10. Inspect
`/api/compatibility`, update all components and reload stale tabs. No mixed protocol
or automatic downgrade; this development version is unpublished and does not freeze
the protocol. Snapshot **8** reads 1/2/3/4/5/6/7/8; history **2** migrates old/version-1 records.
Unknown future formats stop startup and never silently select an older backup.
Known corruption tries `session.previous.json`; preserve files if both are invalid.
Current playback returns as interrupted review, with no persisted audio or auto-start.

Back up **all of `STATE_DIR`**, including `bridge-credentials.json`, to retain
revocations and rotations. Its private registry is authoritative over old environment
secrets. Changing game/host passwords invalidates saved browser sessions; rotating
one Bridge secret does not. Do not share a UUID between processes or edit the registry
concurrently. Issued identity files contain raw secrets and require private storage.

History is immutable at final validation, host-only and loaded on demand: at most
50 games, 90 days and 16 MiB, without audio. Confirmed deletion removes records from
both managed snapshots, but not exported files, external backups or current results.
Snapshots are capped at 64 MiB each; allow up to 256 MiB for both copies and temporary
writes. Combined stored catalogues are capped at 200,000 tracks. See [V0.5](v0.5.en.md).

Rollback to V0.3 requires its entire server/web/Bridge installation **and the
pre-upgrade state backup**: it cannot read snapshot 8. Keep a private recent copy;
new answers cannot be merged automatically. Restore V0.5 backups with a compatible
V0.5 installation and preserved registry/secrets. Verify health, host identity,
catalogues and exports. Host review remains available; uncertain automatic matches require review.

## Report safely

Share redacted doctor JSON, versions, OS/architecture, error code and reproduction
steps. Do not share config.toml/backups, `.env`, secret headers/cookies, entire
catalogue, music root, snapshot or TLS keys. Verbose paths and browser traces may
contain private data; inspect/redact first. Security issues follow
[SECURITY.md](../SECURITY.md). Publishing requirements and defective-release
procedure are in [releasing.md](releasing.md).

See [automatic scoring](automatic-scoring.en.md) for optional matching, aliases and
finale waves, and [local CA trust](local-certificate.en.md) for LAN phones. Update
all components together to protocol 10 and back up state before snapshot-8 migration.
