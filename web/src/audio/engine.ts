// One live AudioContext, created by a gesture; only a permanently closed context is replaced.
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
import { applyPlaybackSession, releasePlaybackSession } from "./unlock";

const RETRIES_MS = [500, 1000, 2000];
const LATE_NOTICE_MS = 250;

type Send = (msg: ClientMessage) => boolean;

export interface EngineSnapshot {
  readonly state: AudioState;
  readonly contextState: string;
  readonly lateJoinMs: number | null;
  readonly heardConfirmed: boolean;
  readonly volume: number;
  readonly manualLatencyMs: number;
}

export class AudioEngine {
  private ctx: AudioContext | null = null;
  private gain: GainNode | null = null;
  private buffers = new Map<string, AudioBuffer>();
  private loading = new Set<string>();
  private requests = new Map<string, AbortController>();
  private active = true;
  private source: AudioBufferSourceNode | null = null;
  private scheduledPlayId: string | null = null;
  private playing = false;
  private state: AudioState = "LOCKED";
  private assetId: string | null = null;
  private error: AudioErrorCode | null = null;
  private lateJoinMs: number | null = null;
  private heardConfirmed = false;
  private volume: number;
  private manualLatencyMs: number;
  private appliedLatencyMs = 0;
  private lastView: AnyView | null = null;
  private listeners = new Set<() => void>();
  private snapshot: EngineSnapshot;

