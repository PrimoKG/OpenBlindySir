// AudioEngine: ONE AudioContext per page, created at the first gesture and never re-created.
// Downloads and decodes clips, schedules PLAY at the server's start_at (spec §9.5) and
// reports its state. No resynchronisation during playback (§9.6).
import type {
  AnyView,
  AudioErrorCode,
  AudioState,
  AudioStatus,
  ClientMessage,
  PlayInfo,
  PlayMsg,
} from "../protocol";
import { readLocal, writeLocal } from "../storage";
import { type ClockEstimator, serverToLocal } from "./clock";
import { assetsToFetch } from "./prefetch";
import { buildAudioStatus, buildPlaybackReport } from "./report";
import { contextTimeForLocal, planStart, type StartPlan } from "./schedule";
import { applyPlaybackSession } from "./unlock";

const RETRIES_MS = [500, 1000, 2000];
const LATE_NOTICE_MS = 250;

type Send = (msg: ClientMessage) => boolean;

export interface EngineSnapshot {
  readonly state: AudioState;
  readonly contextState: string;
  readonly lateJoinMs: number | null;
  readonly heardConfirmed: boolean;
  readonly volume: number;
}

export class AudioEngine {
  private ctx: AudioContext | null = null;
  private gain: GainNode | null = null;
  private buffers = new Map<string, AudioBuffer>();
  private loading = new Set<string>();
  private source: AudioBufferSourceNode | null = null;
  private scheduledPlayId: string | null = null;
  private playing = false;
  private state: AudioState = "LOCKED";
  private assetId: string | null = null;
  private error: AudioErrorCode | null = null;
  private lateJoinMs: number | null = null;
  private heardConfirmed = false;
  private volume: number;
  private lastView: AnyView | null = null;
  private listeners = new Set<() => void>();
  private snapshot: EngineSnapshot;

  constructor(
    private readonly clock: ClockEstimator,
    private send: Send,
  ) {
    const stored = Number(readLocal("volume"));
    this.volume = Number.isFinite(stored) && readLocal("volume") !== null ? stored : 0.8;
    this.snapshot = this.makeSnapshot();
  }

  setSender(send: Send): void {
    this.send = send;
  }

  // --- observable state -----------------------------------------------------------------

  private makeSnapshot(): EngineSnapshot {
    return {
      state: this.state,
      contextState: this.ctx?.state ?? "none",
      lateJoinMs: this.lateJoinMs,
      heardConfirmed: this.heardConfirmed,
      volume: this.volume,
    };
  }

  getSnapshot = (): EngineSnapshot => this.snapshot;

  subscribe = (callback: () => void): (() => void) => {
    this.listeners.add(callback);
    return () => this.listeners.delete(callback);
  };

  private changed(): void {
    this.snapshot = this.makeSnapshot();
    for (const listener of this.listeners) {
      listener();
    }
  }

  status(): AudioStatus {
    return buildAudioStatus(this.state, this.assetId, this.error, this.clock.estimate());
  }

  private setState(state: AudioState, assetId: string | null, error: AudioErrorCode | null = null) {
    this.state = state;
    this.assetId = assetId;
    this.error = error;
    this.send(this.status());
    this.changed();
  }

  // --- unlock ---------------------------------------------------------------------------

  /** Must be called inside a user gesture (spec §9.7). */
  async unlock(): Promise<void> {
    if (!this.ctx) {
      this.ctx = new AudioContext({ latencyHint: "interactive" });
      this.gain = this.ctx.createGain();
      this.gain.gain.value = this.volume;
      this.gain.connect(this.ctx.destination);
      this.ctx.onstatechange = () => this.onContextState();
    }
    applyPlaybackSession();
    try {
      await this.ctx.resume();
    } catch {
      // stays suspended: the overlay keeps offering to retry
    }
    this.onContextState();
  }

  private onContextState(): void {
    if (!this.ctx) {
      return;
    }
    if (this.ctx.state !== "running") {
      if (this.state !== "LOCKED") {
        this.setState("LOCKED", null);
      }
    } else if (this.state === "LOCKED") {
      this.setState("IDLE", null);
      if (this.lastView) {
        this.syncWithView(this.lastView);
      }
    }
    this.changed();
  }

  get unlocked(): boolean {
    return this.ctx?.state === "running";
  }

  testBeep(): void {
    if (!this.ctx || !this.gain) {
      return;
    }
    const osc = this.ctx.createOscillator();
    const envelope = this.ctx.createGain();
    osc.frequency.value = 880;
    envelope.gain.value = 0.3;
    osc.connect(envelope).connect(this.gain);
    const now = this.ctx.currentTime;
    osc.start(now);
    osc.stop(now + 0.15);
  }

  confirmHeard(): void {
    this.heardConfirmed = true;
    this.changed();
  }

  setVolume(value: number): void {
    this.volume = Math.min(1, Math.max(0, value));
    if (this.gain) {
      this.gain.gain.value = this.volume;
    }
    writeLocal("volume", String(this.volume));
    this.changed();
  }

  // --- clips ----------------------------------------------------------------------------

  /** Download what the view offers (never N+1 during our own playback) and late-start. */
  syncWithView(view: AnyView): void {
    this.lastView = view;
    if (!this.unlocked) {
      return;
    }
    if (view.paused && !view.paused.resume_at && this.scheduledPlayId) {
      this.stop(this.scheduledPlayId, view.paused.paused_at);
    }
    if (!view.play && !view.paused && this.playing) {
      this.stopSource();
      this.playing = false;
    }
    const keep = new Set<string>();
    for (const ref of [view.audio.current, view.audio.next]) {
      if (ref) {
        keep.add(ref.asset_id);
      }
    }
    for (const id of [...this.buffers.keys()]) {
      if (!keep.has(id)) {
        this.buffers.delete(id);
      }
    }
    const have = new Set([...this.buffers.keys(), ...this.loading]);
    for (const assetId of assetsToFetch(view.audio, have, this.playing)) {
      const ref = view.audio.current?.asset_id === assetId ? view.audio.current : view.audio.next;
      if (ref) {
        void this.fetchDecode(assetId, ref.url);
      }
    }
    if (
      view.play &&
      view.play.play_id !== this.scheduledPlayId &&
      this.buffers.has(view.play.asset_id)
    ) {
      this.play(view.play);
    }
  }

