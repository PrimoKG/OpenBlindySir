"""Atomic, versioned local snapshots. Audio and cleartext credentials are never stored."""

import hashlib
import json
import os
import shutil
from collections import deque
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from openblindysir_protocol import enums
from openblindysir_protocol.enums import AudioState, BridgeState, ConnectionState, RoundState
from openblindysir_server.auth.sessions import SessionRegistry
from openblindysir_server.game import GameEngine, Instant
from openblindysir_server.game import state as models
from openblindysir_server.game.answers import capture_drafts
from openblindysir_server.game.effects import Play
from openblindysir_server.game.scoring import ScoreEvent, ScoreJournal
from openblindysir_server.game.state import current_round

FORMAT = 1
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
CLASSES = {
    name: cls for name, cls in vars(models).items() if isinstance(cls, type) and is_dataclass(cls)
}
CLASSES.update(Play=Play, ScoreEvent=ScoreEvent, Instant=Instant)
ENUMS = {
    name: cls
    for name, cls in vars(enums).items()
    if isinstance(cls, type) and issubclass(cls, Enum)
}


def _encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return {"enum": type(value).__name__, "value": value.value}
    if is_dataclass(value):
        return {
            "type": type(value).__name__,
            "fields": {f.name: _encode(getattr(value, f.name)) for f in fields(value)},
        }
    if isinstance(value, dict):
        return {"map": [[_encode(k), _encode(v)] for k, v in value.items()]}
    if isinstance(value, set | tuple | deque):
        return {"container": type(value).__name__, "items": [_encode(v) for v in value]}
    if isinstance(value, list):
        return [_encode(v) for v in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise ValueError("unsupported snapshot value")


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(v) for v in value]
    if not isinstance(value, dict):
        return value
    if "enum" in value:
        return ENUMS[value["enum"]](value["value"])
    if "type" in value:
        return CLASSES[value["type"]](**{k: _decode(v) for k, v in value["fields"].items()})
    if "map" in value:
        return {_decode(k): _decode(v) for k, v in value["map"]}
    constructors = {"set": set, "tuple": tuple, "deque": deque}
    return constructors[value["container"]](_decode(v) for v in value["items"])


class SnapshotStore:
    def __init__(self, directory: Path, secrets: tuple[str, ...]) -> None:
        self.directory = directory
        self.fingerprint = hashlib.sha256(json.dumps(secrets).encode()).hexdigest()

    def save(self, engine: GameEngine, sessions: SessionRegistry, at: Instant) -> None:
        s = engine.state
        excluded = {"config", "ids", "rng", "journal", "touched", "last_at"}
        payload = dict(
            format=FORMAT,
            at=dict(mono_ms=at.mono_ms, wall_ms=at.wall_ms),
            auth=self.fingerprint,
            state={
                f.name: _encode(getattr(s, f.name)) for f in fields(s) if f.name not in excluded
            },
            events=_encode(s.journal.events()),
            frozen=sorted(s.journal.frozen_games()),
            sessions=sessions.snapshot(at.mono_ms),
        )
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(data) > MAX_SNAPSHOT_BYTES:
            raise ValueError("snapshot too large")
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / "session.json"
        temporary = self.directory / "session.tmp"
        with temporary.open("wb") as stream:
            os.chmod(temporary, 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists():
            shutil.copyfile(target, self.directory / "session.previous.json")
            os.chmod(self.directory / "session.previous.json", 0o600)
        os.replace(temporary, target)

    def restore(self, engine: GameEngine, sessions: SessionRegistry, at: Instant) -> bool:  # noqa: PLR0915 - recovery transaction
        target = self.directory / "session.json"
        if not target.exists():
            return False
        payload = None
        for candidate in (target, self.directory / "session.previous.json"):
            try:
                if candidate.stat().st_size > MAX_SNAPSHOT_BYTES:
                    raise ValueError("snapshot too large")
                row = json.loads(candidate.read_text(encoding="utf-8"))
                if row["format"] != FORMAT:
                    raise ValueError("unsupported snapshot format")
                decoded = {k: _decode(v) for k, v in row["state"].items()}
                journal = ScoreJournal()
                for event in _decode(row["events"]):
                    journal.append(
                        **{f.name: getattr(event, f.name) for f in fields(event) if f.name != "id"}
                    )
                for game_id in row["frozen"]:
                    journal.freeze(game_id)
                payload = row
                break
            except (OSError, ValueError, KeyError, TypeError):
                continue
        if payload is None:
            raise ValueError("no valid session snapshot; preserve files and restore a backup")
        s = engine.state
        for name, value in decoded.items():
            if name not in {"config", "ids", "rng", "journal", "last_at", "touched"}:
                setattr(s, name, value)
        s.journal = journal
        shift = at.mono_ms - payload["at"]["mono_ms"]
        for r in s.game.rounds:
            for name in (
                "created_at",
                "loading_since",
                "ready_deadline",
                "official_start_at",
                "deadline",
                "closed_at",
                "published_at",
                "paused_at",
                "resume_at",
            ):
                value = getattr(r, name)
                if value is not None:
                    setattr(r, name, value + shift)
            r.plays = [
                Play(p.play_id, p.asset_id, p.start_at + shift, p.clip_offset_s, p.ends_at + shift)
                for p in r.plays
            ]
            r.stopped_play_ids.update(p.play_id for p in r.plays)
            for answer in r.answers.values():
                if answer.received_at is not None:
                    answer.received_at += shift
                if answer.draft_last_changed_at is not None:
                    answer.draft_last_changed_at += shift
            for listen in r.listen.values():
                if listen.ready_at is not None:
                    listen.ready_at += shift
                listen.offline_since = None
        r = current_round(s.game)
        if r is not None:
            if r.state is RoundState.OPEN:
                capture_drafts(r)
                r.state = RoundState.REVIEW
                r.recovery_interrupted = True
                r.closed_at = at.mono_ms
            elif r.state in {
                RoundState.QUEUED,
                RoundState.PREPARING,
                RoundState.LOADING,
                RoundState.COUNTDOWN,
            }:
                r.state = RoundState.QUEUED
                r.slot.asset_id = None
                r.official_start_at = r.deadline = r.ready_deadline = None
                r.plays = []
                if r.slot.track_ref is not None and not r.previously_played:
                    s.played.discard(r.slot.track_ref)
            r.paused_at = r.resume_at = None
        for slot in s.game.pipeline:
            slot.asset_id = None
        # Keep metadata for review/history, but no RAM audio survives a process restart.
        for asset in s.assets.values():
            asset.state = enums.AssetState.EVICTED
        s.jobs.clear()
        s.asset_ready.clear()
        for p in s.players.values():
            if p.connection is not ConnectionState.REMOVED:
                p.connection = ConnectionState.OFFLINE
            p.audio_state, p.audio_asset_id, p.audio_error = AudioState.LOCKED, None, None
            p.joined_at_mono += shift
            p.last_report = None
        for bridge in s.bridges.values():
            bridge.state = BridgeState.OFFLINE
        s.last_at, s.recovered = at.mono_ms, True
        if payload["auth"] == self.fingerprint:
            sessions.restore(
                payload["sessions"],
                at.mono_ms,
                max(0, at.wall_ms - payload["at"]["wall_ms"]),
                set(s.players),
            )
        return True
