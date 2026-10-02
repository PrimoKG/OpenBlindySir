// Decoded-buffer measurements for spike S0 (pure, testable with node --test).

/**
 * Energy centroid (seconds) of the strongest burst found in [loS, hiS] of a decoded channel.
 * Mirrors burst_centroid_s() in server.py. Comparing it with the burst centre written by the
 * generator gives the decoder offset: how far a decoder shifts the audio (encoder priming /
 * edit list / pre-skip handling). Returns null when the window is empty or silent.
 */
export function burstCentroid(samples, sampleRate, loS, hiS, halfMs = 15) {
  const lo = Math.max(0, Math.round(loS * sampleRate));
  const hi = Math.min(samples.length, Math.round(hiS * sampleRate));
  if (hi <= lo) return null;
  let peak = lo;
  let peakAbs = -1;
  for (let i = lo; i < hi; i++) {
    const a = Math.abs(samples[i]);
    if (a > peakAbs) {
      peakAbs = a;
      peak = i;
    }
  }
  const half = Math.round((halfMs / 1000) * sampleRate);
  const a = Math.max(0, peak - half);
  const b = Math.min(samples.length, peak + half);
  let sum = 0;
  let weighted = 0;
  for (let i = a; i < b; i++) {
    const e = samples[i] * samples[i];
    sum += e;
    weighted += i * e;
  }
  if (sum <= 0) return null;
  return weighted / sum / sampleRate;
}
