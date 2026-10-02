import { describe, expect, it } from "vitest";
import { ClockEstimator, estimate, sampleFrom, serverToLocal } from "../src/audio/clock";
import { assetsToFetch } from "../src/audio/prefetch";
import { buildAudioStatus, buildPlaybackReport } from "../src/audio/report";
import { contextTimeForLocal, planStart } from "../src/audio/schedule";

describe("clock (spec §9.2)", () => {
  it("computes rtt and theta from one exchange", () => {
    // local 1000 → server answers 5_050 → back at local 1100: θ = 5050 − 1050
    expect(sampleFrom(1000, 1100, 5050)).toEqual({ rtt: 100, theta: 4000 });
  });

  it("keeps the error under asymmetry/2 with jitter and outliers", () => {
    const trueOffset = 12_345;
    const clock = new ClockEstimator();
    let seed = 7;
    const rand = () => {
      seed = (seed * 16807) % 2147483647;
      return seed / 2147483647;
    };
    for (let i = 0; i < 30; i += 1) {
      const up = 20 + rand() * 30 + (i % 7 === 0 ? 400 : 0); // outliers
      const down = 15 + rand() * 30;
      const t0 = i * 1000;
      const serverAtReception = t0 + up + trueOffset;
      const t1 = t0 + up + down;
      clock.add(sampleFrom(t0, t1, serverAtReception));
    }
    const result = clock.estimate();
    expect(result).not.toBeNull();
    // |error| ≤ |up − down| / 2 for the selected low-RTT samples (≤ 30/2 here)
    expect(Math.abs((result?.offset ?? 0) - trueOffset)).toBeLessThanOrEqual(30);
    expect(result?.epsilon).toBeCloseTo((result?.rttMin ?? 0) / 2);
  });

  it("uses the median theta of the three lowest-RTT samples", () => {
    const samples = [
      { rtt: 10, theta: 100 },
      { rtt: 12, theta: 104 },
      { rtt: 11, theta: 98 },
      { rtt: 500, theta: 9999 },
    ];
    expect(estimate(samples)?.offset).toBe(100);
    expect(estimate([])).toBeNull();
  });

  it("converts a server instant to local time", () => {
    expect(serverToLocal(10_000, 4_000)).toBe(6_000);
    expect(serverToLocal(10_000, 4_000, 120)).toBe(5_880);
  });
});

describe("scheduling (spec §9.5)", () => {
  it("uses getOutputTimestamp when available", () => {
    const T = contextTimeForLocal(2_000, {
      ts: { contextTime: 10, performanceTime: 1_000 },
      currentTime: 99,
      perfNow: 99,
    });
    expect(T).toBeCloseTo(11);
  });

  it("falls back on currentTime minus the output latency", () => {
    const T = contextTimeForLocal(2_000, {
      ts: null,
      currentTime: 10,
      perfNow: 1_000,
      outputLatency: 0.02,
    });
    expect(T).toBeCloseTo(10.98);
  });

  it("schedules a future start and catches up a past one", () => {
    expect(planStart(12, 10, 0, 30)).toEqual({ kind: "scheduled", when: 12, offset: 0 });
    const late = planStart(8, 10, 0, 30);
    expect(late.kind).toBe("catchup");
    if (late.kind === "catchup") {
      expect(late.offset).toBeCloseTo(2.05);
      expect(late.when).toBeCloseTo(10.05);
      expect(late.lateMs).toBeCloseTo(2000);
    }
    expect(planStart(0, 40, 0, 30)).toEqual({ kind: "too_late" });
  });
});

describe("prefetch (spec §7.3)", () => {
  const ref = (id: string) => ({ asset_id: id, url: `/api/audio/${id}`, duration_ms: 20_000 });

  it("fetches current first and next only when not playing", () => {
    const slots = { current: ref("a1"), next: ref("a2") };
    expect(assetsToFetch(slots, new Set(), false)).toEqual(["a1", "a2"]);
    expect(assetsToFetch(slots, new Set(), true)).toEqual(["a1"]);
    expect(assetsToFetch(slots, new Set(["a1"]), false)).toEqual(["a2"]);
    expect(assetsToFetch({ current: null, next: null }, new Set(), false)).toEqual([]);
  });
});

describe("reports", () => {
  it("builds valid audio statuses", () => {
    const est = { offset: 3, rttMin: 40, epsilon: 20 };
    expect(buildAudioStatus("READY", "a1", null, est)).toEqual({
      t: "AUDIO_STATUS",
      state: "READY",
      asset_id: "a1",
      clock: { offset: 3, rtt_min: 40 },
    });
    expect(buildAudioStatus("LOCKED", "a1", null, null)).toEqual({
      t: "AUDIO_STATUS",
      state: "LOCKED",
      clock: { offset: null, rtt_min: null },
    });
  });

  it("clamps playback reports into protocol bounds", () => {
    const report = buildPlaybackReport("pl_1", 10_000_000, null, 9);
    expect(report.late_ms).toBe(600_000);
    expect(report.out_latency).toBe(5_000);
  });
});
