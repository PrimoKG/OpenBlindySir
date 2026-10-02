"""Corrupted or illegitimate clip uploads (spec §5.3, §8.1): never STORED, never served."""

import hashlib
import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from conftest import FAKE_M4A, Harness, bridge_hello, catalog, put_asset, put_catalog

from openblindysir_protocol.bridge import UPLOAD_TOKEN_TTL_S
from openblindysir_protocol.enums import AssetState

HELLO = json.dumps({"t": "HELLO", "client_version": "0.1.0", "protocol": 2})


def receive(ws: Any, t: str) -> dict[str, Any]:
    for _ in range(30):
        msg = ws.receive_json()
        if msg["t"] == t:
            return msg
    raise AssertionError(f"no {t}")


@dataclass
class Job:
    harness: Harness
    bridge: Any
    player_cookie: dict[str, str]
    prepare: dict[str, Any]

    @property
    def url(self) -> str:
        return str(self.prepare["upload_url"])

    @property
    def token(self) -> str:
        return str(self.prepare["upload_token"])

    @property
    def asset_id(self) -> str:
        return self.url.rsplit("/", 1)[-1]

    def state(self, asset_id: str | None = None) -> AssetState | None:
        info = self.harness.runtime.engine.asset_info(asset_id or self.asset_id)
        return None if info is None else info.state

    def served(self, asset_id: str | None = None) -> int:
        url = f"/api/audio/{asset_id or self.asset_id}"
        return self.harness.client.get(url, headers=self.player_cookie).status_code

    def next_prepare(self) -> dict[str, Any]:
        return receive(self.bridge, "PREPARE")


@pytest.fixture
def job(harness: Harness) -> Iterator[Job]:
    """A started game whose first PREPARE has been received by a fake Bridge."""
    body = catalog()
    _, host_token = harness.join("Yo")
    harness.elevate(host_token)
    _, player_token = harness.join("Ayoub")
    with harness.bridge_ws() as bridge:
        bridge.send_text(bridge_hello(body["catalog_hash"], 6))
        token = str(receive(bridge, "WELCOME")["catalog_upload_token"])
        assert put_catalog(harness, body, token).status_code == 204
        with harness.player_ws(host_token) as host:
            host.send_text(HELLO)
            receive(host, "STATE")
            for cmd, args in (
                (
                    "configure",
                    {
                        "rounds": 2,
                        "sources": [{"bridge_id": body["bridge_id"], "folder_prefix": ""}],
                    },
                ),
                ("start_game", {}),
            ):
                msg = {"t": "HOST", "cmd": cmd, "expected_phase": "LOBBY", "args": args}
                host.send_text(json.dumps(msg))
            prepare = receive(bridge, "PREPARE")
            yield Job(harness, bridge, harness.cookie(player_token), prepare)


def _put(job: Job, data: bytes, sha: str | None = None, token: str | None = None) -> Any:
    return job.harness.client.put(
        job.url,
        content=data,
        headers={
            "authorization": f"Bearer {token or job.token}",
            "x-content-sha256": sha or hashlib.sha256(data).hexdigest(),
        },
    )


@pytest.mark.parametrize(
    ("data", "sha"),
    [
        (b"ID3\x04" + b"\x00" * 200, None),  # wrong magic bytes (an MP3, not MP4)
        (b"OggS" + b"\x00" * 200, None),  # incoherent MIME: Ogg while the server expects AAC
        (FAKE_M4A[:-100], hashlib.sha256(FAKE_M4A).hexdigest()),  # truncated in transit
        (FAKE_M4A, "0" * 64),  # announced SHA-256 does not match
        (FAKE_M4A, "not-a-sha"),  # malformed announcement
    ],
    ids=["magic", "mime", "truncated", "sha_mismatch", "sha_malformed"],
)
def test_invalid_upload_is_never_stored_and_retried_once(
    job: Job, data: bytes, sha: str | None
) -> None:
    assert _put(job, data, sha).status_code == 400
    assert job.state() is not AssetState.STORED
    assert job.served() == 404
    retry = job.next_prepare()
    assert retry["track_id"] == job.prepare["track_id"]  # one retry of the same track
    assert retry["upload_url"] != job.prepare["upload_url"]  # with a fresh asset
    assert put_asset(job.harness, retry["upload_url"], retry["upload_token"]).status_code == 204


def test_second_invalid_upload_replaces_the_track(job: Job) -> None:
    assert _put(job, b"garbage" * 10).status_code == 400
    retry = job.next_prepare()
    assert (
        put_asset(job.harness, retry["upload_url"], retry["upload_token"], b"x" * 64).status_code
        == 400
    )
    replacement = job.next_prepare()
    assert replacement["track_id"] != job.prepare["track_id"]


def test_too_large_upload_refused(job: Job) -> None:
    job.harness.runtime.cache.max_item_bytes = 512
    assert _put(job, FAKE_M4A).status_code == 413  # declared Content-Length
    assert job.state() is not AssetState.STORED
    assert job.served() == 404


def test_streamed_upload_beyond_the_limit_refused(job: Job) -> None:
    job.harness.runtime.cache.max_item_bytes = 512

    def chunks() -> Iterator[bytes]:  # no Content-Length: the limit applies while reading
        yield FAKE_M4A[:400]
        yield FAKE_M4A[400:]

    response = job.harness.client.put(
        job.url,
        content=chunks(),
        headers={
            "authorization": f"Bearer {job.token}",
            "x-content-sha256": hashlib.sha256(FAKE_M4A).hexdigest(),
        },
    )
    assert response.status_code == 413
    assert job.state() is not AssetState.STORED


def test_wrong_token_consumes_nothing(job: Job) -> None:
    assert _put(job, FAKE_M4A, token="example-wrong-token").status_code == 403
    assert _put(job, FAKE_M4A).status_code == 204


def test_token_is_single_use(job: Job) -> None:
    assert _put(job, FAKE_M4A).status_code == 204
    assert _put(job, FAKE_M4A).status_code == 403  # replay of the same upload


def test_expired_token_refused(job: Job) -> None:
    job.harness.clock.advance(UPLOAD_TOKEN_TTL_S * 1000 + 1)
    assert _put(job, FAKE_M4A).status_code == 403
    assert job.state() is not AssetState.STORED


def test_token_of_another_asset_refused(job: Job) -> None:
    other = "/api/bridge/assets/a_" + "B" * 22  # an asset without any job
    response = job.harness.client.put(
        other,
        content=FAKE_M4A,
        headers={
            "authorization": f"Bearer {job.token}",
            "x-content-sha256": hashlib.sha256(FAKE_M4A).hexdigest(),
        },
    )
    assert response.status_code == 403
    assert job.state("a_" + "B" * 22) is None
    assert _put(job, FAKE_M4A).status_code == 204  # the real grant is untouched


def test_malformed_asset_id_is_not_found(job: Job) -> None:
    url = "/api/bridge/assets/..%2F..%2Fetc"
    response = job.harness.client.put(url, content=FAKE_M4A, headers={"authorization": "Bearer x"})
    assert response.status_code == 404


def test_rejections_never_log_the_token(job: Job, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        _put(job, FAKE_M4A, token="example-wrong-token")
        _put(job, b"garbage" * 10)
    text = caplog.text
    assert "upload_rejected" in text
    assert job.token not in text
    assert "example-wrong-token" not in text
