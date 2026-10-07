import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ClockEstimator } from "../src/audio/clock";
import { AudioEngine } from "../src/audio/engine";

describe("finale cues", () => {
  const preferences = new Map<string, string>();
  const nodes: { gain: { value: number }; connect: ReturnType<typeof vi.fn> }[] = [];
  const oscillator = vi.fn(() => ({
    frequency: { value: 0 },
    type: "sine",
    connect: vi.fn(() => ({ connect: vi.fn() })),
    start: vi.fn(),
    stop: vi.fn(),
    disconnect: vi.fn(),
    onended: null,
  }));
  const contexts = vi.fn();
  beforeEach(() => {
    preferences.clear();
    nodes.length = 0;
    oscillator.mockClear();
    contexts.mockClear();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => preferences.get(key) ?? null,
      setItem: (key: string, value: string) => preferences.set(key, value),
    });
    vi.stubGlobal("navigator", { userAgent: "test" });
    vi.stubGlobal(
      "AudioContext",
      class {
        state = "running";
        currentTime = 1;
        destination = {};
        constructor() {
          contexts();
        }
        resume() {
          return Promise.resolve();
        }
        createOscillator = oscillator;
        createGain() {
          const node = {
            gain: {
              value: 0,
              setValueAtTime: vi.fn(),
              linearRampToValueAtTime: vi.fn(),
              exponentialRampToValueAtTime: vi.fn(),
            },
            connect: vi.fn(),
            disconnect: vi.fn(),
          };
          nodes.push(node);
          return node;
        }
      },
    );
  });
  afterEach(() => vi.unstubAllGlobals());
  it("requires an unlocked context and never replays a cue missed before the gesture", async () => {
    const engine = new AudioEngine(new ClockEstimator(), () => true);
    engine.playFinaleCue("missed", "win");
    expect(contexts).not.toHaveBeenCalled();
    await engine.unlock();
    engine.playFinaleCue("missed", "win");
    expect(oscillator).not.toHaveBeenCalled();
    engine.playFinaleCue("fresh", "win");
    expect(oscillator).toHaveBeenCalledTimes(4);
    expect(contexts).toHaveBeenCalledTimes(1);
  });
  it("deduplicates live updates and ignores stale or distant server timestamps", async () => {
    const engine = new AudioEngine(new ClockEstimator(), () => true);
    await engine.unlock();
    engine.playFinaleCue("award", "award");
    engine.playFinaleCue("award", "award");
    engine.playFinaleCue("old", "reveal", performance.now() - 1000);
    engine.playFinaleCue("far", "win", performance.now() + 3000);
    expect(oscillator).toHaveBeenCalledTimes(2);
  });
  it("honors the sound preference and the shared volume including mute", async () => {
    const engine = new AudioEngine(new ClockEstimator(), () => true);
    await engine.unlock();
    preferences.set("openblindysir:finaleSounds", "off");
    engine.playFinaleCue("disabled", "award");
    expect(oscillator).not.toHaveBeenCalled();
    preferences.set("openblindysir:finaleSounds", "on");
    engine.setVolume(0);
    engine.playFinaleCue("muted", "award");
    expect(nodes[0]?.gain.value).toBe(0);
    engine.setVolume(0.35);
    expect(nodes[0]?.gain.value).toBe(0.35);
    expect(contexts).toHaveBeenCalledTimes(1);
  });
});
