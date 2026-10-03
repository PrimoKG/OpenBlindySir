"""A hostile or slow control endpoint cannot grow buffers or reuse an old session."""

import asyncio
from unittest.mock import Mock

import pytest

from openblindysir_bridge import client as client_module
from openblindysir_bridge.catalog import LocalCatalog
from openblindysir_bridge.client import BridgeClient
from openblindysir_bridge.urls import validate_server_url
from openblindysir_protocol.bridge import BridgePong
from openblindysir_protocol.enums import ClipFormat


def client() -> BridgeClient:
    return BridgeClient(
        validate_server_url("http://localhost:8000"),
        "synthetic",
        "12345678-1234-1234-1234-123456789abc",
        "Example",
        [ClipFormat.AAC],
        lambda: LocalCatalog({}, "0" * 64, 0),
        Mock(allow_full_review=False),
    )


class SlowSocket:
    def __init__(self, *, failed_writer: bool = False) -> None:
        self.failed_writer = failed_writer
        self.hello = False

    async def send(self, _: str) -> None:
        if not self.hello:
            self.hello = True
            return
        if self.failed_writer:
            raise ConnectionError("synthetic transport failure")
        await asyncio.Event().wait()

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if self.failed_writer:
            await asyncio.Event().wait()
        await asyncio.sleep(0)
        return '{"t":"PING","c":1}'


def test_outbox_flood_stays_bounded_and_fails_session() -> None:
    async def run() -> None:
        c = client()
        with pytest.raises(ConnectionError):
            await asyncio.wait_for(c._session(SlowSocket()), 1)
        assert c._outbox.empty()
        assert c.welcome is None
        assert c._ws is None

    asyncio.run(run())


def test_writer_failure_aborts_reader_and_drops_old_messages() -> None:
    async def run() -> None:
        c = client()
        task = asyncio.create_task(c._session(SlowSocket(failed_writer=True)))
        await asyncio.sleep(0)
        c.send(BridgePong(t="PONG", c=1))
        try:
            with pytest.raises(ConnectionError):
                await asyncio.wait_for(asyncio.shield(task), 0.5)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert c._outbox.empty()

    asyncio.run(run())


def test_long_outage_keeps_backoff_bounded_without_exponent_overflow(monkeypatch) -> None:
    delays = []

    def unavailable(*args, **kwargs):
        raise OSError("synthetic outage")

    async def sleep(delay):
        delays.append(delay)
        if len(delays) == 1030:
            raise asyncio.CancelledError

    monkeypatch.setattr(client_module.websockets, "connect", unavailable)
    monkeypatch.setattr(client_module.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(client().run_forever())
    assert len(delays) == 1030
    assert all(0 < delay <= 36 for delay in delays)
