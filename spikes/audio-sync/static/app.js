// Spike S0 player page: unlock recipes (spec 9.7), format matrix, clock sync (9.2),
// scheduling (9.5). Throwaway code, vanilla JS, no build step.
import {
  BURST_COUNT,
  BURST_SPACING_MS,
  ClockSync,
  KEEPALIVE_MS,
  computeStartTime,
  effectiveOutputLatency,
  isValidOutputTimestamp,
  planStart,
} from "./clock.js";
import { burstCentroid } from "./measure.js";

const $ = (id) => document.getElementById(id);
const TAB_ID = Math.random().toString(36).slice(2, 12);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function storageGet(key, fallback) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}
function storageSet(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode: ignore */
  }
}

const S = {
  ws: null,
  wsOpenedOnce: false,
  reconnectDelay: 500,
  clientId: storageGet("s0.cid", ""),
  voice: null,
  freq: null,
  calibClip: null,
  manifest: null,
  clock: new ClockSync(),
  burstPromise: null,
  ctx: null,
  gain: null,
  buffers: new Map(), // clip name -> Promise<AudioBuffer>
  sources: new Set(),
  unlockedOnce: false,
  recipe: storageGet("s0.recipe", "auto"),
  recipeResult: {},
  silentAudio: null,
  manualLatencyMs: Number(storageGet("s0.manualLatency", "0")) || 0,
  currentPlay: null, // { play_id, startLocal, endLocal, clip, msg }
  playGen: 0, // bumped by stopAll(): an onPlay() that awaited across a newer PLAY/STOP gives up
  pendingPlay: null, // PLAY received before the first unlock (no AudioContext yet)
  prevCtxState: null,
  lastPlayback: null,
};

// ------------------------------------------------------------------------------------------
// Log and small UI helpers
// ------------------------------------------------------------------------------------------

function log(...parts) {
  const line = `${new Date().toISOString().slice(11, 23)} ${parts.join(" ")}`;
  const el = $("log");
  el.textContent = `${line}\n${el.textContent}`.split("\n").slice(0, 80).join("\n");
  console.log(line);
}

function kv(container, rows) {
  container.replaceChildren(
    ...rows.map(([k, v, cls]) => {
      const d = document.createElement("div");
      d.className = "kv";
      const a = document.createElement("span");
      a.textContent = k;
      const b = document.createElement("span");
      b.textContent = v;
      if (cls) b.className = cls;
      d.append(a, b);
      return d;
    }),
  );
}

const fmt = (v, digits = 1, unit = "") =>
  v == null || Number.isNaN(v) ? "—" : `${Number(v).toFixed(digits)}${unit}`;

