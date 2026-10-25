/* Balloon dashboard: SSE-fed live charts (uPlot), camera stream, markers, vertical profiles, replay of past sessions. */
(function () {
  "use strict";
  // Surface JS errors on the page itself (phones have no console).
  function showError(msg) {
    let box = document.getElementById("js-errors");
    if (!box) { box = document.createElement("pre"); box.id = "js-errors"; box.className = "js-errors"; document.body.prepend(box); }
    box.textContent += msg + "\n";
  }
  addEventListener("error", (e) => {
    // Safari masks exceptions it cannot attribute as "Script error." with no file/line; our own try/catch
    // blocks below print the real stack, so only show window errors that carry detail.
    if (!e.message || (/^Script error\.?$/.test(e.message) && !e.filename)) return;
    showError(e.message + " @ " + (e.filename || "").split("/").pop() + ":" + e.lineno + (e.error && e.error.stack ? "\n" + String(e.error.stack).split("\n").slice(0, 3).join("\n") : ""));
  });
  addEventListener("unhandledrejection", (e) => showError("promise: " + (e.reason && e.reason.stack || e.reason && e.reason.message || e.reason)));
  const _seen = {};
  function logOnce(where, e) {           // real stack traces for the phone, each place reported once
    if (_seen[where]) return; _seen[where] = true;
    showError(where + ": " + (e && e.stack ? String(e.stack).split("\n").slice(0, 4).join("\n") : e));
  }

  // ---------- chart definitions (one axis per chart; series colors fixed by slot) ----------
  const CHARTS = [
    { id: "altitude", title: "Altitude (relative)", unit: "m", series: [{ f: "altitude_m", label: "altitude" }], markers: true, dec: 1 },
    { id: "since", title: "Altitude since launch", unit: "m", series: [{ f: "alt_since_launch_m", label: "Δ since launch" }], dec: 1 },
    { id: "vspeed", title: "Vertical speed", unit: "m/s", series: [{ f: "vspeed_mps", label: "v" }], dec: 2 },
    { id: "det", title: "Detections in view (YOLO, all classes)", unit: "", series: [{ f: "det_total", label: "objects" }], dec: 0 },
    { id: "pressure", title: "Pressure", unit: "hPa", series: [{ f: "pressure_hpa", label: "pressure" }], dec: 2 },
    { id: "temp", title: "Temperature", unit: "°C", series: [{ f: "temp_c", label: "temp" }], dec: 2 },
    { id: "humidity", title: "Humidity", unit: "%", series: [{ f: "humidity_pct", label: "RH" }], dec: 1 },
    { id: "tilt", title: "Tilt", unit: "°", series: [{ f: "pitch_deg", label: "pitch" }, { f: "roll_deg", label: "roll" }, { f: "tilt_deg", label: "total" }], dec: 1 },
    { id: "accel", title: "Acceleration magnitude", unit: "g", series: [{ f: "accel_mag_g", label: "|a|" }], dec: 3 },
    { id: "gyro", title: "Rotation rate", unit: "°/s", series: [{ f: "gx_dps", label: "x" }, { f: "gy_dps", label: "y" }, { f: "gz_dps", label: "z" }], dec: 1 },
    { id: "light", title: "Light", unit: "%", series: [{ f: "light_pct", label: "light" }], dec: 1 },
    { id: "uv", title: "UV index", unit: "", series: [{ f: "uv_index", label: "UV" }], dec: 2 },
    { id: "aq", title: "Air quality (raw, lower is cleaner)", unit: "", series: [{ f: "aq_raw", label: "AQ" }], dec: 0 },
    { id: "eco2", title: "eCO₂", unit: "ppm", series: [{ f: "eco2_ppm", label: "eCO₂" }], dec: 0 },
    { id: "tvoc", title: "TVOC", unit: "ppb", series: [{ f: "tvoc_ppb", label: "TVOC" }], dec: 0 },
    { id: "rssi", title: "Wi-Fi signal", unit: "dBm", series: [{ f: "wifi_rssi_dbm", label: "RSSI" }], dec: 0 },
    { id: "cpu", title: "Pi CPU temperature", unit: "°C", series: [{ f: "cpu_temp_c", label: "cpu" }], dec: 1 },
  ];
  const TILES = [
    { f: "altitude_m", label: "Altitude (rel.)", unit: "m", dec: 1, hero: true },
    { f: "det_total", label: "Detections (YOLO)", unit: "", dec: 0, extra: "det_classes" },
    { f: "alt_since_launch_m", label: "Since launch", unit: "m", dec: 1 },
    { f: "elevation_msl_m", label: "Elevation (est.)", unit: "m MSL", dec: 0 },
    { f: "vspeed_mps", label: "Climb rate", unit: "m/s", dec: 2 },
    { f: "pressure_hpa", label: "Pressure", unit: "hPa", dec: 1 },
    { f: "temp_c", label: "Temp", unit: "°C", dec: 1 },
    { f: "tilt_deg", label: "Tilt", unit: "°", dec: 1 },
    { f: "light_pct", label: "Light", unit: "%", dec: 0 },
    { f: "uv_index", label: "UV index", unit: "", dec: 1 },
    { f: "aq_raw", label: "Air quality", unit: "", dec: 0, extra: "aq_level" },
    { f: "eco2_ppm", label: "eCO₂", unit: "ppm", dec: 0 },
    { f: "humidity_pct", label: "Humidity", unit: "%", dec: 0 },
  ];
  const PROFILES = [
    { f: "temp_c", title: "Temperature", unit: "°C", dec: 1 },
    { f: "aq_raw", title: "Air quality", unit: "", dec: 0 },
    { f: "light_pct", title: "Light", unit: "%", dec: 0 },
    { f: "uv_index", title: "UV index", unit: "", dec: 2 },
    { f: "humidity_pct", title: "Humidity", unit: "%", dec: 0 },
    { f: "eco2_ppm", title: "eCO₂", unit: "ppm", dec: 0 },
    { f: "tilt_deg", title: "Tilt (sway)", unit: "°", dec: 1 },
  ];
  const MAX_SECONDS = 1800;
  const params = new URLSearchParams(location.search);
  const REPLAY = params.get("replay");   // session name -> replay mode

  // ---------- state ----------
  const cols = {};        // field -> array (parallel to cols.t_unix)
  let n = 0;
  let windowSec = 300;
  const charts = {};      // id -> {u, def, el}
  let latest = {};
  let markers = [];
  let lastSampleAt = 0;
  let dirty = false;
  let detTiles = {};      // car/people counts posted by the ground station (kept apart from SSE samples)
  let status = {};
  let replay = null;      // {t0, t1, t, speed, playing, stills:[{t,file}]}

  const $ = (s) => document.querySelector(s);
  // ---------- units (metric by default; imperial converts at render time, data stays metric) ----------
  let imperial = false;
  try { imperial = localStorage.getItem("units") === "imperial"; } catch (e) { }
  const IMPERIAL = {   // field -> [factor, offset, unit, decimals]
    altitude_m: [3.28084, 0, "ft", 0], altitude_raw_m: [3.28084, 0, "ft", 0], alt_since_launch_m: [3.28084, 0, "ft", 0],
    elevation_msl_m: [3.28084, 0, "ft MSL", 0], vspeed_mps: [196.8504, 0, "ft/min", 0],
    temp_c: [1.8, 32, "°F", 1], cpu_temp_c: [1.8, 32, "°F", 0], pressure_hpa: [0.0295300, 0, "inHg", 2],
  };
  const conv = (f, v) => (imperial && IMPERIAL[f] && v != null) ? v * IMPERIAL[f][0] + IMPERIAL[f][1] : v;
  const unitOf = (f, u) => (imperial && IMPERIAL[f]) ? IMPERIAL[f][2] : u;
  const decOf = (f, d) => (imperial && IMPERIAL[f]) ? IMPERIAL[f][3] : d;
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const palette = () => [css("--s1"), css("--s2"), css("--s3")];
  const fmt = (v, dec) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : Number(v).toFixed(dec);
  const nowSec = () => replay ? replay.t : Date.now() / 1000;
  function upperBound(arr, x) { let lo = 0, hi = arr.length; while (lo < hi) { const mid = (lo + hi) >> 1; if (arr[mid] <= x) lo = mid + 1; else hi = mid; } return lo; }
  function endIndex() { const t = cols.t_unix || []; return replay ? upperBound(t, replay.t) : t.length; }

  // ---------- theme ----------
  function applyTheme(t) {
    if (t) document.documentElement.setAttribute("data-theme", t); else document.documentElement.removeAttribute("data-theme");
    try { if (t) localStorage.setItem("theme", t); else localStorage.removeItem("theme"); } catch (e) { }
    rebuildCharts();
    dirty = true;
  }
  try { const t = localStorage.getItem("theme"); if (t) document.documentElement.setAttribute("data-theme", t); } catch (e) { }
  $("#theme-toggle").onclick = () => {
    const dark = document.documentElement.getAttribute("data-theme") === "dark" ||
      (!document.documentElement.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
    applyTheme(dark ? "light" : "dark");
  };

  // ---------- data ----------
  function pushSample(s) {
    for (const k of Object.keys(s)) {
      if (!cols[k]) cols[k] = new Array(n).fill(null);
      cols[k].push(typeof s[k] === "number" ? s[k] : (s[k] === null || s[k] === undefined ? null : s[k]));
    }
    for (const k of Object.keys(cols)) if (cols[k].length < n + 1) cols[k].push(null);
    n++;
    const maxN = Math.round(MAX_SECONDS * (status.sample_hz || 5)) + 50;
    if (n > maxN) {
      const cut = n - maxN;
      for (const k of Object.keys(cols)) cols[k].splice(0, cut);
      n = maxN;
    }
    latest = s;
    lastSampleAt = Date.now();
    dirty = true;
  }
  function setColumns(c) {
    for (const k of Object.keys(cols)) delete cols[k];
    n = (c.t_unix || []).length;
    for (const k of Object.keys(c)) cols[k] = c[k].slice();
    for (const k of Object.keys(cols)) while (cols[k].length < n) cols[k].push(null);
  }
  function rowAt(i) { const r = {}; if (i < 0 || i >= n) return r; for (const k of Object.keys(cols)) r[k] = cols[k][i]; return r; }

  function hasData(f) { const a = cols[f]; if (!a) return false; const end = endIndex(); for (let i = end - 1; i >= Math.max(0, end - 300); i--) if (a[i] !== null && a[i] !== undefined) return true; return false; }

  function windowData(fields) {
    const t = cols.t_unix || [];
    const end = endIndex();
    const cutoff = nowSec() - windowSec;
    let start = 0;
    while (start < end && t[start] < cutoff) start++;
    const out = [t.slice(start, end)];
    for (const f of fields) {
      const a = (cols[f] || new Array(t.length).fill(null)).slice(start, end);
      out.push(imperial && IMPERIAL[f] ? a.map((v) => conv(f, v)) : a);
    }
    return out;
  }

  // ---------- charts ----------
  const tooltip = $("#tooltip");
  function tooltipPlugin(def) {
    return {
      hooks: {
        setCursor: (u) => {
          const idx = u.cursor.idx;
          if (idx == null || u.cursor.left < 0) { tooltip.classList.add("hidden"); return; }
          const t = u.data[0][idx];
          if (t == null) { tooltip.classList.add("hidden"); return; }
          const d = new Date(t * 1000);
          let html = `<div class="t">${d.toLocaleTimeString()}</div>`;
          const pal = palette();
          def.series.forEach((s, i) => {
            const v = u.data[i + 1][idx];
            html += `<div class="row"><span class="sw" style="background:${pal[i % pal.length]}"></span>${s.label}: <b>${fmt(v, decOf(s.f, def.dec))}</b> ${unitOf(s.f, def.unit)}</div>`;
          });
          tooltip.innerHTML = html;
          tooltip.classList.remove("hidden");
          const rect = u.over.getBoundingClientRect();
          let x = rect.left + u.cursor.left + 14, y = rect.top + u.cursor.top + 14;
          if (x + tooltip.offsetWidth > innerWidth - 8) x = rect.left + u.cursor.left - tooltip.offsetWidth - 14;
          if (y + tooltip.offsetHeight > innerHeight - 8) y = innerHeight - tooltip.offsetHeight - 8;
          tooltip.style.left = x + "px"; tooltip.style.top = y + "px";
        },
      },
    };
  }
  function markersPlugin() {
    return {
      hooks: {
        draw: (u) => {
          if (!markers.length) return;
          const ctx = u.ctx;
          ctx.save();
          ctx.strokeStyle = css("--s2"); ctx.fillStyle = css("--s2");
          ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
          ctx.font = "11px system-ui"; ctx.textBaseline = "top";
          const [tmin, tmax] = [u.scales.x.min, u.scales.x.max];
          for (const m of markers) {
            if (m.t_unix < tmin || m.t_unix > tmax) continue;
            const x = Math.round(u.valToPos(m.t_unix, "x", true));
            ctx.beginPath(); ctx.moveTo(x, u.bbox.top); ctx.lineTo(x, u.bbox.top + u.bbox.height); ctx.stroke();
            ctx.fillText(m.note || "mark", x + 4, u.bbox.top + 2);
          }
          ctx.restore();
        },
      },
    };
  }

  function makeChart(def) {
    const el = document.createElement("div");
    el.className = "chart";
    const cu = unitOf(def.series[0].f, def.unit), cdec = decOf(def.series[0].f, def.dec);
    el.innerHTML = `<div class="chart-head"><span class="chart-title">${def.title}${cu ? " · " + cu : ""}</span><span class="chart-now" id="now-${def.id}">—</span></div><div class="plot"></div>`;
    $("#charts").appendChild(el);
    const pal = palette();
    const opts = {
      width: el.clientWidth - 16, height: 170,
      cursor: { points: { size: 8 }, drag: { x: false, y: false } },
      legend: { show: def.series.length > 1, live: false },
      scales: { x: { time: true } },
      axes: [
        { stroke: css("--muted"), grid: { stroke: css("--grid"), width: 1 }, ticks: { stroke: css("--axis"), width: 1 }, font: "11px system-ui", space: 70,
          values: [[1, "{HH}:{mm}:{ss}", null, null, null, null, null, null, 1]] },
        { stroke: css("--muted"), grid: { stroke: css("--grid"), width: 1 }, ticks: { show: false }, font: "11px system-ui", size: 52,
          values: (u, vals) => vals.map((v) => fmt(v, cdec)) },
      ],
      series: [{ label: "time" }].concat(def.series.map((s, i) => ({ label: s.label, stroke: pal[i % pal.length], width: 2, spanGaps: true, points: { show: false } }))),
      plugins: [tooltipPlugin(def)].concat(def.markers ? [markersPlugin()] : []),
    };
    const u = new uPlot(opts, windowData(def.series.map((s) => s.f)), el.querySelector(".plot"));
    return { u, def, el };
  }
  function ensureCharts() {
    for (const def of CHARTS) {
      if (charts[def.id]) continue;
      if (def.series.some((s) => hasData(s.f))) charts[def.id] = makeChart(def);
    }
  }
  function rebuildCharts() {
    for (const id of Object.keys(charts)) { charts[id].u.destroy(); charts[id].el.remove(); delete charts[id]; }
    ensureCharts();
    for (const p of Object.keys(profiles)) { profiles[p].el.remove(); delete profiles[p]; }
  }
  function redraw() {
    ensureCharts();
    for (const id of Object.keys(charts)) {
      const c = charts[id];
      c.u.setData(windowData(c.def.series.map((s) => s.f)));
      const f0 = c.def.series[0].f, v = conv(f0, latest[f0]), uu = unitOf(f0, c.def.unit);
      $("#now-" + id).textContent = fmt(v, decOf(f0, c.def.dec)) + (uu ? " " + uu : "");
    }
  }
  addEventListener("resize", () => {
    for (const id of Object.keys(charts)) { const c = charts[id]; c.u.setSize({ width: c.el.clientWidth - 16, height: 170 }); }
    profilesDirty = true;
  });

  // ---------- vertical profiles (value vs altitude, binned per metre, drawn on canvas) ----------
  const profiles = {};
  let profilesDirty = true;
  let lastProfileDraw = 0;
  function altitudeRange() {
    const a = cols.altitude_m; if (!a) return null;
    const end = endIndex(); let lo = Infinity, hi = -Infinity;
    for (let i = 0; i < end; i++) { const v = a[i]; if (v == null) continue; if (v < lo) lo = v; if (v > hi) hi = v; }
    return hi > lo ? [lo, hi] : null;
  }
  function drawProfile(p, range) {
    const alt = cols.altitude_m, val = cols[p.f]; if (!alt || !val) return;
    const end = endIndex();
    const binSize = Math.max(0.5, (range[1] - range[0]) / 60);
    const bins = new Map();
    let vmin = Infinity, vmax = -Infinity;
    const pts = [];
    for (let i = 0; i < end; i++) {
      const a = alt[i], v = val[i]; if (a == null || v == null) continue;
      const b = Math.round(a / binSize);
      const e = bins.get(b) || { s: 0, c: 0 }; e.s += v; e.c++; bins.set(b, e);
      if (v < vmin) vmin = v; if (v > vmax) vmax = v;
      if (i % Math.max(1, Math.floor(end / 1500)) === 0) pts.push([v, a]);
    }
    if (!bins.size) return;
    if (vmax - vmin < 1e-9) { vmin -= 1; vmax += 1; }
    const pad = (vmax - vmin) * 0.08; vmin -= pad; vmax += pad;
    const cv = p.canvas, dpr = devicePixelRatio || 1;
    const W = cv.clientWidth, H = cv.clientHeight;
    if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
    const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
    const L = 38, R = 8, T = 8, B = 22;
    const X = (v) => L + (v - vmin) / (vmax - vmin) * (W - L - R);
    const Y = (a) => T + (1 - (a - range[0]) / (range[1] - range[0])) * (H - T - B);
    ctx.strokeStyle = css("--grid"); ctx.lineWidth = 1; ctx.fillStyle = css("--muted"); ctx.font = "10px system-ui";
    const yTicks = 5;
    for (let i = 0; i <= yTicks; i++) {
      const a = range[0] + (range[1] - range[0]) * i / yTicks, y = Math.round(Y(a)) + 0.5;
      ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(W - R, y); ctx.stroke();
      ctx.textAlign = "right"; ctx.textBaseline = "middle"; ctx.fillText(fmt(conv("altitude_m", a), 0) + " " + unitOf("altitude_m", "m"), L - 4, y);
    }
    const xTicks = 4;
    for (let i = 0; i <= xTicks; i++) {
      const v = vmin + (vmax - vmin) * i / xTicks, x = Math.round(X(v)) + 0.5;
      ctx.beginPath(); ctx.moveTo(x, T); ctx.lineTo(x, H - B); ctx.stroke();
      ctx.textAlign = i === 0 ? "left" : (i === xTicks ? "right" : "center"); ctx.textBaseline = "top"; ctx.fillText(fmt(conv(p.f, v), decOf(p.f, p.dec)), x, H - B + 4);
    }
    const c1 = css("--s1");
    ctx.globalAlpha = 0.18; ctx.fillStyle = c1;
    for (const [v, a] of pts) { ctx.beginPath(); ctx.arc(X(v), Y(a), 1.6, 0, 6.283); ctx.fill(); }
    ctx.globalAlpha = 1;
    const keys = [...bins.keys()].sort((a, b) => a - b);
    ctx.strokeStyle = c1; ctx.lineWidth = 2; ctx.lineJoin = "round"; ctx.beginPath();
    keys.forEach((k, i) => { const e = bins.get(k); const x = X(e.s / e.c), y = Y(k * binSize); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
    ctx.stroke();
    const cur = latest[p.f], ca = latest.altitude_m;
    if (cur != null && ca != null) { ctx.fillStyle = css("--s2"); ctx.beginPath(); ctx.arc(X(cur), Y(ca), 4, 0, 6.283); ctx.fill(); }
    p.now.textContent = fmt(conv(p.f, cur), decOf(p.f, p.dec)) + (unitOf(p.f, p.unit) ? " " + unitOf(p.f, p.unit) : "");
  }
  function renderProfiles(force) {
    const now = Date.now();
    if (!force && now - lastProfileDraw < 1000) return;
    lastProfileDraw = now;
    const range = altitudeRange();
    const note = $("#profiles-note");
    if (!range || range[1] - range[0] < 3) { note.textContent = "waiting for ≥ 3 m of altitude change"; return; }
    note.textContent = "binned mean (line) and raw samples (dots), " + range[0].toFixed(0) + " to " + range[1].toFixed(0) + " m";
    for (const def of PROFILES) {
      if (!cols[def.f] || !hasData(def.f)) continue;
      let p = profiles[def.f];
      if (!p) {
        const el = document.createElement("div"); el.className = "profile";
        el.innerHTML = `<div class="ptitle"><span>${def.title}${def.unit ? " · " + def.unit : ""}</span><span class="pnow"></span></div><canvas></canvas>`;
        $("#profiles").appendChild(el);
        p = profiles[def.f] = Object.assign({}, def, { el, canvas: el.querySelector("canvas"), now: el.querySelector(".pnow") });
      }
      drawProfile(p, range);
    }
  }

  // ---------- tiles / chips / table ----------
  function renderTiles() {
    const box = $("#tiles");
    for (const t of TILES) {
      let el = document.getElementById("tile-" + t.f);
      const v = t.f in detTiles ? detTiles[t.f] : latest[t.f];
      if (v === undefined || v === null) { if (el) el.classList.add("hidden"); continue; }
      if (!el) {
        el = document.createElement("div"); el.id = "tile-" + t.f; el.className = "tile" + (t.hero ? " hero" : "");
        el.innerHTML = `<div class="label">${t.label}</div><div class="value"><span class="v"></span><small>${t.unit}</small><small class="x"></small></div>`;
        box.appendChild(el);
      }
      el.classList.remove("hidden");
      el.querySelector(".v").textContent = fmt(conv(t.f, v), decOf(t.f, t.dec));
      el.querySelector(".value small").textContent = unitOf(t.f, t.unit);
      if (t.extra) el.querySelector(".x").textContent = latest[t.extra] ? " " + String(latest[t.extra]).replace(/:/g, " ").replace(/,/g, " · ") : "";
    }
  }
  // ---------- detections from the ground station (boxes over the video, counts as tiles) ----------
  let detSeq = -1, heading = 0, stabilize = false;
  try { stabilize = localStorage.getItem("stabilize") === "1"; } catch (e) { }
  function applyStabilize() {
    $("#view-live").classList.toggle("stabilized", stabilize);
    $("#btn-stab").classList.toggle("on", stabilize);
    $("#view-live").style.setProperty("--heading", (stabilize ? -heading : 0) + "deg");
  }
  $("#btn-stab").onclick = () => { stabilize = !stabilize; try { localStorage.setItem("stabilize", stabilize ? "1" : "0"); } catch (e) { } applyStabilize(); };
  applyStabilize();
  async function pollDetections() {
    if (replay) return;
    try {
      const r = await fetch("/api/detections"); const d = await r.json();
      const svg = $("#det-overlay"), badge = $("#det-badge");
      if (!d.available) { svg.innerHTML = ""; badge.classList.add("hidden"); detTiles = {}; return; }
      const stale = d.age_s > 15;
      if (d.n !== detSeq) {
        detSeq = d.n;
        latest.det_total = d.total != null ? d.total : (d.detections || []).length;
        latest.det_classes = Object.entries(d.by_class || {}).map(([k, v]) => k + ":" + v).join(",");
        dirty = true;
        const W = d.width || 640, H = d.height || 480;
        svg.setAttribute("viewBox", "0 0 " + W + " " + H);
        svg.innerHTML = (d.detections || []).map((b) => {
          const [x1, y1, x2, y2] = (Array.isArray(b.xyxy) ? b.xyxy : [0, 0, 0, 0]).map((v) => Number(v) || 0);
          const cls = b.cls === "car" || b.cls === "person" ? b.cls : "other";
          const label = /^[\w-]{1,24}$/.test(b.cls) ? b.cls : "?", conf = Number(b.conf);
          return `<rect class="${cls}" x="${x1}" y="${y1}" width="${Math.max(0, x2 - x1)}" height="${Math.max(0, y2 - y1)}" rx="2"/>` +
            `<text x="${x1 + 2}" y="${Math.max(10, y1 - 3)}">${label}${conf ? " " + Math.round(conf * 100) + "%" : ""}</text>`;
        }).join("");
        const c = d.counts || {};
        detTiles = { det_cars: Number(c.car) || 0, det_people: Number(c.person) || 0 };
        dirty = true;
      }
      if (d.heading_deg != null) {                       // spin tracker heading drives the Stabilize view
        heading = d.heading_deg; $("#heading-badge").classList.remove("hidden");
        $("#heading-badge").textContent = "spin " + (heading >= 0 ? "+" : "") + heading.toFixed(0) + "°" + (d.spin_conf != null && d.spin_conf < 0.3 ? " (low conf)" : "");
        if (stabilize) $("#view-live").style.setProperty("--heading", (-heading) + "deg");
      }
      badge.classList.remove("hidden");
      const parts = Object.entries(d.by_class || {}).slice(0, 6).map(([k, v]) => k + " " + v);
      badge.textContent = (stale ? "detector stale · " : "") + (parts.length ? parts.join(" · ") : "nothing detected") + (Object.keys(d.by_class || {}).length > 6 ? " · …" : "");
      svg.style.opacity = stale ? 0.35 : 1;
    } catch (e) { }
  }
  setInterval(pollDetections, 1000);

  // ---------- orientation (bubble level + side view) ----------
  function renderOrientation() {
    const ax = latest.ax_g, ay = latest.ay_g, az = latest.az_g, tilt = latest.tilt_deg;
    const card = $("#orient-card");
    if (ax == null || tilt == null) { card.classList.add("hidden"); return; }
    card.classList.remove("hidden");
    // direction of lean in the sensor's horizontal plane; magnitude = tilt relative to the Level reference
    const ref = status.level_ref;
    let hx = ax, hy = ay;
    if (ref) { hx = ax - ref[0]; hy = ay - ref[1]; }           // deviation from the upright reference
    const dir = Math.atan2(hy, hx);
    const r = Math.min(1, tilt / 45) * 70;                     // 45° reaches the outer ring
    $("#bubble").setAttribute("cx", (80 + r * Math.cos(dir)).toFixed(1));
    $("#bubble").setAttribute("cy", (80 - r * Math.sin(dir)).toFixed(1));
    $("#orient-bubble-lbl").textContent = tilt < 1.5 ? "level" : tilt.toFixed(1) + "°";
    $("#orient-sub").textContent = "pitch " + fmt(latest.pitch_deg, 0) + "° · roll " + fmt(latest.roll_deg, 0) + "°";
    $("#orient-note").textContent = status.leveled ? "relative to the Level reference" : "press Level once the payload hangs still";
    // mini bubble inside the mobile metric bar
    const mb = $("#mchip-tilt-bubble");
    if (mb) { const rr = Math.min(1, tilt / 45) * 7; mb.setAttribute("cx", (10 + rr * Math.cos(dir)).toFixed(1)); mb.setAttribute("cy", (10 - rr * Math.sin(dir)).toFixed(1)); }
  }

  // ---------- talk to the balloon: chat with captions, voice in, spoken replies ----------
  let narSeq = 0, voiceOn = false, lastPlayedId = 0;
  const narAudio = $("#nar-audio"), chat = $("#chat");
  const pendingQ = {};                                  // question text -> local bubble (until the answer arrives)
  function speak(rec) {
    if (!voiceOn || !rec || !rec.audio_url || rec.id <= lastPlayedId) return;
    lastPlayedId = rec.id;
    narAudio.src = rec.audio_url; narAudio.play().catch(() => {});
  }
  function addMsg(cls, text, opts) {
    opts = opts || {};
    const el = document.createElement("div");
    el.className = "msg " + cls + (opts.pending ? " pending" : "");
    const t = opts.t ? new Date(opts.t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
    el.innerHTML = `<div class="text"></div><div class="meta">${t ? `<span>${t}</span>` : ""}${opts.audio ? `<button data-audio="${opts.audio}">▶ play</button>` : ""}</div>`;
    el.querySelector(".text").textContent = text;
    const stick = chat.scrollTop + chat.clientHeight >= chat.scrollHeight - 40;
    chat.appendChild(el);
    while (chat.children.length > 120) chat.removeChild(chat.firstChild);
    if (stick) chat.scrollTop = chat.scrollHeight;
    return el;
  }
  function renderCaption(c) {
    if (c.kind === "answer") {
      const q = c.question || "";
      if (pendingQ[q]) { pendingQ[q].remove(); delete pendingQ[q]; } else addMsg("user", q, { t: c.t_unix });
      addMsg("bot", c.text, { t: c.t_unix, audio: c.audio_url });
    } else {
      addMsg("caption", c.text, { t: c.t_unix, audio: c.audio_url });
    }
  }
  async function pollCaptions() {
    if (replay) return;
    try {
      const r = await fetch("/api/captions?since=" + narSeq); const d = await r.json();
      if (d.items.length) { narSeq = d.seq; d.items.forEach(renderCaption); speak(d.items[d.items.length - 1]); }
      $("#nar-status").textContent = d.narrator_online ? "narrator live · Claude watching the camera" :
        (d.latest ? "narrator offline (last caption " + Math.round((Date.now() / 1000 - d.latest.t_unix) / 60) + " min ago) · run ground/start.sh on the laptop" : "narrator offline · run ground/start.sh on the laptop");
    } catch (e) { logOnce("captions", e); }
  }
  setInterval(pollCaptions, 1500);
  chat.addEventListener("click", (e) => { const b = e.target.closest("button[data-audio]"); if (b) { narAudio.src = b.dataset.audio; narAudio.play().catch(() => {}); } });
  $("#btn-voice").onclick = () => {
    voiceOn = !voiceOn;
    $("#btn-voice").textContent = voiceOn ? "🔊 Speaking" : "🔇 Muted";
    $("#btn-voice").classList.toggle("voice-on", voiceOn); $("#btn-voice").classList.toggle("ghost", !voiceOn);
    $("#btn-voice").setAttribute("aria-pressed", String(voiceOn));
    if (voiceOn) { narAudio.muted = false; narAudio.play().catch(() => {}); }   // the tap unlocks audio on phones
  };
  async function ask(text) {
    text = (text || "").trim(); if (!text) return;
    const bubble = addMsg("user", text, { t: Date.now() / 1000 });
    pendingQ[text] = bubble;
    const wait = addMsg("bot", "…", { pending: true });
    try {
      const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
      const d = await r.json(); if (!d.ok) throw new Error(d.error || "ask failed");
      const t0 = Date.now();
      const timer = setInterval(async () => {
        try {
          const s = await (await fetch("/api/ask/" + d.id)).json();
          if (s.answer) { clearInterval(timer); wait.remove(); }          // the real answer arrives through pollCaptions
          else if (Date.now() - t0 > 60000) { clearInterval(timer); wait.textContent = "No answer: the laptop narrator isn't running (ground/start.sh)."; wait.classList.remove("pending"); delete pendingQ[text]; }
        } catch (e) { }
      }, 1000);
    } catch (e) { wait.textContent = "Could not send: " + e.message; wait.classList.remove("pending"); }
  }
  $("#btn-ask").onclick = () => { ask($("#ask-text").value); $("#ask-text").value = ""; };
  $("#ask-text").addEventListener("keydown", (e) => { if (e.key === "Enter") { ask($("#ask-text").value); $("#ask-text").value = ""; } });
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null;
  $("#btn-mic").onclick = () => {
    if (!SR) { $("#ask-text").focus(); $("#nar-status").textContent = "Voice input isn't available in this browser here (needs HTTPS on most phones); type instead."; return; }
    if (rec) { rec.stop(); return; }
    try { rec = new SR(); } catch (e) { $("#nar-status").textContent = "Mic unavailable: " + e.message; return; }
    rec.lang = "en-US"; rec.interimResults = true; rec.continuous = false;
    $("#btn-mic").textContent = "⏹"; $("#btn-mic").classList.add("rec"); $("#ask-text").placeholder = "Listening…";
    let finalText = "";
    rec.onresult = (e) => { let t = ""; for (const r of e.results) t += r[0].transcript; $("#ask-text").value = t; if (e.results[e.results.length - 1].isFinal) finalText = t; };
    rec.onerror = (e) => { $("#nar-status").textContent = "Mic error: " + e.error + (e.error === "not-allowed" ? " (browser blocked the mic on a plain-http page; type instead)" : ""); };
    rec.onend = () => { $("#btn-mic").textContent = "🎤"; $("#btn-mic").classList.remove("rec"); $("#ask-text").placeholder = "Ask what it sees, how high it is, anything…"; rec = null;
      const t = finalText || $("#ask-text").value; if (t.trim()) { ask(t); $("#ask-text").value = ""; } };
    rec.start();
  };

  // ---------- mobile metric bar: main readings first, colour-coded ----------
  const METRICS = [
    { f: "elevation_msl_m", label: "elevation", unit: "m", dec: 0, color: "--s1" },
    { f: "pressure_hpa", label: "pressure", unit: "hPa", dec: 1, color: "--s2" },
    { f: "temp_c", label: "temp", unit: "°C", dec: 1, color: "--s3" },
    { f: "tilt_deg", label: "tilt", unit: "°", dec: 0, color: "--s3", bubble: true, warn: (v) => v > 25 ? "warn" : "" },
    { f: "aq_raw", label: "air quality", unit: "", dec: 0, color: "--s2", warn: (v) => v > 700 ? "bad" : (v > 300 ? "warn" : "") },
    { f: "altitude_m", label: "altitude", unit: "m", dec: 1, color: "--s1" },
    { f: "vspeed_mps", label: "climb", unit: "m/s", dec: 2, color: "--s1", secondary: true },
    { f: "det_total", label: "yolo", unit: "", dec: 0, color: "--s2", secondary: true },
    { f: "cpu_temp_c", label: "cpu", unit: "°C", dec: 0, color: "--s3", secondary: true, warn: (v) => v > 75 ? "bad" : "" },
  ];
  function renderMetricBar() {
    const bar = $("#metricbar");
    if (!bar || getComputedStyle(bar).display === "none") return;
    for (const m of METRICS) {
      const v = latest[m.f];
      let el = document.getElementById("mchip-" + m.f);
      if (v == null) { if (el) el.classList.add("hidden"); continue; }
      if (!el) {
        el = document.createElement("div"); el.id = "mchip-" + m.f; el.className = "mchip";
        el.innerHTML = (m.bubble
          ? `<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7" class="ring"/><circle id="mchip-tilt-bubble" cx="10" cy="10" r="3" class="bubble"/></svg>`
          : `<span class="d" style="background:var(${m.color})"></span>`) + `<span class="l">${m.label}</span><span class="v"></span>`;
        bar.appendChild(el);
      }
      el.classList.remove("hidden");
      const uu = unitOf(m.f, m.unit);
      el.querySelector(".v").textContent = fmt(conv(m.f, v), decOf(m.f, m.dec)) + (uu ? " " + uu : "");
      el.className = "mchip " + (m.secondary ? "secondary " : "") + (m.warn ? m.warn(v) : "");
    }
  }

  let peakAlt = null;
  function renderFlight() {
    if (replay) { peakAlt = null; const end = endIndex(); const a = cols.altitude_m || []; for (let i = 0; i < end; i++) if (a[i] != null && (peakAlt == null || a[i] > peakAlt)) peakAlt = a[i]; }
    else {
      const a = latest.altitude_m;
      if (a != null && (peakAlt == null || a > peakAlt)) peakAlt = a;
      if (peakAlt == null && cols.altitude_m) for (const v of cols.altitude_m) if (v != null && (peakAlt == null || v > peakAlt)) peakAlt = v;
    }
    $("#chip-peak").textContent = "peak " + (peakAlt == null ? "—" : fmt(conv("altitude_m", peakAlt), decOf("altitude_m", 1))) + " " + unitOf("altitude_m", "m");
    const tNow = latest.t_unix;
    const launch = markers.filter((m) => /launch|release|lift/i.test(m.note || "") && (!tNow || m.t_unix <= tNow)).slice(-1)[0];
    if (launch && tNow) {
      const s = Math.max(0, Math.round(tNow - launch.t_unix));
      $("#chip-aloft").textContent = "aloft " + Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
    } else $("#chip-aloft").textContent = "launch not marked";
    const nm = replay ? markers.filter((m) => !tNow || m.t_unix <= tNow).length : markers.length;
    $("#chip-markers").textContent = nm + " marker" + (nm === 1 ? "" : "s");
    const sess = replay ? REPLAY : status.session;
    if (sess) {
      $("#csv-link").href = "/data/sessions/" + sess + "/telemetry.csv";
      $("#browse-link").href = "/data/sessions/" + sess + "/";
    }
  }
  function renderChips() {
    $("#chip-samples").textContent = (replay ? endIndex() : (status.samples || n)) + " samples";
    const free = latest.disk_free_gb; $("#chip-disk").textContent = "disk " + (free != null ? free.toFixed(1) + " GB free" : "—");
    $("#chip-disk").classList.toggle("bad", free != null && free < 1.5);
    const cpu = latest.cpu_temp_c; $("#chip-cpu").textContent = "cpu " + (cpu != null ? cpu.toFixed(0) + "°C" : "—");
    $("#chip-cpu").classList.toggle("bad", cpu != null && cpu > 75);
    const rssi = latest.wifi_rssi_dbm; $("#chip-rssi").textContent = "wifi " + (rssi != null ? rssi + " dBm" : "—");
    $("#chip-rssi").classList.toggle("bad", rssi != null && rssi < -75);
  }
  function renderTable() {
    const tb = $("#values-table tbody");
    const keys = Object.keys(latest).sort();
    tb.innerHTML = keys.map((k) => `<tr><td>${k}</td><td>${typeof latest[k] === "number" ? latest[k] : (latest[k] != null ? latest[k] : "—")}</td></tr>`).join("");
  }

  function tick() {
    if (replay) {
      $("#conn-dot").className = "dot " + (replay.playing ? "live" : "");
      $("#conn-text").textContent = "replay" + (replay.playing ? " " + replay.speed + "×" : " paused");
      $("#conn-text").classList.remove("bad");
    } else {
      const alive = Date.now() - lastSampleAt < 3000;
      $("#conn-dot").className = "dot " + (alive ? "live" : "down");
      $("#conn-text").textContent = alive ? "live" : "no data";
      $("#conn-text").classList.toggle("bad", !alive);
    }
    if (dirty) {
      dirty = false;
      for (const [name, fn] of [["charts", redraw], ["tiles", renderTiles], ["metricbar", renderMetricBar], ["chips", renderChips],
                                ["flight", renderFlight], ["orientation", renderOrientation], ["profiles", () => renderProfiles(false)]]) {
        try { fn(); } catch (e) { logOnce(name, e); }
      }
      try { if ($("#values-table").closest("details").open) renderTable(); } catch (e) { logOnce("table", e); }
    }
  }
  setInterval(() => { try { tick(); } catch (e) { logOnce("tick", e); } }, 250);

  // ---------- SSE ----------
  function connect() {
    const es = new EventSource("/events");
    es.addEventListener("sample", (e) => { try { pushSample(JSON.parse(e.data)); } catch (err) { logOnce("sse", err); } });
    es.addEventListener("marker", (e) => { try { markers.push(JSON.parse(e.data)); dirty = true; } catch (err) { logOnce("marker", err); } });
    es.onerror = () => { /* EventSource reconnects on its own */ };
  }
  async function loadHistory() {
    try {
      const r = await fetch("/api/history?seconds=" + MAX_SECONDS);
      const j = await r.json();
      setColumns(j.columns || {});
      if (n) { latest = rowAt(n - 1); lastSampleAt = Date.now(); }
      dirty = true;
    } catch (e) { console.warn("history failed", e); }
  }
  async function pollStatus() {
    try {
      const r = await fetch("/api/status"); status = await r.json();
      $("#chip-session").textContent = "session " + (status.session || "—");
      if (!replay) markers = status.markers || markers;
      $("#servo-row").classList.toggle("hidden", !status.servo || !!replay);
      const si = status.sensors || {};
      $("#sensors-info").textContent = status.sim ? "SIMULATED sensors (BALLOON_SIM=1)" :
        "I2C: " + (si.i2c_addresses || []).join(", ") + " · detected: " + (si.sensors || []).map((s) => s.name).join(", ") +
        ((si.errors || []).length ? " · errors: " + si.errors.join("; ") : "");
      if (!replay && status.mosaic && mosaicVisible()) refreshMosaic();
    } catch (e) { logOnce("status", e); }
  }
  async function pollSessions() {
    try {
      const r = await fetch("/api/sessions"); const list = await r.json();
      $("#sessions-table tbody").innerHTML = list.map((s) => `<tr><td>${s.name}${s.current ? " (current)" : ""}</td><td>${s.size_mb} MB</td><td>${s.video_segments}</td><td>${s.stills}</td><td><a href="${s.csv}" download>csv</a> · <a href="/data/sessions/${s.name}/">browse</a> · <a href="/?replay=${s.name}">replay</a></td></tr>`).join("");
    } catch (e) { }
  }

  // ---------- camera ----------
  const cam = $("#cam");
  function camUrl() { return `${location.protocol}//${location.hostname}:${status.camera_port || 8081}/stream?t=${Date.now()}`; }
  function startCam() { if (replay) return; $("#cam-overlay").classList.remove("hidden"); cam.src = camUrl(); }
  cam.onload = () => $("#cam-overlay").classList.add("hidden");
  cam.onerror = () => { if (replay) return; $("#cam-overlay").classList.remove("hidden"); setTimeout(startCam, 3000); };
  const mosaicVisible = () => !$("#view-mosaic").classList.contains("hidden");
  function refreshMosaic() { $("#mosaic").src = (replay ? "/data/sessions/" + REPLAY + "/mosaic.jpg" : "/mosaic.jpg") + "?t=" + Date.now(); }
  $("#mosaic").onload = () => $("#mosaic-overlay").classList.add("hidden");
  $("#mosaic").onerror = () => $("#mosaic-overlay").classList.remove("hidden");
  setInterval(() => { if (!replay && mosaicVisible()) refreshMosaic(); }, 5000);
  document.querySelectorAll(".tab").forEach((b) => b.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
    const live = b.dataset.view === "live";
    $("#view-live").classList.toggle("hidden", !live); $("#view-mosaic").classList.toggle("hidden", live);
    if (live) { if (replay) showReplayStill(true); else startCam(); } else { if (!replay) cam.src = ""; refreshMosaic(); }
  });

  // ---------- controls ----------
  $("#window-seg").querySelectorAll("button").forEach((b) => b.onclick = () => {
    windowSec = +b.dataset.win; $("#window-seg").querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b)); dirty = true;
  });
  $("#btn-mark").onclick = async () => {
    if (replay) return;
    const note = $("#mark-note").value.trim() || "mark";
    $("#btn-mark").textContent = "✓"; setTimeout(() => ($("#btn-mark").textContent = "Mark"), 800);
    await fetch("/api/mark", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note }) });
    $("#mark-note").value = "";
  };
  $("#btn-zero").onclick = () => { if (!replay) fetch("/api/zero", { method: "POST" }); };
  $("#btn-level").onclick = () => { if (!replay) fetch("/api/level", { method: "POST" }); };
  $("#btn-level2").onclick = () => { if (!replay) fetch("/api/level", { method: "POST" }); };
  const servo = $("#servo");
  let servoTimer = null;
  servo.oninput = () => { $("#servo-val").textContent = servo.value + "°"; clearTimeout(servoTimer);
    servoTimer = setTimeout(() => fetch("/api/servo", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ angle: +servo.value }) }), 80); };
  $("#values-table").closest("details").addEventListener("toggle", renderTable);

  // units toggle: rebuild charts/profiles so titles and axes update
  function applyUnits() {
    $("#units-toggle").textContent = imperial ? "ft/°F" : "m/°C";
    for (const id of Object.keys(charts)) { charts[id].u.destroy(); charts[id].el.remove(); delete charts[id]; }
    for (const k of Object.keys(profiles)) { profiles[k].el.remove(); delete profiles[k]; }
    dirty = true; lastProfileDraw = 0;
  }
  $("#units-toggle").onclick = () => { imperial = !imperial; try { localStorage.setItem("units", imperial ? "imperial" : "metric"); } catch (e) { } applyUnits(); };
  applyUnits();

  // QR overlay
  $("#qr-toggle").onclick = () => {
    $("#qr-img").src = "/qr.svg?t=" + Date.now();
    $("#qr-url").textContent = location.protocol + "//" + location.host + "/";
    $("#qr-overlay").classList.remove("hidden");
  };
  $("#qr-overlay").onclick = () => $("#qr-overlay").classList.add("hidden");

  // ---------- replay ----------
  let lastStill = null;
  function showReplayStill(force) {
    if (!replay || !replay.stills.length) return;
    const t = replay.t;
    let lo = 0, hi = replay.stills.length - 1;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (replay.stills[mid].t < t) lo = mid + 1; else hi = mid; }
    const s = replay.stills[lo];
    if (s && (force || s !== lastStill)) { lastStill = s; cam.src = "/data/sessions/" + REPLAY + "/stills/" + s.file; $("#cam-overlay").classList.add("hidden"); }
  }
  function setReplayTime(t) {
    replay.t = Math.min(replay.t1, Math.max(replay.t0, t));
    latest = rowAt(Math.max(0, endIndex() - 1));
    $("#rp-time").textContent = new Date(replay.t * 1000).toLocaleTimeString() + "  (+" + Math.round(replay.t - replay.t0) + " s)";
    $("#rp-scrub").value = Math.round((replay.t - replay.t0) / (replay.t1 - replay.t0) * 1000);
    showReplayStill(false);
    dirty = true;
  }
  async function startReplay() {
    const r = await fetch("/api/replay/" + encodeURIComponent(REPLAY));
    if (!r.ok) { showError("replay session not found: " + REPLAY); return; }
    const j = await r.json();
    setColumns(j.columns || {});
    markers = j.markers || [];
    const t = cols.t_unix || [];
    replay = { t0: t[0] || 0, t1: t[t.length - 1] || 1, t: t[0] || 0, speed: 10, playing: false, stills: [] };
    try {
      const txt = await (await fetch("/data/sessions/" + REPLAY + "/stills/index.csv")).text();
      replay.stills = txt.trim().split("\n").slice(1).map((l) => { const p = l.split(","); return { file: p[0], t: +p[1] }; }).filter((s) => s.file && s.t);
    } catch (e) { }
    $("#replay-bar").classList.remove("hidden"); $("#live-link").classList.remove("hidden");
    $("#rp-session").textContent = "replay " + REPLAY + " · " + n + " samples";
    document.querySelector(".actions").classList.add("hidden");
    if (!replay.stills.length) { $("#cam-overlay").textContent = "no stills in this session"; }
    $("#rp-play").onclick = () => { replay.playing = !replay.playing; $("#rp-play").textContent = replay.playing ? "Pause" : "Play"; if (replay.playing && replay.t >= replay.t1) setReplayTime(replay.t0); };
    $("#rp-speed").onchange = () => (replay.speed = +$("#rp-speed").value);
    $("#rp-scrub").oninput = () => setReplayTime(replay.t0 + (+$("#rp-scrub").value / 1000) * (replay.t1 - replay.t0));
    let last = Date.now();
    setInterval(() => {
      const now = Date.now(); const dt = (now - last) / 1000; last = now;
      if (replay.playing) { setReplayTime(replay.t + dt * replay.speed); if (replay.t >= replay.t1) { replay.playing = false; $("#rp-play").textContent = "Play"; } }
    }, 100);
    setReplayTime(replay.t1);   // start showing the full flight; press Play to animate from the start
    replay.t = replay.t1;
    renderProfiles(true);
  }

  // ---------- boot ----------
  (async () => {
    await pollStatus();
    if (REPLAY) { await startReplay(); pollSessions(); return; }
    await loadHistory();
    connect();
    startCam();
    pollSessions();
    setInterval(pollStatus, 5000);
    setInterval(pollSessions, 30000);
  })();
})();
