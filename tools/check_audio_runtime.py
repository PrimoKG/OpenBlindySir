"""Fail a Docker build if its audio-only FFmpeg gains network/video capabilities."""

import hashlib
import subprocess
from pathlib import Path

from openblindysir_bridge.ffmpeg import check, discover

SOURCE_SHA256 = "8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e"


def main() -> None:
    tools = discover()
    info = check(tools)
    assert info.version == "FFmpeg 9.0.2", "Unexpected FFmpeg release"
    for executable in (tools.ffmpeg, tools.ffprobe):
        protocols = subprocess.check_output(
            [executable, "-hide_banner", "-protocols"], text=True, timeout=10
        )
        names = {
            line.strip() for line in protocols.splitlines() if line.startswith(" ") and line.strip()
        }
        assert names == {"file"}, "Network or secondary file protocols enabled"
        decoders = subprocess.check_output(
            [executable, "-hide_banner", "-decoders"], text=True, timeout=10
        )
        assert not any(
            len(parts := line.split()) >= 2 and parts[0].startswith(("V", "S")) and parts[1] != "="
            for line in decoders.splitlines()
        ), "Video/subtitle decoding enabled"
    assert {"aac", "libopus", "flac"} <= info.encoders, "Audio/demo encoder missing"
    source = Path("/usr/local/share/licenses/ffmpeg/source.tar.xz")
    assert hashlib.sha256(source.read_bytes()).hexdigest() == SOURCE_SHA256
    print("PASS signed FFmpeg 9.0.2 source, audio codecs and file-only protocols")


if __name__ == "__main__":
    main()