function isIOS() {
  return (
    /iPhone|iPad|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

function envInfo() {
  const ctx = S.ctx;
  return {
    user_agent: navigator.userAgent,
    platform: navigator.userAgentData?.platform ?? navigator.platform,
    ua_mobile: navigator.userAgentData?.mobile ?? null,
    max_touch_points: navigator.maxTouchPoints,
    is_ios: isIOS(),
    secure_context: window.isSecureContext,
    has_audio_context: "AudioContext" in window,
    has_webkit_audio_context: "webkitAudioContext" in window,
    has_audio_session: "audioSession" in navigator,
    audio_session_type: navigator.audioSession?.type ?? null,
    audio_session_state: navigator.audioSession?.state ?? null,
    has_get_output_timestamp: !!ctx && typeof ctx.getOutputTimestamp === "function",
    ctx_state: ctx?.state ?? null,
    sample_rate: ctx?.sampleRate ?? null,
    base_latency: ctx?.baseLatency ?? null,
    output_latency: ctx?.outputLatency ?? null,
    recipe: S.recipe,
    recipe_result: S.recipeResult,
    manual_latency_ms: S.manualLatencyMs,
    visibility: document.visibilityState,
  };
}

async function postReport(kind, payload) {
  if (!S.clientId) return;
  try {
    const res = await fetch("/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: S.clientId, kind, env: envInfo(), ...payload }),
    });
    log(`report ${kind}: HTTP ${res.status}`);
  } catch (e) {
    log(`report ${kind} failed: ${e}`);
  }
}

// ------------------------------------------------------------------------------------------
// WebSocket and clock sync (spec 9.2)
// ------------------------------------------------------------------------------------------

function connect() {
  if (S.ws && S.ws.readyState <= WebSocket.OPEN) return; // already connecting or open
  const proto = location.protocol === "https:" ? "wss" : "ws";
  // tab: one random id per page load, so the server can tell this page reconnecting (take
  // over the old socket, keep the voice) from a duplicated tab (new identity).
  const url = `${proto}://${location.host}/ws?cid=${encodeURIComponent(S.clientId)}&tab=${TAB_ID}`;
  const ws = new WebSocket(url);
  S.ws = ws;
  updateBadges();
  ws.onopen = () => {
    const reason = S.wsOpenedOnce ? "reconnect" : "connect";
    S.wsOpenedOnce = true;
    S.reconnectDelay = 500;
    send({ t: "HELLO", ua: navigator.userAgent, env: envInfo() });
    log(`ws open (${reason})`);
    updateBadges();
  };
  ws.onmessage = (ev) => {
    const t1 = performance.now(); // read first: it is the PONG reception time
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    onMessage(msg, t1);
  };
  ws.onclose = () => {
    log(`ws closed, retry in ${S.reconnectDelay} ms`);
    if (S.ws === ws) S.ws = null;
    updateBadges();
    setTimeout(connect, S.reconnectDelay);
    S.reconnectDelay = Math.min(5000, S.reconnectDelay * 2);
  };
}

function send(msg) {
  if (S.ws?.readyState === WebSocket.OPEN) S.ws.send(JSON.stringify(msg));
}

function ping() {
  send({ t: "PING", c: performance.now() });
}

/** Burst of 8 pings 50 ms apart (connect, reconnect, visibilitychange, before play). */
function syncBurst(reason) {
  if (S.burstPromise) return S.burstPromise;
  S.burstPromise = (async () => {
    for (let i = 0; i < BURST_COUNT; i++) {
      ping();
      await sleep(BURST_SPACING_MS);
    }
    await sleep(150); // let the last PONGs arrive
    const e = S.clock.estimate();
    log(`burst (${reason}): theta=${fmt(e?.theta, 1)} rtt_min=${fmt(e?.rttMin, 1)} n=${e?.count ?? 0}`);
    sendStatus();
  })().finally(() => {
    S.burstPromise = null;
  });
  return S.burstPromise;
}

function onMessage(msg, t1) {
  switch (msg.t) {
    case "PONG":
      if (typeof msg.c === "number" && typeof msg.s === "number") S.clock.add(msg.c, t1, msg.s);
      break;
    case "WELCOME":
      S.clientId = msg.client_id;
      storageSet("s0.cid", msg.client_id);
      S.voice = msg.voice;
      S.freq = msg.freq_hz;
      S.calibClip = msg.calib_clip;
      // a new connection may face a restarted server (other clock origin): start afresh
      S.clock.reset();
      log(`welcome: client ${msg.client_id}, voice ${msg.voice} (${msg.freq_hz} Hz), clock ${msg.server_clock}`);
      updateBadges();
      syncBurst(S.unlockedOnce ? "reconnect" : "connect");
      // Decoding needs the AudioContext, and the context must be created inside the unlock
      // gesture, after the recipe (spec 9.7): before the first unlock, unlock() preloads.
      if (S.unlockedOnce) preload();
      break;
    case "PLAY":
      onPlay(msg, msg.rejoin ? "rejoin" : "play").catch((e) => log(`play error: ${e}`));
      break;
    case "STOP":
      S.pendingPlay = null;
      stopAll();
      log("STOP");
      break;
    case "SYNC":
      syncBurst("admin");
      break;
    default:
      break;
  }
}

function audioState() {
  if (!S.ctx || S.ctx.state !== "running") return "LOCKED";
  return S.calibReady ? "READY" : "UNLOCKED";
}

function sendStatus() {
  const e = S.clock.estimate();
  const ctx = S.ctx;
  let effLatency = null;
  if (ctx?.getOutputTimestamp) {
    effLatency = effectiveOutputLatency({
      outputTimestamp: ctx.getOutputTimestamp(),
      currentTime: ctx.currentTime,
      perfNow: performance.now(),
    });
  }
  send({
    t: "AUDIO_STATUS",
    state: audioState(),
    ctx_state: ctx?.state ?? "none",
    clock: e ? { offset: e.theta, rtt_min: e.rttMin, epsilon: e.epsilon, samples: e.count } : null,
    recipe: S.recipe,
    recipe_result: S.recipeResult,
    audio_session_type: navigator.audioSession?.type ?? null,
    sample_rate: ctx?.sampleRate ?? null,
    base_latency: ctx?.baseLatency ?? null,
    output_latency: ctx?.outputLatency ?? null,
    effective_latency_ms: effLatency == null ? null : effLatency * 1000,
    manual_latency_ms: S.manualLatencyMs,
    last_playback: S.lastPlayback,
    visibility: document.visibilityState,
  });
}

// ------------------------------------------------------------------------------------------
// AudioContext and unlock recipes (spec 9.7)
// ------------------------------------------------------------------------------------------

function ensureContext() {
  if (S.ctx) return S.ctx; // one AudioContext per page, never recreated
  const Ctor = window.AudioContext || window.webkitAudioContext;
  if (!Ctor) throw new Error("Web Audio API indisponible");
  const ctx = new Ctor();
  S.ctx = ctx;
  S.gain = ctx.createGain();
  S.gain.gain.value = Number($("volume").value);
  S.gain.connect(ctx.destination);
  ctx.onstatechange = onContextState;
  log(`AudioContext created: state=${ctx.state} sampleRate=${ctx.sampleRate}`);
  return ctx;
}

function onContextState() {
  const st = S.ctx.state;
  const prev = S.prevCtxState;
  S.prevCtxState = st;
  log(`ctx state -> ${st}`);
  if (st === "running") {
    $("overlay").classList.remove("show");
    // The context clock stood still while suspended/interrupted: the scheduled source is now
    // late. Same path as a reconnection (spec 9.6): reschedule with the "T past" rule.
    const p = S.currentPlay;
    if (prev && prev !== "running" && p && performance.now() < p.endLocal) {
      log("context resumed during playback: rescheduling");
      onPlay(p.msg, "resume").catch((e) => log(`resume play error: ${e}`));
    }
  } else if (S.unlockedOnce) {
    $("overlay-state").textContent = `AudioContext : ${st}`;
    $("overlay").classList.add("show");
  }
  updateBadges();
  sendStatus(); // reports LOCKED as soon as the context is no longer running
}

function silentWavUrl() {
  // 1 s of 8 kHz 16-bit mono silence, built in memory (no file to ship)
  const rate = 8000;
  const n = rate;
  const buf = new ArrayBuffer(44 + n * 2);
  const v = new DataView(buf);
  const str = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF");
  v.setUint32(4, 36 + n * 2, true);
  str(8, "WAVEfmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  str(36, "data");
  v.setUint32(40, n * 2, true);
  return URL.createObjectURL(new Blob([buf], { type: "audio/wav" }));
}

/** Must run synchronously inside the user gesture. */
function applyRecipe() {
  const recipe = S.recipe;
  const hasSession = "audioSession" in navigator;
  const useSession =
    recipe === "audioSession" || recipe === "both" || (recipe === "auto" && hasSession);
  const useSilent =
    recipe === "silent-audio" || recipe === "both" || (recipe === "auto" && !hasSession && isIOS());
  const result = { recipe, audio_session: null, silent_audio: null };
  if (useSession) {
    try {
      if (!hasSession) throw new Error("navigator.audioSession absent");
      navigator.audioSession.type = "playback";
      result.audio_session = `ok (type=${navigator.audioSession.type})`;
    } catch (e) {
      result.audio_session = `error: ${e.message ?? e}`;
    }
  }
  if (useSilent) {
    if (!S.silentAudio) {
      const a = document.createElement("audio");
      a.src = silentWavUrl();
      a.loop = true;
      a.preload = "auto";
      a.playsInline = true;
      a.setAttribute("playsinline", "");
      a.setAttribute("x-webkit-airplay", "deny");
      S.silentAudio = a;
    }
    result.silent_audio = "play() called";
    S.silentAudio
      .play()
      .then(() => {
        S.recipeResult.silent_audio = "playing";
        log("silent <audio> playing");
      })
      .catch((e) => {
        S.recipeResult.silent_audio = `error: ${e.name}: ${e.message}`;
        log(`silent <audio> failed: ${e.name}: ${e.message}`);
      });
  }
  S.recipeResult = result;
  log(`recipe ${recipe}: session=${result.audio_session} silent=${result.silent_audio}`);
}

function beep(ctx) {
  const osc = ctx.createOscillator();
  const g = ctx.createGain();
  osc.frequency.value = 880;
  const t = ctx.currentTime + 0.05;
  g.gain.setValueAtTime(0, t);
  g.gain.linearRampToValueAtTime(0.4, t + 0.01);
  g.gain.setValueAtTime(0.4, t + 0.14);
  g.gain.linearRampToValueAtTime(0, t + 0.15);
  osc.connect(g).connect(S.gain);
  osc.start(t);
  osc.stop(t + 0.16);
}

/** Unlock button / overlay tap: recipe, resume() and a beep, all inside the gesture. */
function unlock() {
  applyRecipe();
  let ctx;
  try {
    ctx = ensureContext();
  } catch (e) {
    log(String(e));
    return;
  }
  const p = ctx.resume(); // called synchronously in the gesture
  beep(ctx);
  S.unlockedOnce = true;
  Promise.resolve(p)
    .then(() => {
      log(`resume() resolved, state=${ctx.state}`);
      if (ctx.state === "running") $("overlay").classList.remove("show");
      updateBadges();
      sendStatus();
      preload();
      const pending = S.pendingPlay;
      S.pendingPlay = null;
      if (pending) onPlay(pending, "unlock-rejoin").catch((e) => log(`play error: ${e}`));
    })
    .catch((e) => log(`resume() failed: ${e}`));
}

// ------------------------------------------------------------------------------------------
// Clips: fetch + decodeAudioData (spec 9.3)
// ------------------------------------------------------------------------------------------

function decode(ctx, data) {
  // promise form, with the callback form for old Safari versions
  return new Promise((resolve, reject) => {
    const p = ctx.decodeAudioData(data, resolve, (e) =>
      reject(e ?? new Error("decodeAudioData error (null)")),
    );
    if (p && typeof p.then === "function") p.then(resolve, reject);
  });
}

async function fetchAndDecode(name) {
  const ctx = ensureContext();
  const t0 = performance.now();
  const res = await fetch(`/clips/${encodeURIComponent(name)}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.arrayBuffer();
  const t1 = performance.now();
  const buffer = await decode(ctx, data);
  const t2 = performance.now();
  return { buffer, bytes: data.byteLength, fetchMs: t1 - t0, decodeMs: t2 - t1 };
}

function loadClip(name) {
  if (!S.buffers.has(name)) {
    const p = fetchAndDecode(name).then((r) => r.buffer);
    p.catch(() => S.buffers.delete(name));
    S.buffers.set(name, p);
  }
  return S.buffers.get(name);
}

async function loadManifest() {
  if (!S.manifest) S.manifest = await (await fetch("/api/manifest")).json();
  return S.manifest;
}

async function preload() {
  if (!S.calibClip) return;
  try {
    await loadClip(S.calibClip);
    S.calibReady = true;
    log(`preloaded ${S.calibClip}`);
    updateBadges();
    sendStatus();
  } catch (e) {
    log(`preload ${S.calibClip} failed: ${e}`);
  }
}

async function testFormats() {
  // Still inside the click: unlock first, so the recipe runs before the context exists.
  if (!S.unlockedOnce) unlock();
  const ctx = ensureContext();
  const manifest = await loadManifest();
  const tbody = $("formats").querySelector("tbody");
  tbody.replaceChildren();
  const results = [];
  const probe = document.createElement("audio");
  for (const clip of manifest.clips.filter((c) => c.kind === "test")) {
    const r = {
      name: clip.name,
      label: clip.label,
      mime: clip.mime,
      can_play_type: probe.canPlayType(clip.mime),
      media_source: window.MediaSource?.isTypeSupported?.(clip.mime) ?? null,
    };
    try {
      const { buffer, bytes, fetchMs, decodeMs } = await fetchAndDecode(clip.name);
      const center = burstCentroid(
        buffer.getChannelData(0),
        buffer.sampleRate,
        clip.marker_center_s - 0.2,
        clip.marker_center_s + 0.2,
      );
      Object.assign(r, {
        ok: true,
        bytes,
        fetch_ms: fetchMs,
        decode_ms: decodeMs,
        duration_s: buffer.duration,
        duration_error_ms: (buffer.duration - clip.expected_duration_s) * 1000,
        channels: buffer.numberOfChannels,
        sample_rate: buffer.sampleRate,
        marker_offset_ms: center == null ? null : (center - clip.marker_center_s) * 1000,
        ffmpeg_marker_offset_ms: clip.ffmpeg_marker_offset_ms,
      });
      S.buffers.set(clip.name, Promise.resolve(buffer));
    } catch (e) {
      Object.assign(r, { ok: false, error: `${e?.name ?? "Error"}: ${e?.message ?? e}` });
    }
    results.push(r);
    const tr = document.createElement("tr");
    const cells = [
      r.label,
      r.ok ? "✓ décodé" : `✗ ${r.error}`,
      r.ok ? fmt(r.duration_s, 3) : "—",
      r.ok ? fmt(r.decode_ms, 0) : "—",
      r.ok ? fmt(r.marker_offset_ms, 2) : "—",
      r.can_play_type || "(vide)",
    ];
    for (const [i, text] of cells.entries()) {
      const td = document.createElement("td");
      td.textContent = text;
      if (i === 1) td.className = r.ok ? "ok" : "bad";
      tr.append(td);
    }
    const td = document.createElement("td");
    if (r.ok) {
      const b = document.createElement("button");
      b.textContent = "▶";
      b.onclick = () => playLocal(clip.name);
      td.append(b);
    }
    tr.append(td);
    tbody.append(tr);
    log(`format ${clip.name}: ${r.ok ? "ok" : r.error}`);
  }
  await postReport("formats", { results, ctx_state: ctx.state });
}

async function playLocal(name) {
  const ctx = ensureContext();
  stopAll();
  const gen = S.playGen;
  const buffer = await loadClip(name);
  if (gen !== S.playGen) return; // stopped or replaced while decoding
  const src = ctx.createBufferSource();
  src.buffer = buffer;
  src.connect(S.gain);
  src.start();
  S.sources.add(src);
  src.onended = () => S.sources.delete(src);
}

function stopAll() {
  for (const s of S.sources) {
    try {
      s.stop();
    } catch {
      /* already stopped */
    }
  }
  S.sources.clear();
  S.currentPlay = null;
  S.playGen++; // invalidates any onPlay()/playLocal() still awaiting
}

// ------------------------------------------------------------------------------------------
// PLAY (spec 9.5)
// ------------------------------------------------------------------------------------------

async function onPlay(msg, reason = "play") {
  if (!S.unlockedOnce) {
    // No user gesture yet: creating the context here would bypass the recipe (spec 9.7).
    // Keep the PLAY; unlock() schedules it with the "T past" rule.
    S.pendingPlay = msg;
    log(`PLAY (${reason}) ${msg.play_id} kept until unlock: audio LOCKED`);
    return;
  }
  const ctx = ensureContext();
  stopAll();
  const gen = S.playGen; // any later stopAll() (STOP, newer PLAY, resume) supersedes this one
  const received = performance.now();
  let e = S.clock.estimate();
  const leadMs = e ? msg.start_at - e.theta - received : Number.POSITIVE_INFINITY;
  log(`PLAY (${reason}) ${msg.play_id} ${msg.clip} in ${fmt(leadMs, 0)} ms`);
  if (leadMs > 900) await syncBurst("before-play"); // fresh estimate (spec: burst at LOADING)
  const buffer = await loadClip(msg.clip);
  if (gen !== S.playGen) {
    log(`PLAY (${reason}) ${msg.play_id} superseded by STOP or a newer PLAY while waiting`);
    return;
  }
  e = S.clock.estimate();
  if (!e) {
    log("no clock estimate, cannot schedule");
    return;
  }
  const ts = typeof ctx.getOutputTimestamp === "function" ? ctx.getOutputTimestamp() : null;
  const perfNow = performance.now();
  const now = ctx.currentTime;
  const st = computeStartTime({
    startAt: msg.start_at,
    theta: e.theta,
    manualLatencyMs: S.manualLatencyMs,
    outputTimestamp: ts,
    currentTime: now,
    perfNow,
    outputLatency: ctx.outputLatency,
    baseLatency: ctx.baseLatency,
  });
  const clipOffset = Number(msg.clip_offset) || 0;
  const plan = planStart({ T: st.T, now, clipOffset, duration: buffer.duration });
  if (!plan.skipped) {
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(S.gain);
    src.start(plan.when, plan.offset);
    S.sources.add(src);
    src.onended = () => S.sources.delete(src);
  }
  S.currentPlay = {
    play_id: msg.play_id,
    startLocal: st.tLocal,
    endLocal: st.tLocal + (buffer.duration - clipOffset) * 1000,
    clip: msg.clip,
    msg,
  };
  const report = {
    reason,
    play_id: msg.play_id,
    clip: msg.clip,
    start_at: msg.start_at,
    late_ms: plan.lateMs,
    offset: e.theta,
    rtt_min: e.rttMin,
    out_latency: st.latencyS == null ? null : st.latencyS * 1000, // ms
    est_error_ms: e.epsilon,
    api_used: st.apiUsed,
    skipped: plan.skipped,
    clip_offset: clipOffset,
    start_offset_s: plan.offset,
    when_s: plan.when,
    T_s: st.T,
    ctx_current_time_s: now,
    perf_now_ms: perfNow,
    t_local_ms: st.tLocal,
    ms_until_start: st.tLocal - perfNow,
    output_timestamp: ts ? { contextTime: ts.contextTime, performanceTime: ts.performanceTime } : null,
    output_timestamp_valid: isValidOutputTimestamp(ts),
    base_latency: ctx.baseLatency ?? null,
    output_latency: ctx.outputLatency ?? null,
    manual_latency_ms: S.manualLatencyMs,
    ctx_state: ctx.state,
    samples: e.count,
  };
  S.lastPlayback = {
    reason,
    play_id: msg.play_id,
    late_ms: report.late_ms,
    api_used: report.api_used,
    out_latency: report.out_latency,
    est_error_ms: report.est_error_ms,
    skipped: report.skipped,
    ctx_state: report.ctx_state,
  };
  log(
    `scheduled ${msg.clip}: api=${st.apiUsed} late=${fmt(plan.lateMs, 1)} ms ` +
      `latency=${fmt(report.out_latency, 1)} ms ctx=${ctx.state}${plan.skipped ? " SKIPPED" : ""}`,
  );
  kv($("play-info"), [
    ["play_id", msg.play_id],
    ["clip", msg.clip],
    ["API", st.apiUsed],
    ["retard (late_ms)", fmt(plan.lateMs, 1)],
    ["latence sortie (ms)", fmt(report.out_latency, 1)],
    ["incertitude ε (ms)", fmt(e.epsilon, 1)],
    ["état ctx", ctx.state, ctx.state === "running" ? "ok" : "bad"],
  ]);
  sendStatus();
  await postReport("playback", report);
}

function drawCountdown() {
  const p = S.currentPlay;
  const el = $("countdown");
  if (!p) {
    el.textContent = "—";
  } else {
    const ms = p.startLocal - performance.now(); // visual only, the sound is on the audio thread
    el.textContent = ms > 0 ? `Lecture dans ${(ms / 1000).toFixed(1)} s` : `En lecture (${p.clip})`;
  }
  requestAnimationFrame(drawCountdown);
}

// ------------------------------------------------------------------------------------------
// Live panels
// ------------------------------------------------------------------------------------------

function updateBadges() {
  $("voice").textContent = S.voice ?? "?";
  $("voice-freq").textContent = S.freq ? `${S.freq} Hz` : "?";
  const ws = S.ws?.readyState === WebSocket.OPEN ? "connecté" : "déconnecté";
  $("ws-state").textContent = ws;
  $("ws-state").className = `badge ${ws === "connecté" ? "ok" : "bad"}`;
  const st = audioState();
  $("audio-state").textContent = `${st} (${S.ctx?.state ?? "pas de contexte"})`;
  $("audio-state").className = `badge ${st === "LOCKED" ? "bad" : "ok"}`;
}

function refreshPanels() {
  const e = S.clock.estimate();
  kv($("clock-info"), [
    ["θ (ms)", fmt(e?.theta, 1)],
    ["rtt_min (ms)", fmt(e?.rttMin, 1)],
    ["ε = rtt_min/2 (ms)", fmt(e?.epsilon, 1)],
    ["dernier RTT (ms)", fmt(e?.lastRtt, 1)],
    ["échantillons", String(e?.count ?? 0)],
    ["heure serveur estimée", e ? fmt(performance.now() + e.theta, 0) : "—"],
  ]);
  const ctx = S.ctx;
  let ts = null;
  let eff = null;
  if (ctx?.getOutputTimestamp) {
    ts = ctx.getOutputTimestamp();
    eff = effectiveOutputLatency({
      outputTimestamp: ts,
      currentTime: ctx.currentTime,
      perfNow: performance.now(),
    });
  }
  kv($("ctx-info"), [
    ["state", ctx?.state ?? "pas encore créé", ctx?.state === "running" ? "ok" : "bad"],
    ["sampleRate", ctx ? String(ctx.sampleRate) : "—"],
    ["baseLatency (ms)", ctx?.baseLatency == null ? "absent" : fmt(ctx.baseLatency * 1000, 1)],
    ["outputLatency (ms)", ctx?.outputLatency == null ? "absent" : fmt(ctx.outputLatency * 1000, 1)],
    ["getOutputTimestamp", ctx ? (ctx.getOutputTimestamp ? "présent" : "absent") : "—"],
    ["ts.contextTime (s)", ts ? fmt(ts.contextTime, 3) : "—"],
    ["ts.performanceTime (ms)", ts ? fmt(ts.performanceTime, 1) : "—"],
    ["latence effective (ms)", eff == null ? "—" : fmt(eff * 1000, 1)],
    ["currentTime (s)", ctx ? fmt(ctx.currentTime, 3) : "—"],
  ]);
  const env = envInfo();
  kv($("env-info"), [
    ["navigateur", navigator.userAgent],
    ["plateforme", String(env.platform)],
    ["iOS détecté", String(env.is_ios)],
    ["contexte sécurisé", String(env.secure_context)],
    ["navigator.audioSession", env.has_audio_session ? `présent (type=${env.audio_session_type}, state=${env.audio_session_state})` : "absent"],
    ["recette appliquée", JSON.stringify(S.recipeResult)],
    ["visibilité", env.visibility],
  ]);
  updateBadges();
}

// ------------------------------------------------------------------------------------------
// Wiring
// ------------------------------------------------------------------------------------------

$("unlock").addEventListener("click", unlock);
$("overlay").addEventListener("click", unlock);
$("test-formats").addEventListener("click", () => testFormats().catch((e) => log(`formats: ${e}`)));
$("stop").addEventListener("click", stopAll);
$("sync").addEventListener("click", () => syncBurst("manual"));
$("recipe").value = S.recipe;
$("recipe").addEventListener("change", (ev) => {
  S.recipe = ev.target.value;
  storageSet("s0.recipe", S.recipe);
  // A recipe cannot be undone (audioSession.type, the looping silent <audio>, the context
  // already unlocked): comparing recipes on the same page would be contaminated. Reload.
  if (S.unlockedOnce || S.ctx) {
    log(`recipe -> ${S.recipe}: reloading the page for a clean test`);
    location.reload();
  }
});
$("volume").addEventListener("input", (ev) => {
  if (S.gain) S.gain.gain.value = Number(ev.target.value);
});
$("manual-latency").value = String(S.manualLatencyMs);
$("manual-latency").addEventListener("change", (ev) => {
  S.manualLatencyMs = Number(ev.target.value) || 0;
  storageSet("s0.manualLatency", String(S.manualLatencyMs));
  sendStatus();
});
document.addEventListener("visibilitychange", () => {
  log(`visibility -> ${document.visibilityState}`);
  if (document.visibilityState !== "visible") return;
  if (!S.ws) connect();
  syncBurst("visibilitychange");
  if (S.ctx && S.ctx.state !== "running" && S.unlockedOnce) {
    $("overlay-state").textContent = `AudioContext : ${S.ctx.state}`;
    $("overlay").classList.add("show");
  }
});

setInterval(() => {
  ping(); // keepalive and heartbeat
  sendStatus();
}, KEEPALIVE_MS);
setInterval(refreshPanels, 250);
requestAnimationFrame(drawCountdown);
loadManifest().catch((e) => log(`manifest: ${e}`));
connect();
refreshPanels();
