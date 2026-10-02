// Game WebSocket (spec §8.2, §9.2): HELLO, clock bursts, keep-alive, reconnection,
// one pending ANSWER_SUBMIT while disconnected.
import { type ClockEstimator, sampleFrom } from "../audio/clock";
import {
  type AudioStatus,
  type ClientMessage,
  type ErrorCode,
  PROTOCOL_VERSION,
  type ServerMessage,
  type StateMsg,
} from "../protocol";
import { readSession, writeSession } from "../storage";
import { api } from "./api";
import { nextDelay } from "./backoff";
import { closeAction } from "./closeCodes";
import type { ViewStore } from "./viewStore";

export type SocketStatus =
  | "connecting"
  | "open"
  | "reconnecting"
  | "superseded"
  | "kicked"
  | "session_ended"
  | "rejoin";

const PING_INTERVAL_MS = 5_000;
const BURST_PINGS = 8;
const BURST_SPACING_MS = 50;
export const CLIENT_VERSION = "0.1.0";

interface Options {
  readonly store: ViewStore;
  readonly clock: ClockEstimator;
  readonly onCritical: (msg: ServerMessage) => void;
  readonly onStatus: (status: SocketStatus) => void;
  readonly audioStatus: () => AudioStatus;
  readonly onPendingChange?: (pending: boolean) => void;
}

export class GameSocket {
  private ws: WebSocket | null = null;
  private attempt = 0;
  private firstState = true;
  private lastError: ErrorCode | null = null;
  private pingTimer: number | undefined;
  private retryTimer: number | undefined;
  private pending: { roundId: string; text: string } | null = null;
  private stopped = false;
  status: SocketStatus = "connecting";

  constructor(private readonly opts: Options) {}

  private setStatus(status: SocketStatus): void {
    this.status = status;
    this.opts.onStatus(status);
  }

  async connect(): Promise<void> {
    this.stopped = false;
    const session = await api.session(); // also refreshes the cookie lifetime
    if (!session.ok) {
      if (session.error === "unauthenticated") {
        this.setStatus("rejoin");
        return;
      }
      this.scheduleReconnect();
      return;
    }
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${scheme}://${location.host}/api/ws`);
    this.ws = ws;
    this.firstState = true;
    ws.onopen = () => {
      this.attempt = 0;
      this.lastError = null;
      this.send({ t: "HELLO", client_version: CLIENT_VERSION, protocol: PROTOCOL_VERSION });
      this.send(this.opts.audioStatus());
      this.burstSync();
      window.clearInterval(this.pingTimer);
      this.pingTimer = window.setInterval(() => this.ping(), PING_INTERVAL_MS);
      this.setStatus("open");
    };
    ws.onmessage = (event) => this.onMessage(event);
    ws.onclose = (event) => this.onClose(event.code);
  }

  private onMessage(event: MessageEvent): void {
    const t1 = performance.now(); // read first, before parsing (§9.2)
    let msg: ServerMessage;
    try {
      msg = JSON.parse(String(event.data)) as ServerMessage;
    } catch {
      return;
    }
    switch (msg.t) {
      case "PONG":
        this.opts.clock.add(sampleFrom(msg.c, t1, msg.s));
        return;
      case "STATE":
        this.onState(msg);
        return;
      case "ERROR":
        this.lastError = msg.code;
        this.opts.onCritical(msg);
        return;
      default:
        this.opts.onCritical(msg);
    }
  }

  private onState(msg: StateMsg): void {
    const first = this.firstState;
    this.firstState = false;
    this.opts.store.apply(msg, first);
    if (first && this.pending) {
      const round = msg.view.round;
      const pending = this.pending;
      this.pending = null;
      this.opts.onPendingChange?.(false);
      if (round && round.round_id === pending.roundId) {
        this.send({ t: "ANSWER_SUBMIT", round_id: pending.roundId, text: pending.text });
      }
    }
  }

  private onClose(code: number): void {
    window.clearInterval(this.pingTimer);
    this.ws = null;
    if (this.stopped) {
      return;
    }
    const action = closeAction(code, this.lastError);
    switch (action) {
      case "superseded":
        this.setStatus("superseded");
        return;
      case "kicked":
        this.setStatus("kicked");
        return;
      case "session_ended":
        this.opts.store.reset();
        this.setStatus("session_ended");
        return;
      case "reload":
        if (readSession("protocolReload") !== "1") {
          writeSession("protocolReload", "1");
          location.reload();
        }
        return;
      default:
        this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    this.setStatus("reconnecting");
    window.clearTimeout(this.retryTimer);
    const delay = nextDelay(this.attempt, Math.random);
    this.attempt += 1;
    this.retryTimer = window.setTimeout(() => void this.connect(), delay);
  }

  /** Reconnect now (e.g. back to the foreground) if the socket is closed. */
  ensureConnected(): void {
    if (!this.ws && !this.stopped && this.status === "reconnecting") {
      window.clearTimeout(this.retryTimer);
      void this.connect();
    }
  }

  resume(): void {
    this.attempt = 0;
    void this.connect();
  }

  send(msg: ClientMessage): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return false;
    }
    this.ws.send(JSON.stringify(msg));
    return true;
  }

  submitAnswer(roundId: string, text: string): "sent" | "pending" {
    if (this.send({ t: "ANSWER_SUBMIT", round_id: roundId, text })) {
      return "sent";
    }
    this.pending = { roundId, text };
    this.opts.onPendingChange?.(true);
    return "pending";
  }

  private ping(): void {
    this.send({ t: "PING", c: performance.now() });
  }

  burstSync(): void {
    for (let i = 0; i < BURST_PINGS; i += 1) {
      window.setTimeout(() => this.ping(), i * BURST_SPACING_MS);
    }
  }

  close(): void {
    this.stopped = true;
    window.clearInterval(this.pingTimer);
    window.clearTimeout(this.retryTimer);
    this.ws?.close(1000);
  }
}
