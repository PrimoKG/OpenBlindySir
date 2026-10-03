import { afterEach, expect, it, vi } from "vitest";
import { ClockEstimator } from "../src/audio/clock";
import { AudioEngine } from "../src/audio/engine";

afterEach(() => vi.unstubAllGlobals());

it("persists bounded manual latency locally without sending a scoring or timing message", () => {
  const data = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => data.set(key, value),
  });
  const send = vi.fn(() => true);
  const engine = new AudioEngine(new ClockEstimator(), send);
  expect(engine.getSnapshot().manualLatencyMs).toBe(0);
  engine.setManualLatency(150.6);
  expect(engine.getSnapshot().manualLatencyMs).toBe(151);
  expect(new AudioEngine(new ClockEstimator(), send).getSnapshot().manualLatencyMs).toBe(151);
  engine.setManualLatency(999);
  expect(engine.getSnapshot().manualLatencyMs).toBe(500);
  engine.setManualLatency(-999);
  expect(engine.getSnapshot().manualLatencyMs).toBe(-500);
  engine.setManualLatency(Number.NaN);
  expect(engine.getSnapshot().manualLatencyMs).toBe(-500);
  expect(send).not.toHaveBeenCalled();
});
