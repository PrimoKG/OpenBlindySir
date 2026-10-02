// Latest full view sent by the server; consumed with useSyncExternalStore.
import type { AnyView, StateMsg } from "../protocol";

export interface ViewSnapshot {
  readonly v: number;
  readonly epoch: string;
  readonly view: AnyView;
}

export interface ViewStore {
  getSnapshot(): ViewSnapshot | null;
  subscribe(callback: () => void): () => void;
  /** Accepted iff first STATE of the connection, epoch changed, or a newer per-connection v. */
  apply(msg: StateMsg, firstOfConnection: boolean): boolean;
  reset(): void;
}

export function createViewStore(): ViewStore {
  let snapshot: ViewSnapshot | null = null;
  const listeners = new Set<() => void>();
  const notify = () => {
    for (const listener of listeners) {
      listener();
    }
  };
  return {
    getSnapshot: () => snapshot,
    subscribe(callback) {
      listeners.add(callback);
      return () => listeners.delete(callback);
    },
    apply(msg, firstOfConnection) {
      const epoch = msg.view.session.epoch;
      const accept =
        snapshot === null || firstOfConnection || epoch !== snapshot.epoch || msg.v > snapshot.v;
      if (accept) {
        snapshot = { v: msg.v, epoch, view: msg.view };
        notify();
      }
      return accept;
    },
    reset() {
      snapshot = null;
      notify();
    },
  };
}
