# Base images are fixed by multi-platform digest; application dependencies use lockfiles.
FROM node:24-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv@sha256:f513a91fc62fe7c17567eee97230dd198e43edb8a9fbecca843714a4358fe1bc AS uv
FROM python:3.13-slim-bookworm@sha256:5024f48ba9441d4b13a95d3945abc6365538e3a31109833367a1923523c6efed AS python-build
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

FROM python:3.13-slim-bookworm@sha256:5024f48ba9441d4b13a95d3945abc6365538e3a31109833367a1923523c6efed AS runtime
ENV PATH="/workspace/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN groupadd --gid 10001 openblindysir && useradd --uid 10001 --gid 10001 --no-create-home openblindysir
WORKDIR /opt/openblindysir
LABEL org.opencontainers.image.title="OpenBlindySir" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/PrimoKG/OpenBlindySir"

FROM runtime AS bridge
# FFmpeg belongs only to the Bridge image. Debian updates are installed at build time.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir /data && chown 10001:10001 /data
COPY --from=bridge-build /workspace/.venv /workspace/.venv
COPY tools/docker_bridge.py /opt/tools/docker_bridge.py
ENV OPENBLINDYSIR_BRIDGE_CONFIG=/data/config.toml OPENBLINDYSIR_BRIDGE_DIR=/music
USER 10001:10001
ENTRYPOINT ["python", "/opt/tools/docker_bridge.py"]

FROM runtime AS app
COPY --from=server-build /workspace/.venv /workspace/.venv
COPY --from=web-build /web/dist /opt/openblindysir/web
COPY tools/host_pc.py tools/docker_config.py /opt/tools/
ENV STATIC_DIR=/opt/openblindysir/web BIND_HOST=127.0.0.1 PORT=8000 DEV_MODE=0
USER 10001:10001
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=12 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"
CMD ["openblindysir-server", "serve"]
