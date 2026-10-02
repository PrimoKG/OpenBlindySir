// Messages describing the local audio state and playback quality. Pure functions.
import type { AudioErrorCode, AudioState, AudioStatus, PlaybackReport } from "../protocol";
import type { Estimate } from "./clock";

export function buildAudioStatus(
  state: AudioState,
  assetId: string | null,
  error: AudioErrorCode | null,
  estimate: Estimate | null,
): AudioStatus {
  const clock = {
    offset: estimate ? estimate.offset : null,
    rtt_min: estimate ? Math.min(estimate.rttMin, 60_000) : null,
  };
  if (state === "LOADING" || state === "READY" || state === "PLAYING") {
    return { t: "AUDIO_STATUS", state, asset_id: assetId, clock };
  }
  if (state === "ERROR") {
    return assetId
      ? { t: "AUDIO_STATUS", state, asset_id: assetId, error, clock }
      : { t: "AUDIO_STATUS", state, error, clock };
  }
  return { t: "AUDIO_STATUS", state, clock };
}

export function buildPlaybackReport(
  playId: string,
  lateMs: number,
  estimate: Estimate | null,
  outputLatencyS: number,
): PlaybackReport {
  const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));
  return {
    t: "PLAYBACK_REPORT",
    play_id: playId,
    late_ms: clamp(lateMs, -600_000, 600_000),
    offset: estimate ? estimate.offset : 0,
    rtt_min: estimate ? clamp(estimate.rttMin, 0, 60_000) : 0,
    out_latency: clamp(outputLatencyS * 1000, 0, 5_000),
    est_error_ms: estimate ? clamp(estimate.epsilon, 0, 60_000) : 0,
  };
}
