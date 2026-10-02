"""Shell test helpers: an app with a fake clock and sequential ids, plus protocol clients."""

import gzip
import hashlib
import json
import random
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from openblindysir_protocol.catalog_rules import compute_catalog_hash, compute_track_id
from openblindysir_server.config import Settings
from openblindysir_server.game import FakeClock, SequentialIds
from openblindysir_server.main import create_app

BLIND = "example-blind-password"
HOST = "example-host-password"
SECRET = "example-bridge-secret-0123456789abcdef"
ORIGIN = "http://localhost:8000"
BRIDGE_ID = "12345678-1234-1234-1234-123456789abc"


def settings_for_test(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "blind_password": BLIND,
        "host_password": HOST,
        "bridge_secret": SECRET,
        "dev_mode": True,
        "domain": None,
        "trusted_proxies": ("10.99.0.0/16",),
    }
    values.update(overrides)
    return Settings(**values)


class Harness:
    def __init__(self, client: TestClient, clock: FakeClock) -> None:
        self.client = client
        self.clock = clock

    @property
    def app(self) -> Any:
        return self.client.app

    @property
    def runtime(self) -> Any:
        return self.app.state.obs.runtime

    def join(self, nickname: str, password: str = BLIND) -> tuple[str, str]:
        """Returns (player_id, session token) without polluting the shared cookie jar."""
        response = self.client.post(
            "/api/session/join",
            json={"password": password, "nickname": nickname},
            headers={"origin": ORIGIN},
        )
        assert response.status_code == 200, response.text
        token = response.cookies["openblindysir_dev"]
        self.client.cookies.clear()
        return response.json()["player_id"], token

    def cookie(self, token: str) -> dict[str, str]:
        return {"cookie": f"openblindysir_dev={token}"}

    def elevate(self, token: str) -> None:
        response = self.client.post(
            "/api/session/host",
            json={"host_password": HOST},
            headers={"origin": ORIGIN, **self.cookie(token)},
        )
        assert response.status_code == 200, response.text
        self.client.cookies.clear()

    def player_ws(self, token: str) -> Any:
        return self.client.websocket_connect(
            "/api/ws", headers={"origin": ORIGIN, **self.cookie(token)}
        )

    def bridge_ws(self, secret: str = SECRET) -> Any:
        return self.client.websocket_connect(
            "/api/bridge/ws", headers={"authorization": f"Bearer {secret}"}
        )


def catalog(count: int = 6, folder: str = "Anime") -> dict[str, Any]:
    entries = []
    for index in range(count):
        relpath = f"{folder}/t{index}.flac"
        entries.append(
            {
                "track_id": compute_track_id(relpath),
                "relpath": relpath,
                "folder": folder,
                "ext": ".flac",
                "size": 100 + index,
            }
        )
    rows = [(e["track_id"], e["relpath"], e["size"]) for e in entries]
    return {"bridge_id": BRIDGE_ID, "catalog_hash": compute_catalog_hash(rows), "entries": entries}


def bridge_hello(catalog_hash: str, track_count: int) -> str:
    return json.dumps(
        {
            "t": "HELLO",
            "bridge_id": BRIDGE_ID,
            "name": "PC",
            "version": "0.1.0",
            "protocol": 1,
            "catalog_hash": catalog_hash,
            "track_count": track_count,
            "formats": ["aac"],
        }
    )


def put_catalog(h: Harness, body: dict[str, Any], token: str) -> Any:
    return h.client.put(
        "/api/bridge/catalog",
        content=gzip.compress(json.dumps(body).encode()),
        headers={
            "authorization": f"Bearer {SECRET}",
            "x-catalog-token": token,
            "content-encoding": "gzip",
            "content-type": "application/json",
        },
    )


FAKE_M4A = b"\x00\x00\x00\x18ftypM4A \x00\x00\x02\x00" + b"\x00" * 1000


def put_asset(h: Harness, upload_url: str, token: str, data: bytes = FAKE_M4A) -> Any:
    return h.client.put(
        upload_url,
        content=data,
        headers={
            "authorization": f"Bearer {token}",
            "x-content-sha256": hashlib.sha256(data).hexdigest(),
        },
    )


@pytest.fixture
def harness() -> Iterator[Harness]:
    clock = FakeClock()
    app = create_app(
        settings_for_test(),
        clock=clock,
        ids=SequentialIds(),
        rng=random.Random(0),
        background_tasks=False,
    )
    with TestClient(app, base_url="http://localhost:8000") as client:
        yield Harness(client, clock)
