// HOST message builders (spec §8.2): every idempotency key is read from the DISPLAYED view,
// so a double click or a second host device sends a stale key and changes nothing.
import type { AnyView, ClientMessage, HostView, MusicalMetadata, SettingsPatch } from "../protocol";

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

export function trackMetadata(
  roundId: string,
  metadata: MusicalMetadata,
  regradeAuto = false,
  expectedRevision?: number,
): Host {
  return {
    t: "HOST",
    cmd: "track_metadata",
    round_id: roundId,
    args: { ...metadata, regrade_auto: regradeAuto, expected_revision: expectedRevision ?? null },
  };
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

export function newGame(resetLibrary = false): Host {
  return {
    t: "HOST",
    cmd: "new_game",
    expected_phase: "FINAL_RESULTS",
    args: { reset_library: resetLibrary },
  };
}

export function roundCmd(view: AnyView, cmd: RoundCmd): Host {
  return { t: "HOST", cmd, round_id: roundId(view), args: {} } as Host;
}

export function endGame(view: AnyView, currentRound: "score" | "abandon"): Host {
  const key = view.round ? { round_id: roundId(view) } : { expected_phase: view.phase };
  return {
    t: "HOST",
    cmd: "end_game",
    ...key,
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

export function scoreDraft(
  round: AnyView | string,
  playerId: string,
  points: number,
  judgement?: {
    judgement: "manual" | "criteria";
    title_correct?: boolean | null;
    artist_correct?: boolean | null;
    custom_correct?: boolean | null;
    album_correct?: boolean | null;
    year_correct?: boolean | null;
    featuring_correct?: boolean | null;
    expected_revision?: number;
  },
): Host {
  return {
    t: "HOST",
    cmd: "score_draft",
    round_id: typeof round === "string" ? round : roundId(round),
    args: { player_id: playerId, points, ...judgement },
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

export function finalSet(
  playerId: string,
  delta: number,
  note?: string | null,
  expected?: { delta: number; note: string | null },
): Host {
  return {
    t: "HOST",
    cmd: "final_set",
    expected_phase: "FINAL_SCORE_REVIEW",
    args: {
      player_id: playerId,
      delta,
      note: note ?? null,
      ...(expected ? { expected_delta: expected.delta, expected_note: expected.note } : {}),
    },
  };
}

export function finalReset(): Host {
  return { t: "HOST", cmd: "final_reset", expected_phase: "FINAL_SCORE_REVIEW", args: {} };
}

export function finaleReveal(roundId: string, fastForward = false): Host {
  return {
    t: "HOST",
    cmd: "finale_reveal",
    expected_phase: "FINAL_SCORE_REVIEW",
    args: { round_id: roundId, fast_forward: fastForward },
  };
}

export function finaleStop(): Host {
  return { t: "HOST", cmd: "finale_stop", expected_phase: "FINAL_SCORE_REVIEW", args: {} };
}

export function finalValidate(confirmUnreviewed = false): Host {
  return {
    t: "HOST",
    cmd: "final_validate",
    expected_phase: "FINAL_SCORE_REVIEW",
    args: { confirm_unreviewed: confirmUnreviewed },
  };
}

export function joinLock(view: AnyView, locked: boolean): Host {
  return { t: "HOST", cmd: "join_lock", expected_phase: view.phase, args: { locked } };
}

export function selectTrack(
  view: Extract<HostView, { kind: "host_mc" }>,
  roundNumber: number,
  track: { bridge_id: string; track_id: string } | null,
): Host {
  return {
    t: "HOST",
    cmd: "select_track",
    expected_phase: view.phase === "LOBBY" ? "LOBBY" : "IN_GAME",
    args: {
      round_number: roundNumber,
      expected_revision: view.mc.selection_revision ?? 0,
      bridge_id: track?.bridge_id ?? null,
      track_id: track?.track_id ?? null,
    },
  };
}
