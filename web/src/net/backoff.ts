// Reconnection delay: min(10 s, 500 ms · 2^attempt) with ±20 % jitter.
export function nextDelay(attempt: number, rand: () => number): number {
  const base = Math.min(10_000, 500 * 2 ** Math.max(0, attempt));
  return base * (0.8 + 0.4 * rand());
}
