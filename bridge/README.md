# OpenBlindySir Bridge

Connect your local music library to your own OpenBlindySir server. Full source
files stay on this computer. Only short, reencoded audio clips are uploaded.

After publication on PyPI, run `uvx openblindysir-bridge`. The first interactive
run starts the French setup wizard. Use `--help`, `--version`, `init`,
`check-config`, `check-ffmpeg` or `doctor` at any time.

Requires CPython 3.12–3.14 and separately installed FFmpeg/ffprobe 4.4 or newer.
The package does not include FFmpeg. AAC is required; Opus is optional.

See the [installation guide](https://github.com/PrimoKG/OpenBlindySir/blob/main/docs/bridge-installation.md)
for native binaries, FFmpeg, private configuration and compatibility, and
the [troubleshooting guide](https://github.com/PrimoKG/OpenBlindySir/blob/main/docs/troubleshooting.md).

OpenBlindySir is self-hosted, open source and licensed under MIT.
