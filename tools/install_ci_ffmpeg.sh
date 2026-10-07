#!/bin/sh
# Full FFmpeg for synthetic fixtures/native tests; never included in release archives.
set -eu
prefix="$(pwd)/.local/ci-ffmpeg"
jobs=2
case "$(uname -s)" in
    Darwin) jobs="$(sysctl -n hw.logicalcpu)" ;;
    Linux) jobs="$(getconf _NPROCESSORS_ONLN)" ;;
esac
# Bound memory use on shared runners while avoiding slow dual-thread Mac builds.
if [ "$jobs" -gt 4 ]; then jobs=4; fi
if [ ! -x "$prefix/bin/ffmpeg" ] || ! "$prefix/bin/ffmpeg" -version | head -n1 | grep -q 'version 9.0.2 '; then
    mkdir -p "$prefix/build"
    cd "$prefix/build"
    curl --fail --location --proto '=https' --tlsv1.2 --output source.tar.xz https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz
    checksum='8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e  source.tar.xz'
    # macOS also ships a BSD sha256sum without GNU --strict; prefer shasum.
    if command -v shasum >/dev/null 2>&1; then
        printf '%s\n' "$checksum" | shasum -a 256 --check --strict
    else
        printf '%s\n' "$checksum" | sha256sum --check --strict
    fi
    tar -xf source.tar.xz
    cd ffmpeg-9.0.2
    ./configure --prefix="$prefix" --disable-autodetect --disable-doc --disable-debug \
        --enable-libmp3lame --enable-libopus --enable-libvorbis
    make -j"$jobs"
    make install
fi
if [ -n "${GITHUB_PATH:-}" ]; then
    printf '%s\n' "$prefix/bin" >> "$GITHUB_PATH"
fi
"$prefix/bin/ffmpeg" -version | head -n1
"$prefix/bin/ffprobe" -version | head -n1