  private async fetchDecode(assetId: string, url: string): Promise<void> {
    if (!this.ctx) {
      return;
    }
    this.loading.add(assetId);
    if (!this.playing) {
      this.setState("LOADING", assetId);
    }
    let lastError: AudioErrorCode = "FETCH_FAILED";
    for (let attempt = 0; attempt <= RETRIES_MS.length; attempt += 1) {
      try {
        const response = await fetch(url, { credentials: "same-origin", cache: "no-store" });
        if (!response.ok) {
          throw new Error("fetch");
        }
        const data = await response.arrayBuffer();
        lastError = "DECODE_FAILED";
        const buffer = await this.ctx.decodeAudioData(data);
        this.buffers.set(assetId, buffer);
        this.loading.delete(assetId);
        if (!this.playing) {
          this.setState("READY", assetId);
        } else {
          this.send(buildAudioStatus("READY", assetId, null, this.clock.estimate()));
        }
        if (this.lastView) {
          this.syncWithView(this.lastView);
        }
        return;
      } catch {
        const wait = RETRIES_MS[attempt];
        if (wait === undefined) {
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, wait));
      }
    }
    this.loading.delete(assetId);
    this.setState("ERROR", assetId, lastError);
  }

  // --- playback ---------------------------------------------------------------------------

  play(msg: PlayMsg | PlayInfo): StartPlan | null {
    const ctx = this.ctx;
    const buffer = this.buffers.get(msg.asset_id);
    if (!ctx || !this.gain || !buffer || msg.play_id === this.scheduledPlayId) {
      return null;
    }
    this.stopSource();
    const estimate = this.clock.estimate();
    const tLocal = serverToLocal(msg.start_at, estimate?.offset ?? 0);
    const timestamp =
      typeof ctx.getOutputTimestamp === "function" ? ctx.getOutputTimestamp() : null;
    const T = contextTimeForLocal(tLocal, {
      ts:
        timestamp && timestamp.contextTime !== undefined && timestamp.performanceTime !== undefined
          ? { contextTime: timestamp.contextTime, performanceTime: timestamp.performanceTime }
          : null,
      currentTime: ctx.currentTime,
      perfNow: performance.now(),
      outputLatency: ctx.outputLatency,
      baseLatency: ctx.baseLatency,
    });
    const plan = planStart(T, ctx.currentTime, msg.clip_offset, buffer.duration);
    this.scheduledPlayId = msg.play_id;
    if (plan.kind === "too_late") {
      return plan;
    }
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.gain);
    source.onended = () => {
      if (this.source === source) {
        this.source = null;
        this.playing = false;
        this.setState("IDLE", null);
        if (this.lastView) {
          this.syncWithView(this.lastView);
        }
      }
    };
    source.start(plan.when, plan.offset);
    this.source = source;
    this.playing = true;
    this.lateJoinMs = plan.kind === "catchup" && plan.lateMs >= LATE_NOTICE_MS ? plan.lateMs : null;
    this.setState("PLAYING", msg.asset_id);
    const lateMs = plan.kind === "catchup" ? plan.lateMs : 0;
    this.send(
      buildPlaybackReport(msg.play_id, lateMs, estimate, ctx.outputLatency ?? ctx.baseLatency ?? 0),
    );
    return plan;
  }

  stop(playId: string, at?: number | null): void {
    if (playId === this.scheduledPlayId) {
      if (at != null && (!this.source || !this.ctx)) return;
      if (at != null && this.source && this.ctx) {
        const local = serverToLocal(at, this.clock.estimate()?.offset ?? 0);
        const timestamp =
          typeof this.ctx.getOutputTimestamp === "function" ? this.ctx.getOutputTimestamp() : null;
        const when = Math.max(
          this.ctx.currentTime,
          contextTimeForLocal(local, {
            ts:
              timestamp &&
              timestamp.contextTime !== undefined &&
              timestamp.performanceTime !== undefined
                ? { contextTime: timestamp.contextTime, performanceTime: timestamp.performanceTime }
                : null,
            currentTime: this.ctx.currentTime,
            perfNow: performance.now(),
            outputLatency: this.ctx.outputLatency,
            baseLatency: this.ctx.baseLatency,
          }),
        );
        try {
          this.source.stop(when);
        } catch {
          /* already stopped */
        }
        return;
      }
      this.stopSource();
      this.playing = false;
      this.setState(this.unlocked ? "IDLE" : "LOCKED", null);
    }
  }

  private stopSource(): void {
    if (this.source) {
      const source = this.source;
      this.source = null;
      try {
        source.stop();
      } catch {
        // already stopped
      }
    }
  }

  debugInfo(): Record<string, unknown> {
    const estimate = this.clock.estimate();
    return {
      context: this.ctx?.state ?? "none",
      outputLatency: this.ctx?.outputLatency ?? null,
      baseLatency: this.ctx?.baseLatency ?? null,
      offset: estimate?.offset ?? null,
      rttMin: estimate?.rttMin ?? null,
      epsilon: estimate?.epsilon ?? null,
      state: this.state,
      lateJoinMs: this.lateJoinMs,
    };
  }
}
