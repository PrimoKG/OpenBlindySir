// HOST message builders (spec §8.2): every idempotency key is read from the DISPLAYED view,
// so a double click or a second host device sends a stale key and changes nothing.
import type { AnyView, ClientMessage, HostView, SettingsPatch } from "../protocol";

type Host = Extract<ClientMessage, { t: "HOST" }>;
type RoundCmd =
  | "next"
  | "force_start"
  | "skip"
  | "close"
  | "publish"
  | "to_final_review"
  | "pause"
  | "resume";

function roundId(view: AnyView): string {
  return view.round?.round_id ?? "";
}

export function configure(view: AnyView, patch: SettingsPatch, start = false): Host {
  const phase = view.phase === "FINAL_SCORE_REVIEW" ? "LOBBY" : view.phase;
  return { t: "HOST", cmd: "configure", expected_phase: phase, args: patch, start_game: start };
}

export function publish(view: AnyView, confirm = false): Host {
  return {
    t: "HOST",
    cmd: "publish",
    round_id: roundId(view),
    args: { confirm_unreviewed: confirm },
  };
}

export function trackMetadata(view: AnyView, title: string, artist: string): Host {
  return { t: "HOST", cmd: "track_metadata", round_id: roundId(view), args: { title, artist } };
}

export function participation(playerId: string, spectator: boolean, team: string | null): Host {
  return {
    t: "HOST",
    cmd: "participation",
    expected_phase: "LOBBY",
    args: { player_id: playerId, spectator, team },
  };
}

export function setMode(view: AnyView, mode: "player" | "mc"): Host {
  return { t: "HOST", cmd: "set_mode", expected_phase: view.phase, args: { mode } };
}

export function kick(view: AnyView, playerId: string): Host {
  return { t: "HOST", cmd: "kick", expected_phase: view.phase, args: { player_id: playerId } };
}

export function rename(view: AnyView, playerId: string, nickname: string): Host {
  return {
    t: "HOST",
    cmd: "rename",
    expected_phase: view.phase,
    args: { player_id: playerId, nickname },
  };
}

export function endSession(view: AnyView): Host {
  return { t: "HOST", cmd: "end_session", expected_phase: view.phase, args: {} };
}

export function startGame(): Host {
  return { t: "HOST", cmd: "start_game", expected_phase: "LOBBY", args: {} };
}

export function newGame(): Host {
  return { t: "HOST", cmd: "new_game", expected_phase: "FINAL_RESULTS", args: {} };
}

export function roundCmd(view: AnyView, cmd: RoundCmd): Host {
  return { t: "HOST", cmd, round_id: roundId(view), args: {} } as Host;
}

export function endGame(view: AnyView, currentRound: "score" | "abandon"): Host {
  return {
    t: "HOST",
    cmd: "end_game",
    round_id: roundId(view),
    args: { current_round: currentRound },
  };
}

/** Never the displayed round: after `next`, the displayed round is already N+1. */
export function undoPublish(view: HostView): Host {
  return { t: "HOST", cmd: "undo_publish", round_id: view.host.undo_round_id ?? "", args: {} };
}

export function replay(view: HostView): Host {
  return {
    t: "HOST",
    cmd: "replay",
    round_id: roundId(view),
    args: { play_id: view.host.last_play_id ?? "" },
  };
}

export function stop(view: AnyView): Host {
  return {
    t: "HOST",
    cmd: "stop",
    round_id: roundId(view),
    args: { play_id: view.play?.play_id ?? "" },
  };
}

export function addTime(view: AnyView): Host {
  const deadline = view.round && "deadline" in view.round ? view.round.deadline : 0;
  return {
    t: "HOST",
    cmd: "add_time",
    round_id: roundId(view),
    args: { expected_deadline: deadline },
  };
}

export function scoreDraft(view: AnyView, playerId: string, points: number): Host {
  return {
    t: "HOST",
    cmd: "score_draft",
    round_id: roundId(view),
    args: { player_id: playerId, points },
  };
}

export function newOpId(): string {
  return crypto.randomUUID().replaceAll("-", "");
}

export function adjust(playerId: string, delta: number, opId: string, note?: string): Host {
  const args: { player_id: string; delta: number; op_id: string; note?: string } = {
    player_id: playerId,
    delta,
    op_id: opId,
  };
  if (note) {
    args.note = note;
  }
  return { t: "HOST", cmd: "adjust", expected_phase: "IN_GAME", args };
}

export function finalSet(playerId: string, delta: number): Host {
  return {
    t: "HOST",
    cmd: "final_set",
    expected_phase: "FINAL_SCORE_REVIEW",
    args: { player_id: playerId, delta },
  };
}

export function finalReset(): Host {
  return { t: "HOST", cmd: "final_reset", expected_phase: "FINAL_SCORE_REVIEW", args: {} };
}

export function finalValidate(): Host {
  return { t: "HOST", cmd: "final_validate", expected_phase: "FINAL_SCORE_REVIEW", args: {} };
}
