"""Read-only HTML/JSON helpers for the Raspberry Pi system health page."""

from __future__ import annotations

from system_health import collect_snapshot, load_history, load_snapshot, record_history, write_snapshot


def collect_system_payload() -> dict:
    """Collect a fresh snapshot and return it with the rolling chart history."""
    try:
        snapshot = collect_snapshot()
        write_snapshot(snapshot)
        history = record_history(snapshot)
        return {"snapshot": snapshot, "history": history, "stale": False}
    except Exception:
        snapshot = load_snapshot()
        if snapshot is None:
            raise
        return {"snapshot": snapshot, "history": load_history(), "stale": True}


def system_page() -> bytes:
    """Return the standalone /system page; no external JS/CSS dependencies."""
    page = r'''<!doctype html>
<html lang="fi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#ffffff">
  <title>Family Display · System</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; background: #fff; color: #111; font-family: Arial, Helvetica, sans-serif; }
    main { width: min(960px, 100%); margin: 0 auto; padding: 18px 20px 36px; }
    header {
      display: flex; align-items: center; justify-content: space-between; gap: 16px;
      border-bottom: 2px solid #111; padding-bottom: 12px; margin-bottom: 16px;
    }
    h1 { margin: 0; font-size: 28px; }
    a { color: #111; font-weight: 700; text-decoration: none; }
    #status-line { display: flex; align-items: baseline; gap: 12px; margin-bottom: 14px; }
    #overall {
      border: 2px solid #111; border-radius: 18px; padding: 5px 12px;
      font-weight: 800; letter-spacing: .04em;
    }
    #stale { color: #666; font-size: 13px; }
    .metrics {
      display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px; margin-bottom: 18px;
    }
    .metric { border: 1px solid #777; border-radius: 8px; padding: 10px 12px; min-height: 76px; }
    .metric .label { color: #555; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
    .metric .value { margin-top: 5px; font-size: 21px; font-weight: 700; overflow-wrap: anywhere; }
    #issues { border-top: 1px solid #aaa; border-bottom: 1px solid #aaa; padding: 10px 0; margin-bottom: 18px; }
    #issues.ok { color: #444; }
    #issues ul { margin: 6px 0 0 20px; padding: 0; }
    .charts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
    .chart-card { border: 1px solid #999; border-radius: 8px; padding: 10px; min-width: 0; }
    .chart-card h2 { margin: 0 0 4px; font-size: 15px; }
    .chart-card .range { color: #666; font-size: 11px; margin-bottom: 5px; }
    canvas { width: 100%; height: 120px; display: block; }
    footer { margin-top: 16px; color: #666; font-size: 12px; }
    @media (max-width: 720px) {
      main { padding: 12px; }
      h1 { font-size: 22px; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .charts { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
<main>
  <header>
    <h1>Raspberry Pi Health</h1>
    <a href="/" target="_top">← Perheen näyttö</a>
  </header>

  <div id="status-line">
    <span id="overall">LOADING</span><span id="last-check"></span><span id="stale"></span>
  </div>

  <section class="metrics">
    <div class="metric"><div class="label">Temperature</div><div class="value" id="temperature">–</div></div>
    <div class="metric"><div class="label">CPU load · 1 min</div><div class="value" id="cpu">–</div></div>
    <div class="metric"><div class="label">RAM used</div><div class="value" id="memory">–</div></div>
    <div class="metric"><div class="label">Disk used</div><div class="value" id="disk">–</div></div>
    <div class="metric"><div class="label">Uptime</div><div class="value" id="uptime">–</div></div>
    <div class="metric"><div class="label">Throttling</div><div class="value" id="throttled">–</div></div>
    <div class="metric"><div class="label">Dashboard service</div><div class="value" id="service">–</div></div>
    <div class="metric"><div class="label">Web dashboard</div><div class="value" id="web">–</div></div>
    <div class="metric"><div class="label">Internet</div><div class="value" id="internet">–</div></div>
  </section>

  <section id="issues" class="ok">Ladataan tilaa…</section>

  <section class="charts">
    <div class="chart-card"><h2>Lämpötila · 24 h</h2><div class="range" id="temperature-range"></div><canvas id="temperature-chart"></canvas></div>
    <div class="chart-card"><h2>RAM · 24 h</h2><div class="range" id="memory-range"></div><canvas id="memory-chart"></canvas></div>
    <div class="chart-card"><h2>Levy · 24 h</h2><div class="range" id="disk-range"></div><canvas id="disk-chart"></canvas></div>
  </section>

  <footer>
    Sivun ollessa auki tarkistus tehdään viiden minuutin välein. Jatkuva taustakeräys lisätään myöhemmin erillisellä systemd-timerilla.
  </footer>
</main>
<script>
  const byId = (id) => document.getElementById(id);
  const value = (v, suffix = "") => (v === null || v === undefined ? "–" : `${v}${suffix}`);

  function formatUptime(seconds) {
    if (seconds === null || seconds === undefined) return "–";
    let remaining = Math.max(0, Number(seconds));
    const days = Math.floor(remaining / 86400); remaining %= 86400;
    const hours = Math.floor(remaining / 3600);
    const minutes = Math.floor((remaining % 3600) / 60);
    const parts = [];
    if (days) parts.push(`${days} d`);
    if (hours || days) parts.push(`${hours} h`);
    parts.push(`${minutes} min`);
    return parts.join(" ");
  }

  function formatCheck(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    return `Tarkistettu ${date.toLocaleTimeString("fi-FI", {hour: "2-digit", minute: "2-digit"})}`;
  }

  function drawChart(canvasId, rangeId, points, key, suffix) {
    const canvas = byId(canvasId);
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(240, Math.round(rect.width));
    const height = 120;
    const scale = window.devicePixelRatio || 1;
    canvas.width = width * scale; canvas.height = height * scale;
    const ctx = canvas.getContext("2d");
    ctx.scale(scale, scale); ctx.clearRect(0, 0, width, height);

    const samples = points
      .map((point) => ({time: new Date(point.checked_at).getTime(), value: Number(point[key])}))
      .filter((sample) => Number.isFinite(sample.time) && Number.isFinite(sample.value));

    if (!samples.length) {
      byId(rangeId).textContent = "Ei historiatietoa vielä";
      ctx.fillStyle = "#777"; ctx.font = "12px Arial";
      ctx.fillText("Historia kertyy tarkistuksista", 8, 24);
      return;
    }

    let minValue = Math.min(...samples.map((sample) => sample.value));
    let maxValue = Math.max(...samples.map((sample) => sample.value));
    if (minValue === maxValue) { minValue -= 1; maxValue += 1; }
    const padding = Math.max(1, (maxValue - minValue) * 0.15);
    minValue -= padding; maxValue += padding;

    const minTime = samples[0].time;
    const maxTime = samples[samples.length - 1].time;
    const timeSpan = Math.max(1, maxTime - minTime);
    const left = 8, right = width - 8, top = 8, bottom = height - 18;

    ctx.strokeStyle = "#ddd"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(left, bottom); ctx.lineTo(right, bottom); ctx.stroke();

    ctx.strokeStyle = "#111"; ctx.lineWidth = 2; ctx.beginPath();
    samples.forEach((sample, index) => {
      const x = left + ((sample.time - minTime) / timeSpan) * (right - left);
      const y = bottom - ((sample.value - minValue) / (maxValue - minValue)) * (bottom - top);
      if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();

    const values = samples.map((sample) => sample.value);
    byId(rangeId).textContent = `${Math.min(...values).toFixed(1)}${suffix} – ${Math.max(...values).toFixed(1)}${suffix} · ${samples.length} pistettä`;
  }

  function render(data) {
    const snapshot = data.snapshot || {};
    const history = Array.isArray(data.history) ? data.history : [];
    byId("overall").textContent = String(snapshot.status || "unknown").toUpperCase();
    byId("last-check").textContent = formatCheck(snapshot.checked_at);
    byId("stale").textContent = data.stale ? "(viimeisin tallennettu tieto)" : "";
    byId("temperature").textContent = value(snapshot.temperature_c, " °C");
    byId("cpu").textContent = value(snapshot.cpu_load_1m);
    byId("memory").textContent = value(snapshot.memory_percent, " %");
    byId("disk").textContent = value(snapshot.disk_percent, " %");
    byId("uptime").textContent = formatUptime(snapshot.uptime_seconds);
    byId("throttled").textContent = snapshot.throttled || "–";
    byId("service").textContent = snapshot.dashboard_service || "–";
    byId("web").textContent = String(snapshot.web_dashboard || "–").toUpperCase();
    byId("internet").textContent = String(snapshot.internet || "–").toUpperCase();

    const issues = Array.isArray(snapshot.issues) ? snapshot.issues : [];
    const issuesBox = byId("issues");
    if (!issues.length) {
      issuesBox.className = "ok"; issuesBox.textContent = "Ei havaittuja ongelmia.";
    } else {
      issuesBox.className = ""; issuesBox.replaceChildren();
      const title = document.createElement("strong"); title.textContent = "Havaitut ongelmat";
      const list = document.createElement("ul");
      issues.forEach((issue) => {
        const item = document.createElement("li");
        item.textContent = `${String(issue.severity || "").toUpperCase()}: ${issue.message || issue.code || ""}`;
        list.appendChild(item);
      });
      issuesBox.appendChild(title); issuesBox.appendChild(list);
    }

    drawChart("temperature-chart", "temperature-range", history, "temperature_c", " °C");
    drawChart("memory-chart", "memory-range", history, "memory_percent", " %");
    drawChart("disk-chart", "disk-range", history, "disk_percent", " %");
  }

  async function refresh() {
    try {
      const response = await fetch(`/system-health.json?v=${Date.now()}`, {cache: "no-store"});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      render(data);
    } catch (error) {
      byId("overall").textContent = "ERROR";
      byId("issues").textContent = "Systeemitietoja ei saatu ladattua.";
      console.error(error);
    }
  }

  let touchStartX = null;
  let touchStartY = null;
  document.addEventListener("touchstart", (event) => {
    if (event.touches.length !== 1) return;
    touchStartX = event.touches[0].clientX;
    touchStartY = event.touches[0].clientY;
  }, {passive: true});
  document.addEventListener("touchend", (event) => {
    if (touchStartX === null || touchStartY === null || !event.changedTouches.length) return;
    const dx = event.changedTouches[0].clientX - touchStartX;
    const dy = event.changedTouches[0].clientY - touchStartY;
    touchStartX = null; touchStartY = null;
    if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 1.25 || dx >= 0) return;
    if (window.parent !== window) {
      window.parent.postMessage({type: "family-display-system-swipe-left"}, window.location.origin);
    } else {
      window.location.href = "/";
    }
  }, {passive: true});

  refresh();
  setInterval(refresh, 5 * 60 * 1000);
  window.addEventListener("resize", () => refresh());
</script>
</body>
</html>
'''
    return page.encode("utf-8")
