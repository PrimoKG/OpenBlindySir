// Spike S0 admin page: polls /api/admin/state, sends PLAY / STOP / SYNC through the server.
const $ = (id) => document.getElementById(id);
const token = new URLSearchParams(location.search).get("token");
const withToken = (path) => (token ? `${path}?token=${encodeURIComponent(token)}` : path);
const fmt = (v, d = 1) => (v == null || Number.isNaN(v) ? "—" : Number(v).toFixed(d));
let clipsLoaded = false;

$("results").href = withToken("/results.json");

async function api(path, body) {
  const res = await fetch(withToken(path), {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}

function cell(tr, text, cls) {
  const td = document.createElement("td");
  td.textContent = text;
  if (cls) td.className = cls;
  tr.append(td);
}

function formatsSummary(report) {
  if (!report?.results) return "—";
  return report.results
    .map((r) => {
      const short = r.name.replace("test_", "").replace(/\.\w+$/, "") + (r.name.endsWith(".ogg") ? "/ogg" : r.name.endsWith(".webm") ? "/webm" : "");
      return r.ok ? `${short} ✓ (${fmt(r.marker_offset_ms, 1)} ms)` : `${short} ✗`;
    })
    .join("  ");
}

function render(state) {
  if (!clipsLoaded) {
    const sel = $("clip");
    for (const c of state.clips.filter((x) => x.kind === "test")) {
      const o = document.createElement("option");
      o.value = c.name;
      o.textContent = c.label;
      sel.append(o);
    }
    clipsLoaded = true;
  }
  const tbody = $("clients");
  tbody.replaceChildren();
  const clients = [...state.clients].sort((a, b) => Number(b.connected) - Number(a.connected) || a.voice - b.voice);
  for (const c of clients) {
    const tr = document.createElement("tr");
    const st = c.status ?? {};
    const clock = st.clock ?? {};
    const pb = c.last_reports?.playback;
    cell(tr, c.id);
    cell(tr, `${c.voice} (${c.freq_hz} Hz)`);
    cell(tr, c.ua_family);
    cell(tr, c.connected ? "connecté" : "parti", c.connected ? "ok" : "bad");
    cell(tr, `${st.state ?? "?"} / ${st.ctx_state ?? "?"}`, st.state === "LOCKED" ? "bad" : "ok");
    cell(tr, st.recipe ? `${st.recipe}${st.audio_session_type ? ` (${st.audio_session_type})` : ""}` : "—");
    cell(tr, fmt(clock.offset, 1));
    cell(tr, fmt(clock.rtt_min, 1));
    cell(tr, fmt(clock.epsilon, 1));
    cell(tr, fmt(st.effective_latency_ms, 1));
    cell(
      tr,
      pb
        ? `${pb.play_id} ${pb.api_used} late=${fmt(pb.late_ms, 1)} lat=${fmt(pb.out_latency, 1)} ±${fmt(pb.est_error_ms, 1)}${pb.skipped ? " SKIP" : ""} ctx=${pb.ctx_state}`
        : "—",
    );
    cell(tr, formatsSummary(c.last_reports?.formats));
    tbody.append(tr);
  }
  const plays = $("plays");
  plays.replaceChildren();
  for (const p of [...state.plays].reverse()) {
    const tr = document.createElement("tr");
    cell(tr, p.play_id);
    cell(tr, p.kind === "calibration" ? "calibration" : p.targets[0]?.clip ?? p.kind);
    cell(tr, p.issued_at);
    cell(tr, fmt(p.lead_ms, 0));
    cell(tr, p.targets.map((t) => `${t.client}:v${t.voice}`).join(" "));
    plays.append(tr);
  }
}

async function poll() {
  try {
    render(await api("/api/admin/state"));
  } catch (e) {
    $("msg").textContent = String(e);
  }
  setTimeout(poll, 1000);
}

async function action(path, body) {
  try {
    const r = await api(path, body);
    $("msg").textContent = `${path}: ${JSON.stringify(r).slice(0, 200)}`;
  } catch (e) {
    $("msg").textContent = String(e);
  }
}

const leadMs = () => Number($("lead").value) * 1000;
$("play-calib").onclick = () => action("/api/admin/play", { kind: "calibration", lead_ms: leadMs() });
$("play-clip").onclick = () =>
  action("/api/admin/play", {
    kind: "clip",
    clip: $("clip").value,
    lead_ms: leadMs(),
    clip_offset: Number($("clip-offset").value) || 0,
  });
$("stop").onclick = () => action("/api/admin/stop", {});
$("sync").onclick = () => action("/api/admin/sync", {});
poll();
