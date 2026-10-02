"""Any schema change must bump PROTOCOL_VERSION and refresh protocol/schema.lock.json."""

import json
from pathlib import Path

from openblindysir_protocol.export import schema_fingerprints
from openblindysir_protocol.version import PROTOCOL_VERSION

LOCK = Path(__file__).resolve().parent.parent / "schema.lock.json"


def test_schema_lock() -> None:
    locked = json.loads(LOCK.read_text(encoding="utf-8"))
    if locked["protocol"] == PROTOCOL_VERSION:
        assert locked["roots"] == schema_fingerprints(), (
            "the protocol schema changed: bump PROTOCOL_VERSION then run "
            "`uv run python tools/gen_ts_types.py --update-lock`"
        )
    else:
        assert locked["protocol"] < PROTOCOL_VERSION, "PROTOCOL_VERSION went backwards"
