// Which clips to download now (spec §7.3): the current clip first; the next one only when
// offered and never during this client's own playback.
import type { AudioSlots } from "../protocol";

export function assetsToFetch(
  slots: AudioSlots,
  have: ReadonlySet<string>,
  localPlaybackActive: boolean,
): string[] {
  const wanted: string[] = [];
  if (slots.current && !have.has(slots.current.asset_id)) {
    wanted.push(slots.current.asset_id);
  }
  if (slots.next && !have.has(slots.next.asset_id) && !localPlaybackActive) {
    wanted.push(slots.next.asset_id);
  }
  return wanted;
}
