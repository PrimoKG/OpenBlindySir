"""Scenario builder for core tests: a full engine with a fake Bridge, players and a host.

Messages are built from JSON exactly like on the wire (strict protocol models), and the
fake Bridge answers every PREPARE immediately unless ``auto_serve`` is disabled.
"""

import json
import random
from typing import Any

from pydantic import TypeAdapter

from openblindysir_protocol.bridge import JobDone
from openblindysir_protocol.catalog_rules import compute_track_id
from openblindysir_protocol.client import AnswerDraft, AnswerSubmit, AudioStatus, ClientMessage
from openblindysir_protocol.views import HostMcView, HostPlayerModeView, PlayerView
from openblindysir_server.game import CoreConfig, FakeClock, GameEngine, SequentialIds
from openblindysir_server.game import commands as c
from openblindysir_server.game import effects as e
from openblindysir_server.game.state import CatalogEntryData, Round, current_round

BRIDGE_ID = "12345678-1234-1234-1234-123456789abc"
CATALOG_HASH = "c" * 64
UPLOAD_SHA = "a" * 64
CLIENT = TypeAdapter(ClientMessage)

# Canaries: values that must never appear in a view where they are forbidden.
CANARY_FOLDER = "CanaryFolder"
CANARY_TITLE = "CanaryTitle"
CANARY_ARTIST = "CanaryArtist"

AnyView = PlayerView | HostPlayerModeView | HostMcView


def parse(payload: dict[str, Any]) -> Any:
    return CLIENT.validate_json(json.dumps(payload))


def make_catalog(count: int, folder: str = CANARY_FOLDER) -> dict[str, CatalogEntryData]:
    entries: dict[str, CatalogEntryData] = {}
    for index in range(count):
        relpath = f"{folder}/track-{index:03d}.flac"
        entries[compute_track_id(relpath)] = CatalogEntryData(relpath, folder, ".flac", 1000)
    return entries


