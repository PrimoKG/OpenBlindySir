#!/bin/sh
# Only local containers and audio codecs: no video/image codecs, XML or network stack.
set -eu
./configure \
    --prefix=/opt/audio-ffmpeg \
    --disable-autodetect --disable-everything --disable-network --disable-iconv \
    --disable-doc --disable-debug --disable-swscale \
    --enable-ffmpeg --enable-ffprobe --enable-libopus \
    --enable-protocol=file \
    --enable-indev=lavfi \
    --enable-demuxer=mp3,flac,wav,mov,ogg,aiff,asf,aac,matroska,avi \
    --enable-decoder='aac*,ac3*,eac3,alac,flac,mp1*,mp2*,mp3*,opus,vorbis,wmav1,wmav2,wmapro,wmalossless,pcm_*,adpcm_*,dca,truehd,mlp,ape,wavpack,tta' \
    --enable-parser=aac,aac_latm,ac3,dca,flac,mpegaudio,opus,vorbis \
    --enable-encoder=aac,libopus,pcm_s16le,flac \
    --enable-muxer=mp4,ipod,webm,null,flac \
    --enable-filter=aresample,aformat,anull,atrim,asetpts,loudnorm,afade,silencedetect,volumedetect,sine,aevalsrc,anullsrc
make -j2
make install
mkdir -p /opt/audio-ffmpeg/share/licenses/ffmpeg
cp COPYING.LGPLv2.1 LICENSE.md /opt/audio-ffmpeg/share/licenses/ffmpeg/
cp ffbuild/config.log /opt/audio-ffmpeg/share/licenses/ffmpeg/config.log
# Ship exact corresponding source and build recipe with the binaries.
cp /sources/ffmpeg.tar.xz /opt/audio-ffmpeg/share/licenses/ffmpeg/source.tar.xz
cp /sources/ffmpeg.tar.xz.asc /sources/ffmpeg-devel.asc /opt/audio-ffmpeg/share/licenses/ffmpeg/
cp /sources/build_audio_ffmpeg.sh /opt/audio-ffmpeg/share/licenses/ffmpeg/
chmod 644 /opt/audio-ffmpeg/share/licenses/ffmpeg/*
