// Display-only clip progress in OPEN. Answer timing and closure stay server-authoritative.
import type { AudioRef, AudioState, PlayInfo } from "../protocol";

export function clipPresentation(
  play: PlayInfo | null,
  audio: AudioRef | null,
  state: AudioState,
  now: number,
): { kind: "waiting" | "playing" | "ended"; progress: number } {
  if (!audio || audio.duration_ms <= 0) {
    return { kind: "waiting", progress: 0 };
  }
  // The server removes the active PLAY when the clip ends or is stopped. In OPEN,
  // an available clip without a PLAY is finished, while answers can still be edited.
  if (!play) return { kind: "ended", progress: 1 };
  if (play.asset_id !== audio.asset_id) return { kind: "waiting", progress: 0 };
  const elapsed = Math.max(0, now - play.start_at) + play.clip_offset * 1000;
  const progress = Math.min(1, elapsed / audio.duration_ms);
  if (now < play.start_at || (state !== "PLAYING" && state !== "IDLE")) {
    return { kind: "waiting", progress: 0 };
  }
  return { kind: state === "IDLE" || progress >= 1 ? "ended" : "playing", progress };
}
