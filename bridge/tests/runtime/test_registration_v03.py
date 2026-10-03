"""Authentication/protocol failures stop safely; registration never requests audio."""

import asyncio
import json
from unittest.mock import Mock

import pytest
import websockets
from websockets.datastructures import Headers
from websockets.http11 import Response

from openblindysir_bridge import diagnostics, ffmpeg
from openblindysir_bridge.catalog import LocalCatalog
from openblindysir_bridge.client import BridgeClient, BridgeConnectionRejected
from openblindysir_bridge.urls import validate_server_url
from openblindysir_protocol.bridge import Welcome
from openblindysir_protocol.enums import ClipFormat
from openblindysir_protocol.version import PROTOCOL_VERSION


class Socket:
    def __init__(self, response):
        self.response = response
        self.sent = []

    async def __aenter__(self):
        if isinstance(self.response, Exception):
            raise self.response
        return self

    async def __aexit__(self, *args):
        pass

    async def send(self, text):
        self.sent.append(json.loads(text))

    async def recv(self):
        return json.dumps(self.response)


def test_permanent_authentication_failure_is_not_retried(monkeypatch):
    socket = Socket(websockets.exceptions.InvalidStatus(Response(403, "Forbidden", Headers())))
    connect = Mock(return_value=socket)
    monkeypatch.setattr(websockets, "connect", connect)
    client = BridgeClient(
        server=validate_server_url("http://localhost:8000"),
        secret="synthetic-only",
        bridge_id="12345678-1234-1234-1234-123456789abc",
        name="Test",
        formats=[],
        catalog=Mock(),
        runner=Mock(),
    )
    with pytest.raises(BridgeConnectionRejected, match="authentication"):
        asyncio.run(client.run_forever())
    connect.assert_called_once()


def test_registration_hello_is_current_and_creates_no_prepare(monkeypatch, tmp_path):
    from test_distribution_cli import config  # noqa: PLC0415

    cfg = config(tmp_path)
    socket = Socket(
        {
            "t": "WELCOME",
            "clip_format": "aac",
            "bitrate": 128,
            "limits": {"clip_min_s": 5, "clip_max_s": 60, "max_clip_bytes": 4194304},
            "catalog_needed": False,
            "catalog_upload_token": None,
        }
    )
    Welcome.model_validate_json(json.dumps(socket.response))
    monkeypatch.setattr(websockets, "connect", Mock(return_value=socket))
    catalog = LocalCatalog({}, "0" * 64, 0)
    result = asyncio.run(
        diagnostics.check_connection(
            cfg,
            ffmpeg.FfmpegInfo("FFmpeg test", frozenset({"aac"})),
            catalog,
        )
    )
    assert result.ok
    assert len(socket.sent) == 1
    assert socket.sent[0]["protocol"] == PROTOCOL_VERSION
    assert socket.sent[0]["track_count"] == 0
    assert socket.sent[0]["formats"] == [ClipFormat.AAC.value]
