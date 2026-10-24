/* Balloon dashboard: SSE-fed live charts (uPlot), camera stream, markers, controls. */
(function () {
  "use strict";
  // Surface JS errors on the page itself (phones have no console).
  function showError(msg) {
    let box = document.getElementById("js-errors");
    if (!box) { box = document.createElement("pre"); box.id = "js-errors"; box.className = "js-errors"; document.body.prepend(box); }
    box.textContent += msg + "\n";
  }
  addEventListener("error", (e) => showError((e.message || e) + " @ " + (e.filename || "").split("/").pop() + ":" + e.lineno));
  addEventListener("unhandledrejection", (e) => showError("promise: " + (e.reason && e.reason.message || e.reason)));

  // ---------- chart definitions (one axis per chart; series colors fixed by slot) ----------
  const CHARTS = [
    { id: "altitude", title: "Altitude (relative)", unit: "m", series: [{ f: "altitude_m", label: "altitude" }], markers: true, dec: 1 },
    { id: "vspeed", title: "Vertical speed", unit: "m/s", series: [{ f: "vspeed_mps", label: "v" }], dec: 2 },
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
    { f: "altitude_m", label: "Altitude", unit: "m", dec: 1, hero: true },
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
  const MAX_SECONDS = 1800;

  // ---------- state ----------
  const cols = {};        // field -> array (parallel to cols.t_unix)
  let n = 0;
  let windowSec = 300;
  const charts = {};      // id -> {u, def, el}
  let latest = {};
  let markers = [];
  let lastSampleAt = 0;
  let dirty = false;
  let status = {};

  const $ = (s) => document.querySelector(s);
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const palette = () => [css("--s1"), css("--s2"), css("--s3")];
  const fmt = (v, dec) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : Number(v).toFixed(dec);

  // ---------- theme ----------
  function applyTheme(t) {
    if (t) document.documentElement.setAttribute("data-theme", t); else document.documentElement.removeAttribute("data-theme");
    try { if (t) localStorage.setItem("theme", t); else localStorage.removeItem("theme"); } catch (e) { }
    rebuildCharts();
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
    // trim
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

  function hasData(f) { const a = cols[f]; if (!a) return false; for (let i = a.length - 1; i >= Math.max(0, a.length - 200); i--) if (a[i] !== null && a[i] !== undefined) return true; return false; }

  function windowData(fields) {
    const t = cols.t_unix || [];
    const cutoff = Date.now() / 1000 - windowSec;
    let start = 0;
    while (start < t.length && t[start] < cutoff) start++;
    const out = [t.slice(start)];
    for (const f of fields) out.push((cols[f] || new Array(t.length).fill(null)).slice(start));
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
            html += `<div class="row"><span class="sw" style="background:${pal[i % pal.length]}"></span>${s.label}: <b>${fmt(v, def.dec)}</b> ${def.unit}</div>`;
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
    el.innerHTML = `<div class="chart-head"><span class="chart-title">${def.title}${def.unit ? " · " + def.unit : ""}</span><span class="chart-now" id="now-${def.id}">—</span></div><div class="plot"></div>`;
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
          values: (u, vals) => vals.map((v) => fmt(v, def.dec)) },
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
  }
  function redraw() {
    ensureCharts();
    for (const id of Object.keys(charts)) {
      const c = charts[id];
      c.u.setData(windowData(c.def.series.map((s) => s.f)));
      const v = latest[c.def.series[0].f];
      $("#now-" + id).textContent = fmt(v, c.def.dec) + (c.def.unit ? " " + c.def.unit : "");
    }
  }
  addEventListener("resize", () => { for (const id of Object.keys(charts)) { const c = charts[id]; c.u.setSize({ width: c.el.clientWidth - 16, height: 170 }); } });

  // ---------- tiles / chips / table ----------
  function renderTiles() {
    const box = $("#tiles");
    for (const t of TILES) {
      let el = document.getElementById("tile-" + t.f);
      const v = latest[t.f];
      if (v === undefined || v === null) { if (el) el.classList.add("hidden"); continue; }
      if (!el) {
        el = document.createElement("div"); el.id = "tile-" + t.f; el.className = "tile" + (t.hero ? " hero" : "");
        el.innerHTML = `<div class="label">${t.label}</div><div class="value"><span class="v"></span><small>${t.unit}</small><small class="x"></small></div>`;
        box.appendChild(el);
      }
      el.classList.remove("hidden");
      el.querySelector(".v").textContent = fmt(v, t.dec);
      if (t.extra) el.querySelector(".x").textContent = latest[t.extra] ? " " + latest[t.extra] : "";
    }
  }
  function renderChips() {
    $("#chip-samples").textContent = (status.samples || n) + " samples";
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
    tb.innerHTML = keys.map((k) => `<tr><td>${k}</td><td>${typeof latest[k] === "number" ? latest[k] : (latest[k] ?? "—")}</td></tr>`).join("");
  }

  function tick() {
    const alive = Date.now() - lastSampleAt < 3000;
    $("#conn-dot").className = "dot " + (alive ? "live" : "down");
    $("#conn-text").textContent = alive ? "live" : "no data";
    $("#conn-text").classList.toggle("bad", !alive);
    if (dirty) {
      dirty = false;
      redraw(); renderTiles(); renderChips();
      if ($("#values-table").closest("details").open) renderTable();
    }
  }
  setInterval(tick, 250);

  // ---------- SSE ----------
  function connect() {
    const es = new EventSource("/events");
    es.addEventListener("sample", (e) => pushSample(JSON.parse(e.data)));
    es.addEventListener("marker", (e) => { markers.push(JSON.parse(e.data)); dirty = true; });
    es.onerror = () => { /* EventSource reconnects on its own */ };
  }
  async function loadHistory() {
    try {
      const r = await fetch("/api/history?seconds=" + MAX_SECONDS);
      const j = await r.json();
      const c = j.columns || {};
      n = (c.t_unix || []).length;
      for (const k of Object.keys(c)) cols[k] = c[k].slice();
      if (n) { latest = {}; for (const k of Object.keys(c)) latest[k] = c[k][n - 1]; lastSampleAt = Date.now(); }
      dirty = true;
    } catch (e) { console.warn("history failed", e); }
  }
  async function pollStatus() {
    try {
      const r = await fetch("/api/status"); status = await r.json();
      $("#chip-session").textContent = "session " + (status.session || "—");
      markers = status.markers || markers;
      $("#servo-row").classList.toggle("hidden", !status.servo);
      $("#sensors-info").textContent = status.sim ? "SIMULATED sensors (BALLOON_SIM=1)" :
        "I2C: " + ((status.sensors || {}).i2c_addresses || []).join(", ") + " · detected: " +
        ((status.sensors || {}).sensors || []).map((s) => s.name).join(", ") +
        ((status.sensors || {}).errors || []).length ? " · errors: " + ((status.sensors || {}).errors || []).join("; ") : "";
      if (status.mosaic && mosaicVisible()) refreshMosaic();
    } catch (e) { }
  }
  async function pollSessions() {
    try {
      const r = await fetch("/api/sessions"); const list = await r.json();
      $("#sessions-table tbody").innerHTML = list.map((s) => `<tr><td>${s.name}${s.current ? " (current)" : ""}</td><td>${s.size_mb} MB</td><td>${s.video_segments}</td><td>${s.stills}</td><td><a href="${s.csv}" download>csv</a> · <a href="/data/sessions/${s.name}/">browse</a></td></tr>`).join("");
    } catch (e) { }
  }

  // ---------- camera ----------
  const cam = $("#cam");
  function camUrl() { return `${location.protocol}//${location.hostname}:${status.camera_port || 8081}/stream?t=${Date.now()}`; }
  function startCam() { $("#cam-overlay").classList.remove("hidden"); cam.src = camUrl(); }
  cam.onload = () => $("#cam-overlay").classList.add("hidden");
  cam.onerror = () => { $("#cam-overlay").classList.remove("hidden"); setTimeout(startCam, 3000); };
  const mosaicVisible = () => !$("#view-mosaic").classList.contains("hidden");
  function refreshMosaic() { $("#mosaic").src = "/mosaic.jpg?t=" + Date.now(); }
  $("#mosaic").onload = () => $("#mosaic-overlay").classList.add("hidden");
  $("#mosaic").onerror = () => $("#mosaic-overlay").classList.remove("hidden");
  setInterval(() => { if (mosaicVisible()) refreshMosaic(); }, 5000);
  document.querySelectorAll(".tab").forEach((b) => b.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
    const live = b.dataset.view === "live";
    $("#view-live").classList.toggle("hidden", !live); $("#view-mosaic").classList.toggle("hidden", live);
    if (live) startCam(); else { cam.src = ""; refreshMosaic(); }   // stop pulling the stream while on the map
  });

  // ---------- controls ----------
  $("#window-seg").querySelectorAll("button").forEach((b) => b.onclick = () => {
    windowSec = +b.dataset.win; $("#window-seg").querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b)); dirty = true;
  });
  $("#btn-mark").onclick = async () => {
    const note = $("#mark-note").value.trim() || "mark";
    await fetch("/api/mark", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note }) });
    $("#mark-note").value = "";
  };
  $("#btn-zero").onclick = () => fetch("/api/zero", { method: "POST" });
  const servo = $("#servo");
  let servoTimer = null;
  servo.oninput = () => { $("#servo-val").textContent = servo.value + "°"; clearTimeout(servoTimer);
    servoTimer = setTimeout(() => fetch("/api/servo", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ angle: +servo.value }) }), 80); };
  $("#values-table").closest("details").addEventListener("toggle", renderTable);

  // ---------- boot ----------
  (async () => {
    await pollStatus();
    await loadHistory();
    connect();
    startCam();
    pollSessions();
    setInterval(pollStatus, 5000);
    setInterval(pollSessions, 30000);
  })();
})();
