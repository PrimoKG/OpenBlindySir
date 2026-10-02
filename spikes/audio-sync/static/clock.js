// Pure clock-sync and scheduling math for spike S0 (spec docs/sync.md sections 9.2 and 9.5).
// No DOM, no Web Audio objects: every input is passed explicitly so that `node --test` can
// exercise it (see clock.test.mjs). All times are milliseconds unless the name ends in S
// (seconds, Web Audio context time).

export const MAX_SAMPLES = 30; // keep the last 30 samples
export const BEST_K = 3; // estimate = median theta of the 3 lowest-RTT samples
export const BURST_COUNT = 8; // burst: 8 pings...
export const BURST_SPACING_MS = 50; // ...50 ms apart
export const KEEPALIVE_MS = 5000; // one ping every 5 s (also the heartbeat)
export const CATCH_UP_LEAD_S = 0.05; // "T already past": start 50 ms from now

/** One PING/PONG exchange: t0 = send (local), t1 = receive (local), s = server clock. */
export function makeSample(t0, t1, s) {
  const rtt = t1 - t0;
  return { t0, t1, s, rtt, theta: s - (t0 + t1) / 2 }; // server time = local time + theta
}

export function median(values) {
  if (values.length === 0) return NaN;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

export class ClockSync {
  constructor({ maxSamples = MAX_SAMPLES, bestK = BEST_K } = {}) {
    this.maxSamples = maxSamples;
    this.bestK = bestK;
    this.samples = [];
  }

  /** Add a sample; returns it, or null when it is invalid (negative RTT, NaN). */
  add(t0, t1, s) {
    const sample = makeSample(t0, t1, s);
    if (!Number.isFinite(sample.rtt) || !Number.isFinite(sample.theta) || sample.rtt < 0) {
      return null;
    }
    this.samples.push(sample);
    if (this.samples.length > this.maxSamples) {
      this.samples.splice(0, this.samples.length - this.maxSamples);
    }
    return sample;
  }

  reset() {
    this.samples = [];
  }

  get count() {
    return this.samples.length;
  }

  /** { theta, rttMin, epsilon, count, lastRtt } or null when there is no sample. */
  estimate() {
    if (this.samples.length === 0) return null;
    const best = [...this.samples].sort((a, b) => a.rtt - b.rtt).slice(0, this.bestK);
    const rttMin = best[0].rtt;
    return {
      theta: median(best.map((x) => x.theta)),
      rttMin,
      epsilon: rttMin / 2,
      count: this.samples.length,
      lastRtt: this.samples[this.samples.length - 1].rtt,
    };
  }
}

/** True when getOutputTimestamp() returned something usable (spec: fall back if absent or 0). */
export function isValidOutputTimestamp(ts) {
  return (
    ts != null &&
    Number.isFinite(ts.contextTime) &&
    Number.isFinite(ts.performanceTime) &&
    ts.contextTime > 0 &&
    ts.performanceTime > 0
  );
}

/**
 * Context time T at which to call source.start() so that the sound is HEARD at server time
 * startAt (spec 9.5 step 2).
 *   tLocal = startAt - theta - manualLatencyMs
 *   with getOutputTimestamp: T = ts.contextTime + (tLocal - ts.performanceTime) / 1000
 *   fallback:                T = currentTime + (tLocal - perfNow) / 1000
 *                                - (outputLatency ?? baseLatency ?? 0)
 */
export function computeStartTime({
  startAt,
  theta,
  manualLatencyMs = 0,
  outputTimestamp = null,
  currentTime,
  perfNow,
  outputLatency,
  baseLatency,
}) {
  const tLocal = startAt - theta - manualLatencyMs;
  if (isValidOutputTimestamp(outputTimestamp)) {
    return {
      T: outputTimestamp.contextTime + (tLocal - outputTimestamp.performanceTime) / 1000,
      tLocal,
      apiUsed: "getOutputTimestamp",
      latencyS: effectiveOutputLatency({ outputTimestamp, currentTime, perfNow }),
    };
  }
  let apiUsed = "fallback:none";
  if (outputLatency != null) apiUsed = "fallback:outputLatency";
  else if (baseLatency != null) apiUsed = "fallback:baseLatency";
  const latencyS = outputLatency ?? baseLatency ?? 0;
  return {
    T: currentTime + (tLocal - perfNow) / 1000 - latencyS,
    tLocal,
    apiUsed,
    latencyS,
  };
}

/**
 * Output latency implied by getOutputTimestamp (seconds): context time being rendered now
 * minus context time being heard now. Diagnostic only.
 */
export function effectiveOutputLatency({ outputTimestamp, currentTime, perfNow }) {
  if (!isValidOutputTimestamp(outputTimestamp)) return null;
  const heardNow =
    outputTimestamp.contextTime + (perfNow - outputTimestamp.performanceTime) / 1000;
  return currentTime - heardNow;
}

/**
 * Spec 9.5 step 3. If T is in the future: start(T, clipOffset). Otherwise late = now - T and
 * start(now + 0.05, clipOffset + late + 0.05), unless that is beyond the clip duration.
 * Returns { when, offset, lateMs, skipped } (when/offset in seconds).
 */
export function planStart({ T, now, clipOffset = 0, duration, lead = CATCH_UP_LEAD_S }) {
  if (T > now) {
    return { when: T, offset: clipOffset, lateMs: 0, skipped: false };
  }
  const late = now - T;
  const offset = clipOffset + late + lead;
  if (duration != null && offset >= duration) {
    return { when: null, offset, lateMs: late * 1000, skipped: true };
  }
  return { when: now + lead, offset, lateMs: late * 1000, skipped: false };
}
