import { describe, expect, it } from "vitest";
import { podiumStep, trackTitle } from "../src/player/Finale";

describe("shared podium timing", () => {
  it("reveals ranks together in descending order, including ties", () => {
    expect(podiumStep(999, 1000, [1, 1, 3])).toEqual({ visible: [], done: false });
    expect(podiumStep(1000, 1000, [1, 1, 3])).toEqual({ visible: [3], done: false });
    expect(podiumStep(2800, 1000, [1, 1, 3])).toEqual({ visible: [3, 1], done: false });
    expect(podiumStep(4600, 1000, [1, 1, 3])).toEqual({ visible: [3, 1], done: true });
  });
  it("late joiners resume the current step and recovered results skip the ceremony", () => {
    expect(podiumStep(7000, 1000, [1, 2, 3])).toEqual({ visible: [3, 2, 1], done: true });
    expect(podiumStep(0, null, [1, 1])).toEqual({ visible: [1], done: true });
    expect(podiumStep(0, null, [])).toEqual({ visible: [], done: true });
  });
  it("keeps meaningful title qualifiers and multilingual text", () => {
    const base = {
      cleared_fields: [],
      aliases: null,
      display_name: "Example.mp3",
      title: "Artist - Song (Official Music Video)",
      artist: "Artist",
      folder: "",
      featuring: null,
      album: null,
      year: null,
    };
    expect(trackTitle(base)).toBe("Song");
    expect(trackTitle({ ...base, title: "Song (Live) | أغنية" })).toBe("Song (Live) | أغنية");
    expect(trackTitle({ ...base, title: null, artist: null })).toBe("Example");
  });
});
