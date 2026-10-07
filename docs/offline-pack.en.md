# Precompiled Docker pack

This is a local validation candidate, not a signed public release. The pack contains server, Bridge and Caddy images, their identities and platforms, launchers and FR/EN guides. Hosts do not need Python, Node or FFmpeg and do not compile the application. Docker with Compose is still required. The pack built here targets Linux/amd64; other architectures need separately tested packs.

## Windows installation

1. Install Docker Desktop from its official source and start its Linux engine.
2. Check the pack’s source and its checksum obtained independently of the download. `SHA256SUMS` detects modified files; a manifest from the same download does not authenticate its author. This pack is unsigned.
3. Extract into a user-owned directory and run `powershell -File .\tools\load-pack.ps1`. All files are checked before loading, followed by Docker image identity checks.
4. Run `powershell -File .\tools\party-assistant.ps1`. **Configurer / Setup** asks for the music folder and LAN/VPN address and generates secrets. **Démarrer / Start** starts without building. Status, Open, Stop and Certificate are available in the same window. Configuration passwords are private: do not share a screenshot of this window.
5. Explicitly approve the local authority on trusted devices using [the certificate guide](local-certificate.en.md). No authority is silently installed. Music is mounted read-only; select only a music directory.

Linux/macOS: `sh tools/load-pack.sh`, then `sh tools/docker-host.sh init --address ADDRESS:8443 --music-dir /path/to/music --no-build` and `sh tools/docker-host.sh start --no-build`. The shell checks files and image identities. The graphical assistant is Windows-only. Docker Desktop licensing depends on your organization.

## Updates and rollback

**Backup**, **Update** and **Rollback** run `tools/pack-maintenance.ps1`. Private backups include state, configuration, mounts and image identities with checksums. Update selects a separate verified pack directory. Rollback requires explicit confirmation, checks hashes and the target volume, and backs up current state before replacing data. Previous images must still exist in Docker. These backups do not replace an external backup of volumes and the HTTPS authority.

The pack’s compose file uses pack-specific image tags. Keep the previous pack, private `.local/docker/hosting.env` and `sources.override.yaml` when present.

Before updating, stop with the launcher and back up the Docker volumes, especially `app_data`, the private configuration files and Caddy’s authority. Never use `down -v`. A local state copy before shutdown can be made with `docker cp openblindysir-app-1:/data/state ./private-state-backup`; do not publish this backup.

Verify and load the new pack, copy the private configuration into its `.local/docker/`, then Start. Existing volumes are reused with the same Compose project name, `openblindysir`, declared in compose.

To roll back, stop the services, restore the state backup compatible with the older image into its volume, then start the previous pack with its previous configuration. **Protocol 10 writes snapshot format 8 and reads formats 1–8. Protocol 9 must not receive a format 8 snapshot: restore its format 7 backup.** Scores and responses return to the backup’s date.

Signing a native installer and publishing tested multiarchitecture packs remain release steps. `tools/distribution_pack.py` does not publish externally.
