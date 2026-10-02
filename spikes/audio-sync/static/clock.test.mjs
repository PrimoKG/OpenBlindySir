// Run: node --test spikes/audio-sync/static/
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ClockSync,
  computeStartTime,
  effectiveOutputLatency,
  makeSample,
  median,
  planStart,
} from "./clock.js";
import { burstCentroid } from "./measure.js";

const close = (actual, expected, tol = 1e-9) =>
  assert.ok(Math.abs(actual - expected) <= tol, `${actual} != ${expected} (tol ${tol})`);

test("sample: rtt and theta = s - (t0+t1)/2", () => {
  const s = makeSample(100, 140, 10120);
  assert.equal(s.rtt, 40);
  assert.equal(s.theta, 10000);
});

test("median of odd and even lists", () => {
  assert.equal(median([3, 1, 2]), 2);
  assert.equal(median([4, 1, 3, 2]), 2.5);
  assert.ok(Number.isNaN(median([])));
});

test("estimate is the median theta of the 3 lowest-RTT samples", () => {
  const c = new ClockSync();
  assert.equal(c.estimate(), null);
  // true offset 5000; low-RTT samples are accurate, high-RTT ones are asymmetric
  c.add(0, 10, 5000 + 5 + 1); // rtt 10, theta 5001
  c.add(100, 108, 5100 + 4 - 2); // rtt 8, theta 4998
  c.add(200, 290, 5200 + 80); // rtt 90, theta 5035 (asymmetric path)
  c.add(300, 312, 5300 + 6 + 0.5); // rtt 12, theta 5000.5
  c.add(400, 600, 5400 + 20); // rtt 200, theta 4920
  const e = c.estimate();
  assert.equal(e.count, 5);
  assert.equal(e.rttMin, 8);
  assert.equal(e.epsilon, 4);
  assert.equal(e.lastRtt, 200);
  assert.equal(e.theta, 5000.5); // median of {4998, 5001, 5000.5}
});

test("only the last 30 samples are kept", () => {
  const c = new ClockSync();
  c.add(0, 1, 1000.5); // excellent sample (rtt 1, theta 1000)
  for (let i = 1; i <= 29; i++) c.add(i * 100, i * 100 + 50, i * 100 + 25 + 2000);
  assert.equal(c.count, 30);
  assert.equal(c.estimate().rttMin, 1);
  c.add(5000, 5050, 5025 + 2000); // pushes the excellent one out
  assert.equal(c.count, 30);
  assert.equal(c.estimate().rttMin, 50);
  assert.equal(c.estimate().theta, 2000);
});

test("invalid samples are rejected", () => {
  const c = new ClockSync();
  assert.equal(c.add(10, 5, 100), null); // negative rtt
  assert.equal(c.add(0, NaN, 100), null);
  assert.equal(c.count, 0);
});

test("start time with getOutputTimestamp includes the output latency", () => {
  // heard 2 s after ts.performanceTime, in local time
  const r = computeStartTime({
    startAt: 12000, // server ms
    theta: 1000, // server = local + 1000  -> tLocal = 11000 - manual
    manualLatencyMs: 0,
    outputTimestamp: { contextTime: 4.0, performanceTime: 9000 },
    currentTime: 4.05, // 50 ms rendered ahead of what is heard (output latency)
    perfNow: 9000,
    outputLatency: 0.02,
    baseLatency: 0.01,
  });
  assert.equal(r.apiUsed, "getOutputTimestamp");
  close(r.T, 6.0);
  close(r.latencyS, 0.05);
  assert.equal(r.tLocal, 11000);
});

test("manual latency is subtracted from the local target", () => {
  const r = computeStartTime({
    startAt: 12000,
    theta: 1000,
    manualLatencyMs: 100,
    outputTimestamp: { contextTime: 4.0, performanceTime: 9000 },
    currentTime: 4.0,
    perfNow: 9000,
  });
  close(r.T, 5.9);
});

test("fallback order: outputLatency, then baseLatency, then 0", () => {
  const base = { startAt: 12000, theta: 1000, currentTime: 4.0, perfNow: 9000 };
  let r = computeStartTime({ ...base, outputLatency: 0.03, baseLatency: 0.01 });
  assert.equal(r.apiUsed, "fallback:outputLatency");
  close(r.T, 6.0 - 0.03);
  r = computeStartTime({ ...base, outputLatency: undefined, baseLatency: 0.01 });
  assert.equal(r.apiUsed, "fallback:baseLatency");
  close(r.T, 6.0 - 0.01);
  r = computeStartTime({ ...base });
  assert.equal(r.apiUsed, "fallback:none");
  close(r.T, 6.0);
});

test("getOutputTimestamp returning zeros falls back", () => {
  const r = computeStartTime({
    startAt: 12000,
    theta: 1000,
    outputTimestamp: { contextTime: 0, performanceTime: 0 },
    currentTime: 4.0,
    perfNow: 9000,
    outputLatency: 0.02,
  });
  assert.equal(r.apiUsed, "fallback:outputLatency");
  close(r.T, 5.98);
});

test("effective output latency is null without a valid timestamp", () => {
  assert.equal(effectiveOutputLatency({ outputTimestamp: null, currentTime: 1, perfNow: 1 }), null);
  close(
    effectiveOutputLatency({
      outputTimestamp: { contextTime: 10, performanceTime: 5000 },
      currentTime: 10.13,
      perfNow: 5100,
    }),
    0.03,
  );
});

test("plan: T in the future starts at T", () => {
  assert.deepEqual(planStart({ T: 5, now: 4, clipOffset: 0, duration: 30 }), {
    when: 5,
    offset: 0,
    lateMs: 0,
    skipped: false,
  });
});

test("plan: T past -> start(now + 0.05, offset + late + 0.05)", () => {
  const p = planStart({ T: 3, now: 5.3, clipOffset: 1, duration: 30 });
  close(p.when, 5.35);
  close(p.offset, 1 + 2.3 + 0.05);
  close(p.lateMs, 2300, 1e-6);
  assert.equal(p.skipped, false);
});

test("plan: skipped when the delay exceeds the clip", () => {
  const p = planStart({ T: 0, now: 31, clipOffset: 0, duration: 30 });
  assert.equal(p.skipped, true);
  assert.equal(p.when, null);
});

test("burst centroid finds the centre of a Hann burst", () => {
  const fs = 48000;
  const x = new Float32Array(fs);
  const onset = 24000; // 0.5 s
  const n = 480; // 10 ms
  for (let k = 0; k < n; k++) {
    const w = Math.sin((Math.PI * (k + 0.5)) / n) ** 2;
    x[onset + k] = 0.8 * w * Math.sin((2 * Math.PI * 2000 * k) / fs);
  }
  const c = burstCentroid(x, fs, 0.3, 0.7);
  close(c, 0.505, 0.0002); // within 0.2 ms
  assert.equal(burstCentroid(new Float32Array(100), fs, 0, 0.001), null);
});
