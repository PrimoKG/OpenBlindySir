"""Long source scans must leave the control channel responsive and stay bounded."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from unittest.mock import Mock

import pytest

from openblindysir_bridge.client import BridgeClient
from openblindysir_bridge.urls import validate_server_url


def client_for_scan(rescan: Callable[[list[str] | None], Awaitable[None]]) -> BridgeClient:
    return BridgeClient(
        server=validate_server_url("http://localhost:8000"),
        secret="example-secret",
        bridge_id="12345678-1234-1234-1234-123456789abc",
        name="Example",
        formats=[],
        catalog=Mock(),
        runner=Mock(),
        rescan=rescan,
    )


def test_slow_scan_does_not_block_heartbeat_or_audio_cancellation() -> None:
    async def run() -> None:
        started, release = asyncio.Event(), asyncio.Event()

        async def rescan(_: list[str] | None) -> None:
            started.set()
            await release.wait()

        client = client_for_scan(rescan)
        scan = asyncio.create_task(client._handle('{"t":"SCAN_SOURCES","folders":["Music"]}'))
        try:
            await asyncio.wait_for(started.wait(), 1)
            await asyncio.wait_for(asyncio.shield(scan), 0.1)
            await client._handle('{"t":"PING","c":42}')
            assert json.loads(client._outbox.get_nowait()) == {"t": "PONG", "c": 42.0}
            await client._handle('{"t":"CANCEL","job_id":"j_000001"}')
            client.runner.cancel.assert_called_once_with("j_000001")
        finally:
            release.set()
            await scan
            await client._stop_scans()

    asyncio.run(run())


def test_source_commands_are_serialized_and_a_flood_stays_bounded() -> None:
    async def run() -> None:
        started, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
        calls: list[list[str] | None] = []
        active = 0

        async def rescan(folders: list[str] | None) -> None:
            nonlocal active
            active += 1
            assert active == 1
            calls.append(folders)
            if len(calls) == 1:
                started.set()
                await release.wait()
            active -= 1
            if len(calls) == 5:
                finished.set()

        client = client_for_scan(rescan)
        await client._handle('{"t":"SCAN_SOURCES","folders":["A"]}')
        try:
            await asyncio.wait_for(started.wait(), 1)
            for index in range(20):
                await client._handle(json.dumps({"t": "SCAN_SOURCES", "folders": [str(index)]}))
            assert calls == [["A"]]
            assert client.status.ignored_messages == 16
            release.set()
            await asyncio.wait_for(finished.wait(), 1)
            assert calls == [["A"], ["0"], ["1"], ["2"], ["3"]]
        finally:
            await client._stop_scans()

    asyncio.run(run())


def test_losing_a_connection_cancels_scan_and_drops_queued_folder_changes() -> None:
    async def run() -> None:
        started, cancelled, fresh = asyncio.Event(), asyncio.Event(), asyncio.Event()
        calls = []

        async def rescan(folders: list[str] | None) -> None:
            calls.append(folders)
            if folders == ["A"]:
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            else:
                fresh.set()

        client = client_for_scan(rescan)
        await client._handle('{"t":"SCAN_SOURCES","folders":["A"]}')
        try:
            await asyncio.wait_for(started.wait(), 1)
            await client._handle('{"t":"SCAN_SOURCES","folders":["B"]}')
            await client._stop_scans()
            assert cancelled.is_set()
            await client._handle('{"t":"SCAN_SOURCES","folders":["C"]}')
            await asyncio.wait_for(fresh.wait(), 1)
            assert calls == [["A"], ["C"]]
        finally:
            await client._stop_scans()

    asyncio.run(run())


def test_scan_exception_leaves_later_commands_and_heartbeat_working() -> None:
    async def run() -> None:
        finished = asyncio.Event()

        async def rescan(folders: list[str] | None) -> None:
            if folders == ["A"]:
                raise OSError("synthetic failure")
            finished.set()

        client = client_for_scan(rescan)
        try:
            await client._handle('{"t":"SCAN_SOURCES","folders":["A"]}')
            await client._handle('{"t":"SCAN_SOURCES","folders":["B"]}')
            await asyncio.wait_for(finished.wait(), 1)
            await client._handle('{"t":"PING","c":7}')
            assert json.loads(client._outbox.get_nowait())["t"] == "PONG"
            assert client.status.last_error == "OSError"
        finally:
            await client._stop_scans()

    asyncio.run(run())


def test_slow_catalog_upload_keeps_heartbeat_working_and_coalesces_stale_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        started, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
        tokens = []

        async def upload(token: str) -> int:
            tokens.append(token)
            if len(tokens) == 1:
                started.set()
                await release.wait()
            else:
                finished.set()
            return 204

        client = client_for_scan(Mock())
        monkeypatch.setattr(client, "upload_catalog", upload)

        def welcome(token: str) -> str:
            return json.dumps(
                {
                    "t": "WELCOME",
                    "clip_format": "aac",
                    "bitrate": 128,
                    "limits": {"clip_min_s": 5, "clip_max_s": 60, "max_clip_bytes": 2097152},
                    "catalog_needed": True,
                    "catalog_upload_token": token,
                }
            )

        handling = asyncio.create_task(client._handle(welcome("A" * 43)))
        try:
            await asyncio.wait_for(started.wait(), 1)
            await asyncio.wait_for(asyncio.shield(handling), 0.1)
            await client._handle('{"t":"PING","c":8}')
            assert json.loads(client._outbox.get_nowait()) == {"t": "PONG", "c": 8.0}
            await client._handle(welcome("B" * 43))
            await client._handle(welcome("C" * 43))
            release.set()
            await asyncio.wait_for(finished.wait(), 1)
            assert tokens == ["A" * 43, "C" * 43]
        finally:
            release.set()
            await handling
            await client._stop_catalog_uploads()

    asyncio.run(run())


@pytest.mark.parametrize("busy", [2, 10])
def test_catalog_busy_retry_preserves_token_and_stays_bounded(monkeypatch, busy) -> None:
    from openblindysir_bridge import client as module  # noqa: PLC0415

    async def run() -> None:
        tokens, delays = [], []

        async def upload(token):
            tokens.append(token)
            return 429 if len(tokens) <= busy else 204

        async def sleep(delay):
            delays.append(delay)

        client = client_for_scan(Mock())
        client._catalog_token = "synthetic"
        monkeypatch.setattr(client, "upload_catalog", upload)
        monkeypatch.setattr(module.asyncio, "sleep", sleep)
        await client._upload_catalogs()
        assert tokens == ["synthetic"] * min(busy + 1, 4)
        assert delays == [0.25, 0.5, 1][: min(busy, 3)]
        assert client.status.last_error == (None if busy == 2 else "CatalogUpload429")

    asyncio.run(run())
