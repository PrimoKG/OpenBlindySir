// Wires the view store, the clock, the audio engine and the socket together.
// No game rule here: the client only displays the server's view and sends intents.

import { ClockEstimator } from "../audio/clock";
import { AudioEngine } from "../audio/engine";
import { GameSocket, type SocketStatus } from "../net/socket";
import { createViewStore, type ViewStore } from "../net/viewStore";
import type { ClientMessage, ErrorCode, ServerMessage } from "../protocol";

export interface UiState {
  readonly socket: SocketStatus;
  readonly pendingSubmit: boolean;
  readonly acceptedRound: string | null;
  readonly toast: { readonly code: ErrorCode; readonly at: number } | null;
}

export class GameController {
  readonly store: ViewStore = createViewStore();
  readonly clock = new ClockEstimator();
  readonly engine: AudioEngine;
  readonly socket: GameSocket;
  private ui: UiState = {
    socket: "connecting",
    pendingSubmit: false,
    acceptedRound: null,
    toast: null,
  };
  private uiListeners = new Set<() => void>();

  constructor() {
    this.engine = new AudioEngine(this.clock, () => false);
    this.socket = new GameSocket({
      store: this.store,
      clock: this.clock,
      onCritical: (msg) => this.onCritical(msg),
      onStatus: (status) => this.patchUi({ socket: status }),
      audioStatus: () => this.engine.status(),
      onPendingChange: (pending) => this.patchUi({ pendingSubmit: pending }),
    });
    this.engine.setSender((msg) => this.socket.send(msg));
    this.store.subscribe(() => {
      const snapshot = this.store.getSnapshot();
      if (snapshot) {
        this.engine.syncWithView(snapshot.view);
        const round = snapshot.view.round;
        if (round && round.state === "LOADING") {
          this.socket.burstSync();
        }
      }
    });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        this.socket.burstSync();
        this.socket.ensureConnected();
      }
    });
  }

  start(): void {
    void this.socket.connect();
  }

  send(msg: ClientMessage): boolean {
    return this.socket.send(msg);
  }

  submitAnswer(roundId: string, text: string): void {
    this.socket.submitAnswer(roundId, text);
  }

  private onCritical(msg: ServerMessage): void {
    switch (msg.t) {
      case "PLAY":
        this.engine.play(msg);
        return;
      case "STOP":
        this.engine.stop(msg.play_id, msg.stop_at);
        return;
      case "ANSWER_ACK":
        if (msg.status === "accepted" || msg.reason === "already_locked") {
          this.patchUi({ acceptedRound: msg.round_id });
        } else if (msg.reason) {
          this.patchUi({ toast: { code: "invalid_state", at: Date.now() } });
        }
        return;
      case "ERROR":
        if (msg.code !== "stale_command") {
          this.patchUi({ toast: { code: msg.code, at: Date.now() } });
        }
        return;
      default:
        return;
    }
  }

  // --- UI state store -----------------------------------------------------------------------

  getUi = (): UiState => this.ui;

  subscribeUi = (callback: () => void): (() => void) => {
    this.uiListeners.add(callback);
    return () => this.uiListeners.delete(callback);
  };

  private patchUi(patch: Partial<UiState>): void {
    this.ui = { ...this.ui, ...patch };
    for (const listener of this.uiListeners) {
      listener();
    }
  }

  dismissToast(): void {
    this.patchUi({ toast: null });
  }
}
