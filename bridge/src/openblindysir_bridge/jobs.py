"""Job runner (spec §11): one job at a time, queue of 4, timeouts, cancellation.

Pipeline: lookup → sandbox → ffprobe → start point → ffmpeg → output checks → upload.
The temporary clip is deleted in every case. Nothing about paths is ever sent.
"""

import asyncio
import contextlib
import hashlib
import os
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from openblindysir_bridge import ffmpeg
from openblindysir_bridge.catalog import LocalCatalog
from openblindysir_bridge.clip import ClipRequest, TooShortError, compute_start
from openblindysir_bridge.sandbox import Sandbox, SandboxError
from openblindysir_protocol.bridge import JobDone, JobFailed, JobProgress, Prepare, Tags
from openblindysir_protocol.enums import ClipFormat, JobFailureCode, JobStage

QUEUE_MAX = 4
MIN_OUTPUT_RATIO = 0.5
Sender = Callable[[JobProgress | JobDone | JobFailed], None]
Uploader = Callable[[str, str, Path, str, str], Awaitable[int]]  # url, token, file, sha, mime


class JobError(Exception):
    def __init__(self, code: JobFailureCode, detail: str = "") -> None:
        super().__init__(code.value)
        self.code = code
        self.detail = detail  # console only, with --verbose-paths


@dataclass
class Faults:
    """Fault injection for integration tests (``--demo`` only)."""

    corrupt_upload: int | None = None
    delete_track: int | None = None
    slow_encode_ms: int = 0


@dataclass
class JobStats:
    ok: int = 0
    failed: int = 0
    last_track: str | None = None
    last_seconds: float | None = None
    last_failure: str | None = None


@dataclass
class _Job:
    prepare: Prepare
    request: ClipRequest
    number: int