class Scenario:
    """A game session driven by explicit commands and a fake clock."""

    def __init__(
        self,
        players: tuple[str, ...] = ("Ayoub", "Mehdi", "Sofiane"),
        *,
        host: str | None = "Yo",
        rounds: int = 3,
        tracks: int = 12,
        auto_serve: bool = True,
        config: CoreConfig | None = None,
        seed: int = 7,
        clip_s: float = 20.0,
        tags: bool = True,
    ) -> None:
        self.clock = FakeClock()
        self.engine = GameEngine(
            config or CoreConfig(),
            ids=SequentialIds(),
            rng=random.Random(seed),
            started_at=self.clock.now(),
        )
        self.auto_serve = auto_serve
        self.clip_s = clip_s
        self.tags = tags
        self.effects: list[e.Effect] = []
        self.pending_jobs: list[e.RequestPrepare] = []
        self.rounds = rounds
        self.d(c.BridgeConnected(BRIDGE_ID, "PC", "0.1.0", CATALOG_HASH, tracks))
        self.d(c.CatalogLoaded(BRIDGE_ID, "PC", CATALOG_HASH, make_catalog(tracks)))
        self.ids: dict[str, str] = {}
        self.host_id: str | None = None
        if host is not None:
            self.host_id = self.join(host)
            self.d(c.ElevateHost(self.host_id))
        for name in players:
            self.join(name)
        if self.host_id is not None:
            self.configure(rounds=rounds, sources=[{"bridge_id": BRIDGE_ID, "folder_prefix": ""}])

    # --- plumbing -------------------------------------------------------------------------

    @property
    def s(self) -> Any:
        return self.engine.state

    def d(self, cmd: c.Command) -> e.Outcome:
        outcome = self.engine.dispatch(cmd, self.clock.now())
        self.effects.extend(outcome.effects)
        self._serve(outcome)
        return outcome

    def _serve(self, outcome: e.Outcome) -> None:
        for effect in outcome.effects:
            if isinstance(effect, e.RequestPrepare):
                if self.auto_serve:
                    self.serve(effect)
                else:
                    self.pending_jobs.append(effect)

    def serve(self, job: e.RequestPrepare, *, clip_s: float | None = None) -> None:
        clip = self.clip_s if clip_s is None else clip_s
        self.d(c.UploadVerified(job.asset_id, 1000, UPLOAD_SHA, "audio/mp4"))
        tags = {"title": CANARY_TITLE, "artist": CANARY_ARTIST} if self.tags else None
        done = JobDone.model_validate_json(
            json.dumps(
                {
                    "t": "JOB_DONE",
                    "job_id": job.job_id,
                    "actual_start": 30.0,
                    "clip_duration": clip,
                    "track_duration": 200.0,
                    "bytes": 1000,
                    "sha256": UPLOAD_SHA,
                    "tags": tags,
                }
            )
        )
        self.d(c.JobDoneIn(done))

    def advance(self, ms: int) -> e.Outcome:
        self.clock.advance(ms)
        return self.d(c.Tick())

    def advance_to(self, mono_ms: int) -> e.Outcome:
        self.clock.set(mono_ms)
        return self.d(c.Tick())

    def effects_of(self, kind: type) -> list[Any]:
        return [effect for effect in self.effects if isinstance(effect, kind)]

    # --- players --------------------------------------------------------------------------

    def join(self, name: str, *, connect: bool = True) -> str:
        outcome = self.d(c.Join(name))
        assert outcome.error is None, outcome.error
        pid = outcome.value
        assert isinstance(pid, str)
        self.ids[name] = pid
        if connect:
            self.d(c.Connected(pid, "0.1.0"))
        return pid

    def pid(self, name: str) -> str:
        return self.ids[name]

    @property
    def player_ids(self) -> list[str]:
        return [pid for name, pid in self.ids.items() if pid != self.host_id]

    def audio(self, pid: str, state: str, asset_id: str | None = None, **extra: Any) -> e.Outcome:
        payload: dict[str, Any] = {
            "t": "AUDIO_STATUS",
            "state": state,
            "clock": {"offset": 1.0, "rtt_min": 20.0},
            **extra,
        }
        if asset_id is not None:
            payload["asset_id"] = asset_id
        msg = parse(payload)
        assert isinstance(msg, AudioStatus)
        return self.d(c.AudioStatusIn(pid, msg))

    def ready(self, *pids: str) -> None:
        asset = self.current().slot.asset_id
        assert asset is not None
        for pid in pids or tuple(self.ids.values()):
            self.audio(pid, "READY", asset)

    def draft(self, pid: str, text: str, round_id: str | None = None) -> e.Outcome:
        rid = round_id or self.current().id
        msg = parse({"t": "ANSWER_DRAFT", "round_id": rid, "text": text})
        assert isinstance(msg, AnswerDraft)
        return self.d(c.DraftIn(pid, msg))

    def submit(self, pid: str, text: str, round_id: str | None = None) -> e.SendAck:
        rid = round_id or self.current().id
        msg = parse({"t": "ANSWER_SUBMIT", "round_id": rid, "text": text})
        assert isinstance(msg, AnswerSubmit)
        outcome = self.d(c.SubmitIn(pid, msg))
        acks = [x for x in outcome.effects if isinstance(x, e.SendAck)]
        assert len(acks) == 1
        return acks[0]

    # --- host -----------------------------------------------------------------------------

    def host(self, cmd: str, *, by: str | None = None, **fields: Any) -> e.Outcome:
        msg = parse({"t": "HOST", "cmd": cmd, **fields})
        issuer = by or self.host_id
        assert issuer is not None
        return self.d(c.HostIn(issuer, msg))

    def ok(self, cmd: str, **fields: Any) -> e.Outcome:
        outcome = self.host(cmd, **fields)
        assert outcome.error is None, (cmd, outcome.error)
        return outcome

    def on_round(self, cmd: str, args: dict[str, Any] | None = None, **kw: Any) -> e.Outcome:
        return self.host(cmd, round_id=self.current().id, args=args or {}, **kw)

    def on_phase(self, cmd: str, args: dict[str, Any] | None = None) -> e.Outcome:
        return self.host(cmd, expected_phase=self.s.game.phase.value, args=args or {})

    def configure(self, **args: Any) -> e.Outcome:
        return self.on_phase("configure", args)

    def set_mode(self, mode: str) -> e.Outcome:
        return self.on_phase("set_mode", {"mode": mode})

    def start(self) -> e.Outcome:
        outcome = self.on_phase("start_game")
        assert outcome.error is None, outcome.error
        return outcome

    # --- round helpers --------------------------------------------------------------------

    def current(self) -> Round:
        r = current_round(self.s.game)
        assert r is not None
        return r

    def to_open(self) -> Round:
        """From LOBBY or a REVEALED round: start the next round and open it."""
        if self.s.game.phase.value == "LOBBY":
            self.start()
        elif self.current().state.value == "REVEALED":
            assert self.on_round("next").error is None
        self.ready()
        r = self.current()
        assert r.state.value == "COUNTDOWN", r.state
        assert r.official_start_at is not None
        self.advance_to(r.official_start_at)
        assert r.state.value == "OPEN"
        return r

    def to_review(self) -> Round:
        r = self.current() if self.s.game.phase.value != "LOBBY" else self.to_open()
        if r.state.value != "OPEN":
            r = self.to_open()
        assert self.on_round("close").error is None
        return r

    def publish(self, points: dict[str, int] | None = None) -> Round:
        r = self.current()
        for pid, pts in (points or {}).items():
            assert self.on_round("score_draft", {"player_id": pid, "points": pts}).error is None
        assert self.on_round("publish").error is None
        return r

    def view(self, pid: str) -> AnyView:
        return self.engine.view_for(pid)

    def host_view(self) -> AnyView:
        assert self.host_id is not None
        return self.engine.view_for(self.host_id)
