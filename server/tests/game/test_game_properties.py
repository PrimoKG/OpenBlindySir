"""Property-based checks of the core invariants over random command sequences.

Invariants (blueprint I-numbers): journal projection (I1, I3, I4), single live round (I9),
strict orders (I10), official start written once (I11), no IN_GAME → FINAL_RESULTS (I12),
next clip only in REVIEW/REVEALED (I14), anti-leak canaries (I15), public player entries
(I16), progress bounds (I17), unchanged state on rejection (I18), reveal iff REVEALED (I21).
"""

import json
from typing import Any

from builders import CANARY_ARTIST, CANARY_FOLDER, CANARY_TITLE, Scenario
from hypothesis import event
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule
from pydantic import ValidationError

from openblindysir_protocol.enums import AnswerStatus, GamePhase, JobFailureCode, RoundState
from openblindysir_protocol.host_commands import HOST_COMMAND_NAMES
from openblindysir_server.game import commands as c
from openblindysir_server.game.state import TERMINAL_ROUND_STATES, current_round

ALLOWED_PHASE_STEPS = {
    (GamePhase.LOBBY, GamePhase.IN_GAME),
    (GamePhase.IN_GAME, GamePhase.FINAL_SCORE_REVIEW),
    (GamePhase.FINAL_SCORE_REVIEW, GamePhase.FINAL_RESULTS),
    (GamePhase.FINAL_RESULTS, GamePhase.LOBBY),
}


class GameMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.sc = Scenario(rounds=3, tracks=6)
        self.events_before: tuple[Any, ...] = ()
        self.starts: dict[str, int] = {}

    # --- helpers --------------------------------------------------------------------------

    def pids(self) -> list[str]:
        return [pid for pid in self.sc.s.players if self.sc.engine.player_exists(pid)]

    def fields_for(self, cmd: str, data: st.DataObject) -> dict[str, Any]:
        """A fresh, well-formed command taken from the host's current view."""
        s = self.sc.s
        r = current_round(s.game)
        players = self.pids() or ["p_0001"]
        pid = data.draw(st.sampled_from(players))
        args: dict[str, Any] = {}
        if cmd in ("score_draft",):
            args = {"player_id": pid, "points": data.draw(st.integers(-3, 3))}
        elif cmd == "final_set":
            args = {"player_id": pid, "delta": data.draw(st.integers(-3, 3))}
        elif cmd == "adjust":
            op = f"op-{data.draw(st.integers(0, 10**6)):08d}"
            args = {
                "player_id": pid,
                "delta": data.draw(st.sampled_from([-2, -1, 1, 2])),
                "op_id": op,
            }
        elif cmd in ("replay", "stop"):
            args = {"play_id": r.plays[-1].play_id if r and r.plays else "pl_000000"}
        elif cmd == "add_time":
            args = {"expected_deadline": (r.deadline or 0) if r else 0}
        elif cmd == "end_game":
            args = {"current_round": data.draw(st.sampled_from(["score", "abandon"]))}
        elif cmd == "set_mode":
            args = {"mode": data.draw(st.sampled_from(["player", "mc"]))}
        elif cmd in ("kick",):
            args = {"player_id": pid}
        elif cmd == "rename":
            args = {"player_id": pid, "nickname": data.draw(st.sampled_from(["Zed", "Yan"]))}
        elif cmd == "configure":
            args = {"auto_start": data.draw(st.booleans())}
        round_cmds = {
            "end_game",
            "next",
            "force_start",
            "replay",
            "stop",
            "skip",
            "add_time",
            "close",
            "score_draft",
            "publish",
            "to_final_review",
        }
        if cmd == "undo_publish":
            host = self.sc.host_view()
            target = host.host.undo_round_id if host.kind != "player" else None  # type: ignore[union-attr]
            return {"round_id": target or "r_000000", "args": {}}
        if cmd in round_cmds:
            return {"round_id": r.id if r else "r_000000", "args": args}
        return {"expected_phase": s.game.phase.value, "args": args}

    # --- rules ----------------------------------------------------------------------------

    @rule(data=st.data())
    def host_command(self, data: st.DataObject) -> None:
        cmd = data.draw(st.sampled_from([n for n in HOST_COMMAND_NAMES if n != "end_session"]))
        fields = self.fields_for(cmd, data)
        before_phase = self.sc.s.game.phase
        snapshot = self.dump()
        journal = self.sc.s.journal.events()
        try:
            outcome = self.sc.host(cmd, **fields)
        except ValidationError:
            return  # not expressible on the wire: the shell answers invalid_message
        if outcome.error is not None:
            assert self.dump() == snapshot  # I18: a rejected command changes nothing
            assert self.sc.s.journal.events() == journal
        after = self.sc.s.game.phase
        r_now = current_round(self.sc.s.game)
        round_state = r_now.state.value if r_now else None
        done = cmd if outcome.error is None else "-"
        event(f"phase={after.value} round={round_state} ok={outcome.error is None} cmd={done}")
        if after != before_phase:
            assert (before_phase, after) in ALLOWED_PHASE_STEPS

    @rule(data=st.data())
    def ready_or_audio(self, data: st.DataObject) -> None:
        r = current_round(self.sc.s.game)
        pid = data.draw(st.sampled_from(self.pids()))
        if r is not None and r.slot.asset_id and data.draw(st.booleans()):
            self.sc.audio(pid, "READY", r.slot.asset_id)
        else:
            self.sc.audio(pid, data.draw(st.sampled_from(["IDLE", "LOCKED"])))

    @rule(data=st.data())
    def answer(self, data: st.DataObject) -> None:
        r = current_round(self.sc.s.game)
        if r is None:
            return
        pid = data.draw(st.sampled_from(self.pids()))
        text = data.draw(st.sampled_from(["SECRET-A", "SECRET-B", ""]))
        if data.draw(st.booleans()):
            self.sc.draft(pid, text, round_id=r.id)
        else:
            self.sc.submit(pid, text, round_id=r.id)

    @rule(data=st.data())
    def connection(self, data: st.DataObject) -> None:
        pid = data.draw(st.sampled_from(self.pids()))
        if data.draw(st.booleans()):
            self.sc.d(c.Disconnected(pid))
        else:
            self.sc.d(c.Connected(pid, "0.1.0"))

    @rule(ms=st.integers(1, 40_000))
    def time_passes(self, ms: int) -> None:
        self.sc.advance(ms)

    @precondition(lambda self: True)
    @rule(data=st.data())
    def bridge_trouble(self, data: st.DataObject) -> None:
        self.sc.auto_serve = data.draw(st.booleans())
        if self.sc.pending_jobs:
            job = self.sc.pending_jobs.pop(0)
            if data.draw(st.booleans()):
                self.sc.serve(job)
            else:
                code = data.draw(st.sampled_from(list(JobFailureCode)))
                self.sc.d(c.JobFailedIn(job.job_id, code))

    @rule(data=st.data())
    def progress(self, data: st.DataObject) -> None:
        """Drive the game forward like a normal host, so random rules hit deep states."""
        sc = self.sc
        g = sc.s.game
        r = current_round(g)
        phase = g.phase
        try:
            if phase is GamePhase.LOBBY:
                sc.on_phase("start_game")
            elif phase is GamePhase.FINAL_SCORE_REVIEW:
                sc.on_phase("final_validate")
            elif phase is GamePhase.FINAL_RESULTS:
                sc.on_phase("new_game")
            elif r is None:
                return
            elif r.state is RoundState.LOADING:
                for pid in self.pids():
                    sc.audio(pid, "READY", r.slot.asset_id)
            elif r.state is RoundState.COUNTDOWN and r.official_start_at is not None:
                sc.advance_to(max(r.official_start_at, sc.clock.now().mono_ms))
            elif r.state is RoundState.OPEN:
                sc.on_round("close")
            elif r.state is RoundState.REVIEW:
                pid = data.draw(st.sampled_from(self.pids()))
                sc.on_round(
                    "score_draft", {"player_id": pid, "points": data.draw(st.integers(-2, 3))}
                )
                sc.on_round("publish")
            elif r.state is RoundState.REVEALED:
                if data.draw(st.booleans()) and sc.on_round("next").error is None:
                    return
                sc.on_round("to_final_review")
        except ValidationError:
            return

    @rule()
    def join_late(self) -> None:
        if len(self.pids()) < 8:
            self.sc.join(f"Late{len(self.sc.s.players)}")

    # --- invariants -----------------------------------------------------------------------

    def dump(self) -> str:
        return repr([self.sc.view(pid).model_dump_json() for pid in self.pids()])

    @invariant()
    def journal_projection(self) -> None:
        journal = self.sc.s.journal
        events = journal.events()
        assert events[: len(self.events_before)] == self.events_before
        assert [ev.id for ev in events] == list(range(1, len(events) + 1))
        self.events_before = events
        revoked = journal.revoked_ids()
        game_id = self.sc.s.game.game_id
        for pid in self.sc.s.players:
            naive = sum(
                ev.delta
                for ev in events
                if ev.game_id == game_id and ev.player_id == pid and ev.id not in revoked
            )
            assert journal.score(game_id, pid) == naive
        for ev in events:
            assert abs(ev.delta) <= 1000
            assert (ev.delta == 0) == (ev.kind.value == "revoke")

    @invariant()
    def single_live_round_and_orders(self) -> None:
        g = self.sc.s.game
        live = [r for r in g.rounds if r.state not in TERMINAL_ROUND_STATES]
        assert len(live) <= 1
        if g.phase is GamePhase.IN_GAME:
            r = current_round(g)
            assert r is not None
            assert r.state not in (RoundState.FAILED, RoundState.CANCELLED)
            if live:
                assert live[0] is r
        for r in g.rounds:
            orders = sorted(a.order for a in r.answers.values() if a.status is AnswerStatus.LOCKED)
            assert orders == list(range(1, len(orders) + 1))
            for a in r.answers.values():
                if a.status is not AnswerStatus.LOCKED:
                    assert a.order is None
                    assert a.elapsed_ms is None
            if r.official_start_at is not None:
                assert self.starts.setdefault(r.id, r.official_start_at) == r.official_start_at
                assert r.plays[0].start_at == r.official_start_at
            assert (r.reveal is not None) == (r.state is RoundState.REVEALED)

    @invariant()
    def views_never_leak(self) -> None:
        s = self.sc.s
        r = current_round(s.game)
        for pid in self.pids():
            view = self.sc.view(pid)
            text = view.model_dump_json()
            data = json.loads(text)
            assert '"relpath"' not in text
            assert '"track_id"' not in text
            assert "draft_last_changed_at" not in text
            for entry in data["players"]:
                assert set(entry) == {"id", "nickname", "online", "is_host", "is_me"}
            if view.audio.next is not None:
                assert r is not None
                assert r.state in (RoundState.REVIEW, RoundState.REVEALED)
            if view.kind == "host_mc":
                continue
            revealed = r is not None and r.state is RoundState.REVEALED
            if not revealed:
                for canary in (CANARY_TITLE, CANARY_ARTIST, CANARY_FOLDER):
                    assert canary not in text, (view.kind, r.state if r else None)
            if view.kind == "player" and not revealed and r is not None:
                own = r.answers.get(pid)
                own_text = {own.text, own.draft_text} if own else set()
                for other_pid, answer in r.answers.items():
                    if other_pid == pid or not answer.text or answer.text in own_text:
                        continue
                    assert f'"{answer.text}"' not in text
            round_view = view.round
            progress = getattr(round_view, "progress", None)
            if progress is not None:
                assert progress.expected >= 3
                assert progress.validated <= progress.expected


TestGameMachine = GameMachine.TestCase
