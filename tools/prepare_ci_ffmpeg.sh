#!/bin/sh
# Linux CI only: bounded package-mirror operations before the verified source build.
set -eu
sudo apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=30 \
    -o Acquire::https::Timeout=30 -o Acquire::Languages=none update
sudo apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=30 \
    -o Acquire::https::Timeout=30 install -y \
    build-essential nasm pkg-config libmp3lame-dev libopus-dev libvorbis-dev xz-utils curl
sh tools/install_ci_ffmpeg.sh
