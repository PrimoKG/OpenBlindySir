// Start scheduling in AudioContext time (spec §9.5). Pure functions, unit-tested.

export interface TimeSource {
  /** ctx.getOutputTimestamp(), when available; includes the known output latency. */
  readonly ts: { readonly contextTime: number; readonly performanceTime: number } | null;
  readonly currentTime: number;
  readonly perfNow: number;
  readonly outputLatency?: number | undefined;
  readonly baseLatency?: number | undefined;
}

/** AudioContext time (seconds) matching a local performance.now() instant (ms). */
export function contextTimeForLocal(tLocal: number, src: TimeSource): number {
  if (src.ts && src.ts.performanceTime > 0) {
    return src.ts.contextTime + (tLocal - src.ts.performanceTime) / 1000;
  }
  const latency = src.outputLatency ?? src.baseLatency ?? 0;
  return src.currentTime + (tLocal - src.perfNow) / 1000 - latency;
}

export type StartPlan =
  | { readonly kind: "scheduled"; readonly when: number; readonly offset: number }
  | {
      readonly kind: "catchup";
      readonly when: number;
      readonly offset: number;
      readonly lateMs: number;
    }
  | { readonly kind: "too_late" };

const CATCHUP_MARGIN_S = 0.05;

/** Future T: start at T. Past T: start now + 50 ms at the position the others are at. */
export function planStart(T: number, now: number, clipOffset: number, duration: number): StartPlan {
  if (T > now) {
    return { kind: "scheduled", when: T, offset: clipOffset };
  }
  const late = now - T;
  const offset = clipOffset + late + CATCHUP_MARGIN_S;
  if (offset >= duration) {
    return { kind: "too_late" };
  }
  return { kind: "catchup", when: now + CATCHUP_MARGIN_S, offset, lateMs: late * 1000 };
}
