// Clock synchronisation with the server (spec §9.2). Pure functions, unit-tested.
// One sample: t0 = performance.now(), PING{c: t0}, PONG{c, s} received at t1.
// rtt = t1 − t0 ; θ = s − (t0 + t1) / 2  (server time = local time + θ).

export interface Sample {
  readonly rtt: number;
  readonly theta: number;
}

export interface Estimate {
  readonly offset: number;
  readonly rttMin: number;
  readonly epsilon: number;
}

const KEPT_SAMPLES = 30;
const BEST_SAMPLES = 3;

export function sampleFrom(t0: number, t1: number, s: number): Sample {
  return { rtt: t1 - t0, theta: s - (t0 + t1) / 2 };
}

function median(values: readonly number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) {
    return sorted[mid] ?? 0;
  }
  return ((sorted[mid - 1] ?? 0) + (sorted[mid] ?? 0)) / 2;
}

/** Median θ of the 3 samples with the smallest RTT; uncertainty ε ≈ rtt_min / 2. */
export function estimate(samples: readonly Sample[]): Estimate | null {
  if (samples.length === 0) {
    return null;
  }
  const best = [...samples].sort((a, b) => a.rtt - b.rtt).slice(0, BEST_SAMPLES);
  const rttMin = best[0]?.rtt ?? 0;
  return { offset: median(best.map((s) => s.theta)), rttMin, epsilon: rttMin / 2 };
}

export class ClockEstimator {
  private samples: Sample[] = [];

  add(sample: Sample): void {
    if (!Number.isFinite(sample.rtt) || sample.rtt < 0) {
      return;
    }
    this.samples.push(sample);
    if (this.samples.length > KEPT_SAMPLES) {
      this.samples.shift();
    }
  }

  estimate(): Estimate | null {
    return estimate(this.samples);
  }
}

/** Local performance.now() time of a server instant: t_local = start_at − θ − manual latency. */
export function serverToLocal(serverMs: number, offset: number, manualLatencyMs = 0): number {
  return serverMs - offset - manualLatencyMs;
}
