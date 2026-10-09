"""Atomic, versioned local snapshots. Audio and cleartext credentials are never stored."""

import base64
import hashlib
import json
import math
import os
from collections import deque
from dataclasses import MISSING, asdict, fields, is_dataclass
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

from cryptography.fernet import Fernet, InvalidToken
from pydantic import TypeAdapter

from openblindysir_protocol import enums
from openblindysir_protocol.enums import (
    AudioState,
    BridgeState,
    ConnectionState,
    GamePhase,
    RoundState,
    ScoreKind,
)
from openblindysir_protocol.themes import ThemeFilter
from openblindysir_server.auth.sessions import SessionRegistry
from openblindysir_server.game import GameEngine, Instant, auto_scoring, rounds
from openblindysir_server.game import state as models
from openblindysir_server.game.answers import capture_drafts
from openblindysir_server.game.effects import Play
from openblindysir_server.game.history import HistoryVersionError, retained
from openblindysir_server.game.scoring import ScoreEvent, ScoreJournal
from openblindysir_server.game.state import current_round, is_participant
from openblindysir_server.private_files import (
    atomic_private_write,
    private_temporary,
    require_unlinked_path,
    unique_json_object,
)

FORMAT = 11
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024


class SnapshotVersionError(ValueError):
    """An unknown format must never silently restore an older game or its scores."""


CLASSES = {
    name: cls for name, cls in vars(models).items() if isinstance(cls, type) and is_dataclass(cls)
}
CLASSES.update(Play=Play, ScoreEvent=ScoreEvent, Instant=Instant)
ENUMS = {
    name: cls
    for name, cls in vars(enums).items()
    if isinstance(cls, type) and issubclass(cls, Enum)
}


@cache
def _record_types(record: type) -> dict[str, Any]:
    return get_type_hints(record)


@cache
def _field_adapter(record: type, name: str) -> TypeAdapter:
    annotation = _record_types(record)[name]
    if get_origin(annotation) is deque:
        annotation = list[get_args(annotation)[0]]
    return TypeAdapter(annotation)


def _validate_fields(record: type, values: dict[str, Any]) -> None:
    # Nested dataclasses were already checked when decoding their own fields.
    for name, value in values.items():
        candidate = value
        if get_origin(_record_types(record)[name]) is deque:
            if not isinstance(value, deque):
                raise ValueError("invalid snapshot deque")
            candidate = list(value)
        _field_adapter(record, name).validate_python(candidate, strict=True)


def _snapshot_bytes(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_SNAPSHOT_BYTES + 1)
    if len(data) > MAX_SNAPSHOT_BYTES:
        raise ValueError("snapshot too large")
    return data


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
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("invalid snapshot number")
        if isinstance(value, str):
            value.encode("utf-8")  # Refuse lone surrogates before a view or cookie can use them.
        return value
    if "enum" in value:
        if set(value) != {"enum", "value"}:
            raise ValueError("invalid snapshot enum")
        return ENUMS[value["enum"]](value["value"])
    if "type" in value:
        if set(value) != {"type", "fields"} or not isinstance(value["fields"], dict):
            raise ValueError("invalid snapshot record")
        record = CLASSES[value["type"]]
        decoded = {k: _decode(v) for k, v in value["fields"].items()}
        _validate_fields(record, decoded)
        return record(**decoded)
    if "map" in value:
        if set(value) != {"map"}:
            raise ValueError("invalid snapshot map")
        return {_decode(k): _decode(v) for k, v in value["map"]}
    if set(value) != {"container", "items"}:
        raise ValueError("invalid snapshot container")
    constructors = {"set": set, "tuple": tuple, "deque": deque}
    return constructors[value["container"]](_decode(v) for v in value["items"])