  constructor(
    private readonly clock: ClockEstimator,
    private send: Send,
  ) {
    const stored = Number(readLocal("volume"));
    this.volume =
      Number.isFinite(stored) && readLocal("volume") !== null
        ? Math.min(1, Math.max(0, stored))
        : 0.8;
    const latency = Number(readLocal("manualLatencyMs"));
    this.manualLatencyMs = Number.isFinite(latency) ? Math.min(500, Math.max(-500, latency)) : 0;
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
      manualLatencyMs: this.manualLatencyMs,
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
    if (!this.active) return;
    if (this.ctx?.state === "closed") {
      this.ctx.onstatechange = null;
      this.ctx = null;
      this.gain = null;
    }
    if (!this.ctx) {
      this.ctx = new AudioContext({ latencyHint: "interactive" });
      this.gain = this.ctx.createGain();
      this.gain.gain.value = this.volume;
      this.gain.connect(this.ctx.destination);
      this.ctx.onstatechange = () => this.onContextState();
    }
    applyPlaybackSession();
    if (this.ctx.state !== "running") this.onContextState();
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
      if (this.ctx.state === "closed") {
        for (const request of this.requests.values()) request.abort();
        this.requests.clear();
        this.loading.clear();
      }
      // A suspended context freezes its old source. Discard it so recovery joins
      // the server's current position instead of continuing delayed audio.
      this.stopSource();
      this.playing = false;
      this.scheduledPlayId = null;
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

  /** Refresh after returning from background, even if a mobile state event was missed. */
  refreshContextState(): void {
    this.onContextState();
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
    if (!Number.isFinite(value)) return;
    this.volume = Math.min(1, Math.max(0, value));
    if (this.gain) {
      this.gain.gain.value = this.volume;
    }
    writeLocal("volume", String(this.volume));
    this.changed();
  }

  private finaleCues = new Set<string>();

  /** Small original musical cues, scheduled on the same clock and context as playback. */
  playFinaleCue(id: string, kind: "award" | "reveal" | "win", at?: number): void {
    if (this.finaleCues.has(id)) return;
    this.finaleCues.add(id);
    if (this.finaleCues.size > 64)
      this.finaleCues.delete(this.finaleCues.values().next().value ?? "");
    if (
      readLocal("finaleSounds") === "off" ||
      !this.ctx ||
      !this.gain ||
      !this.unlocked ||
      this.playing
    )
      return;
    const estimate = this.clock.estimate();
    const local = at == null ? performance.now() : at - (estimate?.offset ?? 0);
    // A reconnect, restored ceremony, or background tab must not replay stale applause.
    if (performance.now() - local > 600 || local - performance.now() > 1500) return;
    const start = this.ctx.currentTime + Math.max(0, (local - performance.now()) / 1000);
    const notes =
      kind === "win"
        ? [523.25, 659.25, 783.99, 1046.5]
        : kind === "reveal"
          ? [392, 523.25]
          : [659.25, 783.99];
    for (const [index, frequency] of notes.entries()) {
      const osc = this.ctx.createOscillator();
      const envelope = this.ctx.createGain();
      const time = start + index * 0.09;
      osc.type = "sine";
      osc.frequency.value = frequency;
      envelope.gain.setValueAtTime(0, time);
      envelope.gain.linearRampToValueAtTime(0.08, time + 0.015);
      envelope.gain.exponentialRampToValueAtTime(0.001, time + 0.28);
      osc.connect(envelope).connect(this.gain);
      osc.onended = () => {
        osc.disconnect();
        envelope.disconnect();
      };
      osc.start(time);
      osc.stop(time + 0.3);
    }
  }

  setManualLatency(value: number): void {
    if (!Number.isFinite(value)) return;
    this.manualLatencyMs = Math.round(Math.min(500, Math.max(-500, value)));
    writeLocal("manualLatencyMs", String(this.manualLatencyMs));
    this.changed();
  }

  // --- clips ----------------------------------------------------------------------------

  /** Download what the view offers (never N+1 during our own playback) and late-start. */
  syncWithView(view: AnyView): void {
    if (!this.active) return;
    this.lastView = view;
    const keep = new Set([view.audio.current?.asset_id, view.audio.next?.asset_id]);
    for (const [id, request] of this.requests) {
      if (!keep.has(id)) {
        request.abort();
        this.requests.delete(id);
        this.loading.delete(id);
      }
    }
    if (!this.unlocked) return;
    if (view.paused && !view.paused.resume_at && this.scheduledPlayId) {
      this.stop(this.scheduledPlayId, view.paused.paused_at);
    }
    if (!view.play && !view.paused && this.playing) {
      this.stopSource();
      this.playing = false;
      this.setState("IDLE", null);
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
    const context = this.ctx;
    const controller = new AbortController();
    this.requests.set(assetId, controller);
    const current = () =>
      this.active &&
      this.ctx === context &&
      !controller.signal.aborted &&
      this.requests.get(assetId) === controller;
    const foreground = () => this.lastView?.audio.current?.asset_id === assetId;
    this.loading.add(assetId);
    if (!this.playing && foreground()) {
      this.setState("LOADING", assetId);
    }
    let lastError: AudioErrorCode = "FETCH_FAILED";
    for (let attempt = 0; attempt <= RETRIES_MS.length; attempt += 1) {
      try {
        const response = await fetch(url, {
          credentials: "same-origin",
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error("fetch");
        }
        const data = await response.arrayBuffer();
        lastError = "DECODE_FAILED";
        if (!current()) return;
        const buffer = await context.decodeAudioData(data);
        if (!current()) return;
        this.buffers.set(assetId, buffer);
        this.loading.delete(assetId);
        this.requests.delete(assetId);
        if (!this.unlocked) return;
        if (!this.playing && foreground()) {
          this.setState("READY", assetId);
        } else {
          this.send(buildAudioStatus("READY", assetId, null, this.clock.estimate()));
        }
        if (this.lastView) {
          this.syncWithView(this.lastView);
        }
        return;
      } catch {
        if (!current()) return;
        const wait = RETRIES_MS[attempt];
        if (wait === undefined) {
          break;
        }
        await new Promise<void>((resolve) => {
          const done = () => {
            clearTimeout(timer);
            controller.signal.removeEventListener("abort", done);
            resolve();
          };
          const timer = setTimeout(done, wait);
          controller.signal.addEventListener("abort", done, { once: true });
        });
        if (!current()) return;
      }
    }
    if (!current()) return;
    this.loading.delete(assetId);
    this.requests.delete(assetId);
    if (this.unlocked && !this.playing && foreground()) this.setState("ERROR", assetId, lastError);
  }

  // --- playback ---------------------------------------------------------------------------

  play(msg: PlayMsg | PlayInfo): StartPlan | null {
    if (!this.active || !this.unlocked) return null;
    const ctx = this.ctx;
    const buffer = this.buffers.get(msg.asset_id);
    if (!ctx || !this.gain || !buffer || msg.play_id === this.scheduledPlayId) {
      return null;
    }
    this.stopSource();
    const estimate = this.clock.estimate();
    this.appliedLatencyMs = this.manualLatencyMs;
    const tLocal = serverToLocal(msg.start_at, estimate?.offset ?? 0, this.appliedLatencyMs);
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
        const local = serverToLocal(at, this.clock.estimate()?.offset ?? 0, this.appliedLatencyMs);
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
      source.onended = null;
      try {
        source.stop();
      } catch {
        // already stopped
      }
      source.disconnect?.();
    }
  }

  activate(): void {
    this.active = true;
  }

  dispose(): void {
    this.active = false;
    this.lastView = null;
    for (const request of this.requests.values()) request.abort();
    this.requests.clear();
    this.loading.clear();
    this.buffers.clear();
    this.stopSource();
    this.playing = false;
    this.scheduledPlayId = null;
    this.finaleCues.clear();
    const context = this.ctx;
    this.ctx = null;
    this.gain = null;
    if (context) {
      context.onstatechange = null;
      if (context.state !== "closed") void context.close().catch(() => undefined);
    }
    releasePlaybackSession();
    this.setState("LOCKED", null);
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
      manualLatencyMs: this.manualLatencyMs,
    };
  }
}