@dataclass
class JobRunner:
    tools: ffmpeg.FfmpegTools
    sandbox: Sandbox
    catalog: Callable[[], LocalCatalog]
    uploader: Uploader
    send: Sender
    tmpdir: Path
    faults: Faults = field(default_factory=Faults)
    stats: JobStats = field(default_factory=JobStats)
    on_detail: Callable[[str], None] | None = None
    _queue: deque[_Job] = field(default_factory=deque)
    _wake: asyncio.Event = field(default_factory=asyncio.Event)
    _current: tuple[str, asyncio.Task[None]] | None = None
    _count: int = 0

    def submit(self, prepare: Prepare, request: ClipRequest) -> JobFailureCode | None:
        if len(self._queue) >= QUEUE_MAX:
            return JobFailureCode.QUEUE_FULL
        self._count += 1
        self._queue.append(_Job(prepare, request, self._count))
        self._wake.set()
        return None

    def cancel(self, job_id: str) -> None:
        for job in list(self._queue):
            if job.prepare.job_id == job_id:
                self._queue.remove(job)
                self.send(JobFailed(t="JOB_FAILED", job_id=job_id, code=JobFailureCode.CANCELLED))
                return
        if self._current is not None and self._current[0] == job_id:
            self._current[1].cancel()

    def clear(self) -> None:
        """Connection lost: queued jobs are dropped (the server fails them itself)."""
        self._queue.clear()
        if self._current is not None:
            self._current[1].cancel()

    async def run(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            while self._queue:
                job = self._queue.popleft()
                task = asyncio.create_task(self._execute(job))
                self._current = (job.prepare.job_id, task)
                try:
                    await task
                except asyncio.CancelledError:
                    if asyncio.current_task() and asyncio.current_task().cancelling():  # type: ignore[union-attr]
                        raise
                    self._failed(job, JobFailureCode.CANCELLED, "annulé")
                finally:
                    self._current = None

    def _progress(self, job: _Job, stage: JobStage) -> None:
        self.send(JobProgress(t="JOB_PROGRESS", job_id=job.prepare.job_id, stage=stage))

    def _failed(self, job: _Job, code: JobFailureCode, detail: str) -> None:
        self.stats.failed += 1
        self.stats.last_failure = f"{job.prepare.track_id[:8]}… {code.value}"
        if self.on_detail is not None and detail:
            self.on_detail(detail)
        self.send(JobFailed(t="JOB_FAILED", job_id=job.prepare.job_id, code=code))

    async def _execute(self, job: _Job) -> None:
        loop = asyncio.get_running_loop()
        started = loop.time()
        suffix = ".webm" if job.request.clip_format is ClipFormat.OPUS else ".m4a"
        out = self.tmpdir / f"{job.prepare.job_id}{suffix}"
        try:
            done = await self._pipeline(job, out)
        except JobError as exc:
            self._failed(job, exc.code, exc.detail)
            return
        except Exception as exc:
            self._failed(job, JobFailureCode.DECODE_ERROR, f"erreur interne : {type(exc).__name__}")
            return
        finally:
            with contextlib.suppress(OSError):
                out.unlink(missing_ok=True)
        self.stats.ok += 1
        self.stats.last_track = job.prepare.track_id
        self.stats.last_seconds = loop.time() - started
        self.send(done)

    async def _pipeline(self, job: _Job, out: Path) -> JobDone:  # noqa: PLR0915
        prepare, request = job.prepare, job.request
        self._progress(job, JobStage.PROBING)
        entry = self.catalog().lookup(prepare.track_id)
        if entry is None:
            raise JobError(JobFailureCode.NOT_FOUND, "piste inconnue")
        if self.faults.delete_track == job.number:
            with contextlib.suppress(OSError):
                os.remove(os.path.join(self.sandbox.root_real, *entry.fs_parts))
        try:
            real = self.sandbox.resolve_for_open(entry)
        except SandboxError as exc:
            raise JobError(JobFailureCode.NOT_FOUND, f"sandbox : {exc} ({entry.relpath})") from exc
        probe_run = await ffmpeg.run_bounded(
            ffmpeg.probe_argv(self.tools, real), ffmpeg.PROBE_TIMEOUT_S
        )
        if probe_run.returncode is None:
            raise JobError(JobFailureCode.TIMEOUT, "ffprobe : délai dépassé")
        probe = ffmpeg.parse_probe(probe_run.stdout) if probe_run.returncode == 0 else None
        if probe is None or not probe.has_audio:
            raise JobError(JobFailureCode.DECODE_ERROR, f"ffprobe : {probe_run.stderr}")
        try:
            start, duration = compute_start(probe.duration_s, request.duration_s, request.fraction)
        except TooShortError as exc:
            raise JobError(JobFailureCode.TOO_SHORT, "piste trop courte") from exc
        if request.avoid_silence:
            for attempt in range(3):
                analysis = await ffmpeg.run_bounded(
                    ffmpeg.analysis_argv(self.tools, real, start, duration), ffmpeg.PROBE_TIMEOUT_S
                )
                if analysis.returncode is None:
                    raise JobError(JobFailureCode.TIMEOUT, "silence analysis timed out")
                if analysis.returncode != 0:
                    raise JobError(JobFailureCode.DECODE_ERROR, "silence analysis failed")
                silent, leading = ffmpeg.analyze_silence(analysis.stderr, duration)
                if not silent:
                    start = min(max(0, probe.duration_s - duration), start + leading)
                    break
                start, duration = compute_start(
                    probe.duration_s,
                    request.duration_s,
                    (request.fraction + (attempt + 1) * 0.31) % 0.999,
                )
            else:
                raise JobError(
                    JobFailureCode.SILENT_AUDIO, "no audible excerpt found after three attempts"
                )
        self._progress(job, JobStage.ENCODING)
        if self.faults.slow_encode_ms:
            await asyncio.sleep(self.faults.slow_encode_ms / 1000)
        argv = ffmpeg.encode_argv(
            self.tools,
            real,
            str(out),
            start=start,
            duration=duration,
            bitrate_kbps=request.bitrate_kbps,
            clip_format=request.clip_format,
            normalize_audio=request.normalize_audio,
        )
        encode_run = await ffmpeg.run_bounded(argv, ffmpeg.ENCODE_TIMEOUT_S)
        if encode_run.returncode is None:
            raise JobError(JobFailureCode.TIMEOUT, "ffmpeg : délai dépassé")
        if encode_run.returncode != 0 or not out.is_file():
            raise JobError(JobFailureCode.DECODE_ERROR, f"ffmpeg : {encode_run.stderr}")
        size = out.stat().st_size
        if size > request.max_bytes or size == 0:
            raise JobError(JobFailureCode.INVALID_UPLOAD, f"extrait de {size} octets")
        measured_run = await ffmpeg.run_bounded(
            ffmpeg.duration_argv(self.tools, str(out)), ffmpeg.PROBE_TIMEOUT_S
        )
        measured = (
            ffmpeg.parse_duration(measured_run.stdout) if measured_run.returncode == 0 else None
        )
        if measured is None or measured < MIN_OUTPUT_RATIO * duration:
            raise JobError(JobFailureCode.DECODE_ERROR, "extrait produit trop court")
        data = out.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if self.faults.corrupt_upload == job.number:
            # Altered bytes, announced sha256 unchanged: the server must reject the upload.
            out.write_bytes(data[:-1] + bytes([data[-1] ^ 0xFF]))
        self._progress(job, JobStage.UPLOADING)
        mime = "audio/webm" if request.clip_format is ClipFormat.OPUS else "audio/mp4"
        try:
            status = await self.uploader(
                prepare.upload_url, prepare.upload_token, out, digest, mime
            )
        except Exception as exc:
            raise JobError(JobFailureCode.INVALID_UPLOAD, f"upload : {type(exc).__name__}") from exc
        if not 200 <= status < 300:
            raise JobError(JobFailureCode.INVALID_UPLOAD, f"upload refusé ({status})")
        tags = Tags(title=probe.title, artist=probe.artist) if probe.title or probe.artist else None
        return JobDone(
            t="JOB_DONE",
            job_id=prepare.job_id,
            actual_start=round(start, 3),
            clip_duration=round(measured, 3),
            track_duration=round(probe.duration_s, 3),
            bytes=size,
            sha256=digest,
            tags=tags,
        )