class SnapshotStore:
    def __init__(self, directory: Path, secrets: tuple[str, ...]) -> None:
        self.directory = directory
        self.fingerprint = hashlib.sha256(json.dumps(secrets[:2]).encode()).hexdigest()
        self.legacy_fingerprint = hashlib.sha256(json.dumps(secrets[:3]).encode()).hexdigest()
        key = hashlib.pbkdf2_hmac(
            "sha256", json.dumps(secrets[:2]).encode(), b"OpenBlindySir access v1", 600000
        )
        self.access_cipher = Fernet(base64.urlsafe_b64encode(key))

    def decode_access(self, value: Any) -> dict[str, str]:
        if not isinstance(value, str):
            raise ValueError("invalid encrypted session access")
        try:
            return json.loads(self.access_cipher.decrypt(value.encode()))
        except (InvalidToken, ValueError, TypeError) as exc:
            raise ValueError("invalid encrypted session access") from exc

    def save(
        self,
        engine: GameEngine,
        sessions: SessionRegistry,
        at: Instant,
        *,
        purge_previous: bool = False,
        state: models.SessionState | None = None,
    ) -> None:
        s = state if state is not None else engine.state
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
            recovery=sessions.recovery_snapshot(),
            access=self.access_cipher.encrypt(
                json.dumps(sessions.access.snapshot()).encode()
            ).decode(),
        )
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(data) > MAX_SNAPSHOT_BYTES:
            raise ValueError("snapshot too large")
        require_unlinked_path(self.directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = self.directory / "session.json"
        backup = self.directory / "session.previous.json"
        require_unlinked_path(target)
        require_unlinked_path(backup)
        temporary = private_temporary(self.directory, data)
        try:
            if purge_previous:
                atomic_private_write(backup, data)
            elif target.exists():
                atomic_private_write(backup, _snapshot_bytes(target))
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def restore(self, engine: GameEngine, sessions: SessionRegistry, at: Instant) -> bool:  # noqa: PLR0915 - recovery transaction
        target = self.directory / "session.json"
        require_unlinked_path(target)
        if not target.exists():
            return False
        payload = None
        for candidate in (target, self.directory / "session.previous.json"):
            try:
                require_unlinked_path(candidate)
                row = json.loads(
                    _snapshot_bytes(candidate).decode("utf-8"), object_pairs_hook=unique_json_object
                )
                if type(row["format"]) is not int or row["format"] not in {
                    1,
                    2,
                    3,
                    4,
                    5,
                    6,
                    7,
                    8,
                    9,
                    10,
                    FORMAT,
                }:
                    raise SnapshotVersionError(
                        "unsupported snapshot format; preserve files and upgrade "
                        "or restore a matching backup"
                    )
                decoded = {k: _decode(v) for k, v in row["state"].items()}
                allowed = {f.name for f in fields(models.SessionState)} - {
                    "config",
                    "ids",
                    "rng",
                    "journal",
                    "touched",
                    "last_at",
                }
                if set(decoded) - allowed or not isinstance(decoded.get("game"), models.GameState):
                    raise ValueError("invalid session snapshot state")
                required = {
                    f.name
                    for f in fields(models.SessionState)
                    if f.name in allowed and f.default is MISSING and f.default_factory is MISSING
                }
                if required - set(decoded):
                    raise ValueError("incomplete session snapshot state")
                if row["format"] == 1:
                    migrated = {}
                    for ref, value in decoded.get("metadata", {}).items():
                        if isinstance(value, tuple):
                            if len(value) != 2:
                                raise ValueError("invalid legacy metadata")
                            record = dict(title=value[0], artist=value[1])
                            _validate_fields(models.Metadata, record)
                            migrated[ref] = models.Metadata(**record)
                        else:
                            migrated[ref] = value
                    decoded["metadata"] = migrated
                _validate_fields(models.SessionState, decoded)
                game = decoded["game"]
                ThemeFilter.model_validate(asdict(game.settings.selection_filter))
                if game.current_index is not None and not 0 <= game.current_index < len(
                    game.rounds
                ):
                    raise ValueError("invalid current round index")
                played_ids = {r.id for r in game.rounds if r.official_start_at is not None}
                if (
                    len(set(game.finale_revealed)) != len(game.finale_revealed)
                    or not set(game.finale_revealed) <= played_ids
                    or (
                        game.finale_round_id is not None
                        and game.finale_round_id not in game.finale_revealed
                    )
                ):
                    raise ValueError("invalid finale reveal progress")
                self._validate_recovery(row, decoded, sessions, at)
                decoded["archives"] = retained(decoded.get("archives", []), at.wall_ms)
                journal = ScoreJournal()
                for index, event in enumerate(_decode(row["events"]), start=1):
                    if event.id != index:
                        raise ValueError("invalid score event sequence")
                    journal.append(
                        **{f.name: getattr(event, f.name) for f in fields(event) if f.name != "id"}
                    )
                for game_id in row["frozen"]:
                    journal.freeze(game_id)
                payload = row
                break
            except (SnapshotVersionError, HistoryVersionError):
                raise
            except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
                continue
        if payload is None:
            raise ValueError("no valid session snapshot; preserve files and restore a backup")
        s = engine.state
        for name, value in decoded.items():
            if name not in {"config", "ids", "rng", "journal", "last_at", "touched"}:
                setattr(s, name, value)
        s.journal = journal
        if payload["format"] == 1:
            for r in s.game.rounds:
                r.participant_ids.update(r.answers)
                if r.official_start_at is not None:
                    r.participant_ids.update(p.id for p in s.players.values() if is_participant(p))
                if s.game.phase is not GamePhase.FINAL_RESULTS:
                    # Preserve the audit trail while moving old publications back to drafts.
                    events = [
                        e
                        for e in journal.active(s.game.game_id)
                        if e.kind is ScoreKind.ROUND and e.round_id == r.id
                    ]
                    for event in events:
                        r.score_draft[event.player_id] = event.delta
                        r.score_reviewed.add(event.player_id)
                        journal.append(
                            game_id=event.game_id,
                            player_id=event.player_id,
                            round_id=r.id,
                            delta=0,
                            kind=ScoreKind.REVOKE,
                            by=event.by,
                            at_wall_ms=at.wall_ms,
                            revokes=(event.id,),
                            note="snapshot_v1_migration",
                        )
                    r.published_event_ids = ()
                    r.published_at = None
                    if r.state is RoundState.REVEALED:
                        r.state = RoundState.REVIEW
                if r.slot.track_ref is not None:
                    catalog = s.catalogs.get(r.slot.track_ref.bridge_id)
                    if catalog is not None:
                        r.track_entry = catalog.entries.get(r.slot.track_ref.track_id)
                        r.bridge_name = catalog.bridge_name
        shift = at.mono_ms - payload["at"]["mono_ms"]
        # Public finale progress survives; audio and a past podium never restart on recovery.
        s.game.finale_play = None
        s.game.finalized_at = None
        for r in s.game.rounds:
            r.slot.bridge_wait_since = None
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
                "finale_wave_at",
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
            # A restart always requires the host to resume an interrupted transition.
            r.auto_advance_at = None
            if r.state is RoundState.OPEN:
                capture_drafts(r)
                r.state = RoundState.REVIEW
                r.recovery_interrupted = True
                r.closed_at = at.mono_ms
                auto_scoring.grade_round(s, r)
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
        for played_round in s.game.rounds:
            if played_round.official_start_at is not None and played_round.reveal is None:
                played_round.reveal = rounds.build_reveal(s, played_round)
        for slot in s.game.pipeline:
            slot.asset_id = None
            slot.bridge_wait_since = None
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
        expected_auth = self.fingerprint if payload["format"] >= 4 else self.legacy_fingerprint
        if payload["auth"] == expected_auth:
            sessions.restore(
                payload["sessions"],
                at.mono_ms,
                max(0, at.wall_ms - payload["at"]["wall_ms"]),
                set(s.players),
            )
            sessions.restore_recovery(payload.get("recovery", {}), set(s.players))
            if "access" in payload:
                sessions.access.restore(self.decode_access(payload["access"]))
        return True

    def _validate_recovery(
        self, row: dict, decoded: dict, sessions: SessionRegistry, at: Instant
    ) -> None:
        required = {"format", "at", "auth", "state", "events", "frozen", "sessions"}
        if required - set(row) or set(row) - required - {"recovery", "access"}:
            raise ValueError("invalid snapshot envelope")
        if (
            not isinstance(row["at"], dict)
            or set(row["at"]) != {"mono_ms", "wall_ms"}
            or any(type(v) is not int or v < 0 for v in row["at"].values())
            or not isinstance(row["auth"], str)
            or len(row["auth"]) != 64
            or any(c not in "0123456789abcdef" for c in row["auth"])
            or not isinstance(row["frozen"], list)
            or any(not isinstance(v, str) for v in row["frozen"])
            or not isinstance(row["sessions"], list)
        ):
            raise ValueError("invalid snapshot recovery data")
        for record in row["sessions"]:
            if (
                not isinstance(record, dict)
                or set(record) != {"token_hash", "player_id", "idle_ms"}
                or not isinstance(record["token_hash"], str)
                or not isinstance(record["player_id"], str)
                or type(record["idle_ms"]) is not int
            ):
                raise ValueError("invalid snapshot session")
        # Validate cookie/recovery handling before committing any game state or scores.
        trial = SessionRegistry(sessions.idle_ttl_ms)
        players = set(decoded["players"])
        trial.restore(
            row["sessions"], at.mono_ms, max(0, at.wall_ms - row["at"]["wall_ms"]), players
        )
        trial.restore_recovery(row.get("recovery", {}), players)
        if "access" in row and row["auth"] == self.fingerprint:
            trial.access.restore(self.decode_access(row["access"]))
