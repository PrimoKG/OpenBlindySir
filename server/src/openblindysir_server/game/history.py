"""Versioned, self-contained results; no audio or live catalogue lookup."""

import json
from typing import Any

from openblindysir_protocol.views import GameRecord

MAX_GAMES = 50
MAX_BYTES = 16 * 1024 * 1024
RETENTION_DAYS = 90


class HistoryVersionError(ValueError):
    """Unknown records must not silently select an older copy of published results."""


def migrate_record(value: dict[str, Any]) -> dict[str, Any]:
    version = value.get("version", 1)
    if type(version) is not int or version not in {1, 2, 3}:
        raise HistoryVersionError("unsupported history format; preserve files and upgrade")
    return GameRecord.model_validate({**value, "version": 3}).model_dump(mode="json")


def record_bytes(record: dict[str, Any]) -> int:
    return len(json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def retained(records: list[dict[str, Any]], now_wall_ms: int) -> list[dict[str, Any]]:
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError("invalid history records")
    cutoff = now_wall_ms - RETENTION_DAYS * 86_400_000
    migrated = [migrate_record(value) for value in records]
    if len({value["game_id"] for value in migrated}) != len(migrated):
        raise ValueError("duplicate history identity")
    selected = [value for value in migrated if value["finished_at"] >= cutoff][-MAX_GAMES:]
    sizes = [record_bytes(value) for value in selected]
    total = sum(sizes)
    while selected and total > MAX_BYTES:
        total -= sizes.pop(0)
        selected.pop(0)
    return selected
