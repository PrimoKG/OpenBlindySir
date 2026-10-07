# OpenBlindySir Bridge

Connect your local music library to your own OpenBlindySir server. Full source
files stay on this computer. Only short, reencoded audio clips are uploaded.

This development version is not published yet. From the repository root, run
`uv sync --locked`, then `uv run openblindysir-bridge --version`. Use
`uv run openblindysir-bridge init --credentials IDENTITY_PATH.toml`, then
`uv run openblindysir-bridge run --credentials IDENTITY_PATH.toml`, with a private
identity file issued by the host for this Bridge. Keep its UUID and secret private.
Update server, Bridge and web UI together: **protocol 8**.

After publication on PyPI, run `uvx openblindysir-bridge`. The first interactive
run starts the French setup wizard. Use `--help`, `--version`, `init`,
`check-config`, `check-ffmpeg` or `doctor` at any time.

Requires CPython 3.12–3.14 and separately installed FFmpeg/ffprobe 9.0.2 or newer.
The package does not include FFmpeg. AAC is required; Opus is optional.

See the [English installation guide](https://github.com/PrimoKG/OpenBlindySir/blob/main/docs/bridge-installation.en.md)
or [guide français](https://github.com/PrimoKG/OpenBlindySir/blob/main/docs/bridge-installation.md)
for native binaries, FFmpeg, private configuration and compatibility, and
the [troubleshooting guide](https://github.com/PrimoKG/OpenBlindySir/blob/main/docs/troubleshooting.md).

OpenBlindySir is self-hosted, open source and licensed under MIT.
