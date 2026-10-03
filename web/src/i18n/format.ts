import { getLanguage } from "./index";

const MINUS = "−";
const NARROW_NBSP = " ";

/** 4237 ms → "4,2 s" (tenth of a second, comma). */
export function formatSeconds(ms: number): string {
  const tenths = Math.round(Math.max(0, ms) / 100);
  return `${Math.floor(tenths / 10)}${getLanguage() === "fr" ? "," : "."}${tenths % 10} s`;
}

/** +2, −1 (true minus sign), 0. */
export function formatDelta(n: number): string {
  if (n > 0) {
    return `+${n}`;
  }
  if (n < 0) {
    return `${MINUS}${Math.abs(n)}`;
  }
  return "0";
}

/** "1.", "2≈" for a near tie, "—" without a rank. */
export function formatRank(order: number | null, nearTie: boolean): string {
  if (order === null) {
    return "—";
  }
  return nearTie ? `${order}≈` : `${order}.`;
}

/** 5273 → "5 273" with a narrow no-break space. */
export function formatCount(n: number): string {
  return String(Math.trunc(n)).replace(/\B(?=(\d{3})+(?!\d))/g, NARROW_NBSP);
}

/** Audio delay badge: "⚠ audio +2,3 s" from 300 ms, "⚠ audio ?" without READY, else null. */
export function formatLate(ms: number | null): string | null {
  if (ms === null) {
    return "⚠ audio ?";
  }
  if (ms >= 300) {
    return `⚠ audio +${formatSeconds(ms)}`;
  }
  return null;
}
