# Base images are fixed by multi-platform digest; application dependencies use lockfiles.
FROM caddy:2-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f AS proxy
RUN apk add --no-cache zlib=1.3.2-r1

FROM node:24-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv@sha256:f513a91fc62fe7c17567eee97230dd198e43edb8a9fbecca843714a4358fe1bc AS uv
FROM python:3.13-slim-trixie@sha256:3dd7cc108ec1493442514f5c2a871af6af0ec31d768ff6e378a93340c3b3db5f AS python-build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /workspace
COPY pyproject.toml uv.lock VERSION LICENSE ./
COPY protocol/ protocol/
COPY server/ server/
COPY bridge/ bridge/

FROM python-build AS server-build
RUN uv sync --locked --no-dev --no-editable --package openblindysir-server

FROM python-build AS bridge-build
RUN uv sync --locked --no-dev --no-editable --package openblindysir-bridge

# The distribution FFmpeg pulls in image/XML/device/network libraries unused by the Bridge.
# Build a pinned upstream release with only our local containers and audio operations.
FROM python:3.13-slim-trixie@sha256:3dd7cc108ec1493442514f5c2a871af6af0ec31d768ff6e378a93340c3b3db5f AS audio-build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential nasm pkg-config libopus-dev xz-utils gnupg gpgv \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /sources
ADD --checksum=sha256:8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz ffmpeg.tar.xz
ADD --checksum=sha256:d617fd94ea354dadd2a8bb16243d37c44e1e9729b06b6ad58fe30bfb0fa943f2 https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz.asc ffmpeg.tar.xz.asc
ADD --checksum=sha256:397b3becedcd5a98769967ff1ff8501ddc89f8368b8f766e4701377d7dbaabe5 https://ffmpeg.org/ffmpeg-devel.asc ffmpeg-devel.asc
COPY tools/build_audio_ffmpeg.sh /sources/build_audio_ffmpeg.sh
RUN gpg --batch --with-colons --import-options show-only --import ffmpeg-devel.asc \
    | grep -q '^fpr:::::::::FCF986EA15E6E293A5644F10B4322F04D67658D8:' \
    && gpg --batch --dearmor < ffmpeg-devel.asc > ffmpeg.gpg \
    && gpgv --keyring /sources/ffmpeg.gpg ffmpeg.tar.xz.asc ffmpeg.tar.xz \
    && tar -xf ffmpeg.tar.xz && cd ffmpeg-9.0.2 && sh /sources/build_audio_ffmpeg.sh

FROM python:3.13-slim-trixie@sha256:3dd7cc108ec1493442514f5c2a871af6af0ec31d768ff6e378a93340c3b3db5f AS runtime
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
# Do not import a potentially oversized DHCP/VPN search domain into glibc's resolver.
# Deployment URLs use an IP address or a fully qualified hostname.
ENV PATH="/workspace/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 LOCALDOMAIN="."
RUN groupadd --gid 10001 openblindysir && useradd --uid 10001 --gid 10001 --no-create-home openblindysir
WORKDIR /opt/openblindysir
LABEL org.opencontainers.image.title="OpenBlindySir" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/PrimoKG/OpenBlindySir"

FROM runtime AS bridge
RUN apt-get update && apt-get install -y --no-install-recommends libopus0 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir /data && chown 10001:10001 /data
COPY --from=audio-build /opt/audio-ffmpeg/ /usr/local/
COPY --from=bridge-build /workspace/.venv /workspace/.venv
COPY tools/docker_bridge.py /opt/tools/docker_bridge.py
COPY tools/check_audio_runtime.py /opt/tools/check_audio_runtime.py
ENV OPENBLINDYSIR_BRIDGE_CONFIG=/data/config.toml OPENBLINDYSIR_BRIDGE_DIR=/music
USER 10001:10001
RUN python /opt/tools/check_audio_runtime.py
ENTRYPOINT ["python", "/opt/tools/docker_bridge.py"]

FROM runtime AS app
RUN mkdir /data && chown 10001:10001 /data
COPY --from=server-build /workspace/.venv /workspace/.venv
COPY --from=web-build /web/dist /opt/openblindysir/web
COPY tools/host_pc.py tools/docker_config.py /opt/tools/
ENV STATIC_DIR=/opt/openblindysir/web BIND_HOST=127.0.0.1 PORT=8000 DEV_MODE=0
USER 10001:10001
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=12 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"
CMD ["openblindysir-server", "serve"]
