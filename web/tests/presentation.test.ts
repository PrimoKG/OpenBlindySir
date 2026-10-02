import { describe, expect, it } from "vitest";
import { clipPresentation } from "../src/player/presentation";

const audio = { asset_id: "a_example", url: "/api/audio/a_example", duration_ms: 8000 };
const play = { play_id: "pl_example", asset_id: audio.asset_id, start_at: 10000, clip_offset: 0 };

describe("clip presentation (never answer timing)", () => {
  it("waits for a scheduled start", () => {
    expect(clipPresentation(play, audio, "PLAYING", 9000)).toEqual({
      kind: "waiting",
      progress: 0,
    });
  });
  it("shows playback progress from the current PLAY", () => {
    expect(clipPresentation(play, audio, "PLAYING", 12000)).toEqual({
      kind: "playing",
      progress: 0.25,
    });
  });
  it("shows the clip as ended without closing the answer form", () => {
    expect(clipPresentation(play, audio, "IDLE", 20000)).toEqual({ kind: "ended", progress: 1 });
  });
  it("uses the new start and clip offset on replay", () => {
    expect(
      clipPresentation({ ...play, start_at: 30000, clip_offset: 2 }, audio, "PLAYING", 32000),
    ).toEqual({ kind: "playing", progress: 0.5 });
  });
  it("recognises an early stop", () => {
    expect(clipPresentation(play, audio, "IDLE", 13000)).toEqual({
      kind: "ended",
      progress: 0.375,
    });
  });
  it("does not claim playback while the audio is blocked or loading", () => {
    for (const state of ["LOCKED", "LOADING", "ERROR", "READY"] as const) {
      expect(clipPresentation(play, audio, state, 15000)).toEqual({ kind: "waiting", progress: 0 });
    }
  });
  it("ignores missing or mismatched assets", () => {
    expect(clipPresentation(null, audio, "IDLE", 20000)).toEqual({ kind: "ended", progress: 1 });
    expect(clipPresentation(play, null, "IDLE", 20000)).toMatchObject({ kind: "waiting" });
    expect(
      clipPresentation(play, { ...audio, asset_id: "a_other" }, "PLAYING", 12000),
    ).toMatchObject({ kind: "waiting" });
  });
});
