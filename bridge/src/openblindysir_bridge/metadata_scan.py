"""Bounded local tag discovery; never infer answers from filenames or send paths."""

import asyncio
from dataclasses import replace

from openblindysir_bridge import ffmpeg
from openblindysir_bridge.catalog import LocalCatalog
from openblindysir_bridge.sandbox import Sandbox, SandboxError
from openblindysir_protocol.bridge import Tags


async def enrich_catalog(
    catalog: LocalCatalog,
    sandbox: Sandbox,
    tools: ffmpeg.FfmpegTools,
    cache: dict[tuple[str, int, int], Tags | None],
) -> LocalCatalog:
    """Two workers, 5 s/file, process output bounded by run_bounded; cache by revision."""
    pending = iter(catalog.entries.items())
    metadata: dict[str, Tags] = {}

    async def worker() -> None:
        for tid, entry in pending:
            key = (entry.relpath, entry.size, entry.mtime_ns)
            if key not in cache:
                tags = None
                try:
                    path = sandbox.resolve_for_open(entry)
                    result = await ffmpeg.run_bounded(ffmpeg.probe_argv(tools, path), 5)
                    probe = ffmpeg.parse_probe(result.stdout) if result.returncode == 0 else None
                    if probe and probe.has_audio:
                        tags = Tags(
                            title=probe.title,
                            artist=probe.artist,
                            album=probe.album,
                            featuring=probe.featuring,
                            year=probe.year,
                        )
                except (OSError, SandboxError):
                    pass
                cache[key] = tags
            cached = cache[key]
            if cached is not None:
                metadata[tid] = cached

    await asyncio.gather(worker(), worker())
    live = {(e.relpath, e.size, e.mtime_ns) for e in catalog.entries.values()}
    for key in list(cache):
        if key not in live:
            del cache[key]
    return replace(catalog, metadata=metadata)
