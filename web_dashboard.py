#!/usr/bin/env python3
"""Serve the family dashboard as an auto-refreshing tablet web app.

The primary view is still the existing 960x680 dashboard PNG used by the
future e-paper output. The tablet shell adds browser-only views for Raspberry Pi health,
a monthly calendar and full school reminders.
"""

import argparse
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

Path("cache").mkdir(exist_ok=True)

from data.calendar_month import fetch_month  # noqa: E402
from data.hsl import drop_past_departures  # noqa: E402
from main import MODULES, _render_dashboard, feature_enabled, fetch_module, load_config  # noqa: E402
from school_summary_page import school_payload
from system_health_page import collect_system_payload, system_page  # noqa: E402

log = logging.getLogger("dashboard.web")
OUTPUT_PATH = Path("output/dashboard.png")


def _web_mvp_config(config: dict) -> dict:
    """Use shorter cache windows for the always-visible tablet output."""
    tuned = dict(config)
    cache_cfg = dict(config.get("cache") or {})

    def _cap_minutes(key: str, maximum: int):
        try:
            current = int(cache_cfg.get(key, maximum))
        except (TypeError, ValueError):
            current = maximum
        cache_cfg[key] = min(current, maximum)

    _cap_minutes("ttl_minutes", 5)
    _cap_minutes("hsl_ttl_minutes", 1)
    tuned["cache"] = cache_cfg
    return tuned


def render_once(config_path: str, use_cache: bool = True) -> Path:
    """Fetch enabled data, render the dashboard, and atomically replace the PNG."""
    config = _web_mvp_config(load_config(config_path))
    display_cfg = config.get("display", {})
    width = int(display_cfg.get("width", 960))
    height = int(display_cfg.get("height", 680))

    log.info("Web MVP: fetching data...")
    data = {
        name: fetch_module(name, config, use_cache) if feature_enabled(config, name) else None
        for name in MODULES
    }
    if data.get("hsl"):
        data["hsl"] = drop_past_departures(data["hsl"])

    log.info("Web MVP: rendering %sx%s image...", width, height)
    image = _render_dashboard(config, data, width, height)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = OUTPUT_PATH.with_name(f"{OUTPUT_PATH.stem}.tmp{OUTPUT_PATH.suffix}")
    image.save(temp_path)
    temp_path.replace(OUTPUT_PATH)
    log.info("Web MVP: image updated: %s", OUTPUT_PATH.resolve())
    return OUTPUT_PATH


class DashboardState:
    def __init__(self):
        self.last_success = None
        self.last_error = None


def _render_loop(stop_event, state, config_path, refresh_seconds, use_cache):
    while not stop_event.wait(refresh_seconds):
        try:
            render_once(config_path, use_cache=use_cache)
            state.last_success = time.time()
            state.last_error = None
        except Exception as exc:
            state.last_error = str(exc)
            log.exception("Web MVP refresh failed")


def _page(refresh_seconds: int) -> bytes:
    browser_refresh_ms = max(10, min(refresh_seconds, 60)) * 1000
    page = r'''<!doctype html>
<html lang="fi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#ffffff">
  <title>Perheen näyttö</title>
  <style>
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: #fff;
      color: #000;
      font-family: Arial, Helvetica, sans-serif;
    }
    #track {
      display: flex;
      width: 400vw;
      height: 100vh;
      transform: translateX(-100vw);
      transition: transform 180ms ease-out;
    }
    .page {
      flex: 0 0 100vw;
      width: 100vw;
      height: 100vh;
      background: #fff;
    }
    #system-page, #dashboard-page, #month-page { overflow: hidden; }
    #system-frame {
      width: 100%;
      height: 100%;
      border: 0;
      display: block;
      background: #fff;
    }
    #dashboard-page {
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    #dashboard {
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
      user-select: none;
      -webkit-user-drag: none;
    }
    #month-page {
      display: flex;
      flex-direction: column;
    }
    .month-header {
      flex: 0 0 58px;
      display: grid;
      grid-template-columns: 56px 1fr 56px;
      align-items: center;
      border-bottom: 2px solid #000;
      padding: 0 8px;
      background: #fff;
      position: relative;
      z-index: 3;
    }
    .month-header h1 {
      margin: 0;
      text-align: center;
      font-size: 24px;
      line-height: 1;
      letter-spacing: .02em;
    }
    .month-nav {
      appearance: none;
      border: 0;
      background: transparent;
      color: #000;
      font-size: 38px;
      line-height: 1;
      height: 52px;
      padding: 0;
      cursor: pointer;
    }
    #month-scroll {
      flex: 1 1 auto;
      min-height: 0;
      overflow: auto;
      -webkit-overflow-scrolling: touch;
      touch-action: pan-y;
      background: #fff;
    }
    #month-status { padding: 16px; font-size: 16px; }
    #month-table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      background: #fff;
    }
    #month-table th, #month-table td {
      border-right: 1px solid #777;
      border-bottom: 1px solid #aaa;
      vertical-align: top;
      padding: 6px 7px;
      overflow-wrap: anywhere;
    }
    #month-table th:last-child, #month-table td:last-child { border-right: 0; }
    #month-table thead th {
      position: sticky;
      top: 0;
      z-index: 2;
      background: #fff;
      border-bottom: 2px solid #000;
      font-size: 14px;
      text-align: left;
      min-height: 36px;
    }
    #month-table .day-column { width: 86px; }
    #month-table tbody th {
      font-size: 14px;
      text-align: left;
      background: #fff;
      font-weight: 700;
    }
    #month-table tbody tr.today th,
    #month-table tbody tr.today td {
      border-top: 2px solid #000;
      border-bottom: 2px solid #000;
    }
    .event { margin: 0 0 5px; font-size: 13px; line-height: 1.22; }
    .event:last-child { margin-bottom: 0; }
    .event-time { font-weight: 700; }
    .swipe-hint {
      position: fixed;
      left: 50%;
      bottom: max(8px, env(safe-area-inset-bottom));
      transform: translateX(-50%);
      background: rgba(255,255,255,.88);
      border: 1px solid #aaa;
      border-radius: 14px;
      padding: 4px 10px;
      font-size: 11px;
      color: #555;
      pointer-events: none;
      opacity: 0;
      transition: opacity 180ms ease-out;
      z-index: 5;
    }
    #track.month-visible ~ #month-hint { opacity: 1; }
    #track.system-visible ~ #system-hint { opacity: 1; }
    @media (max-width: 800px) {
      .month-header h1 { font-size: 20px; }
      #month-table .day-column { width: 72px; }
      #month-table th, #month-table td { padding: 5px; }
      #month-table thead th, #month-table tbody th { font-size: 12px; }
      .event { font-size: 12px; }
    }
    #school-page { display: flex; flex-direction: column; overflow: hidden; }
    #school-header { display: flex; gap: 16px; align-items: center; padding: 12px 20px;
      border-bottom: 2px solid #000; flex-wrap: wrap; }
    #school-header h1 { margin: 0; font-size: 24px; flex: 1; }
    .school-button { background: white; color: black; border: 1px solid black;
      border-radius: 4px; padding: 10px 14px; font-size: 16px; cursor: pointer; }
    #school-scroll { flex: 1; min-height: 0; overflow-y: auto; touch-action: pan-y;
      -webkit-overflow-scrolling: touch; padding: 16px 20px 48px; }
    #school-status { margin: 0 0 16px; font-size: 16px; line-height: 1.4; }
    .school-group-children { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; }
    .school-group > h2 { margin: 24px 0 16px; border-bottom: 3px solid; padding-bottom: 8px; font-size: 27px; }
    .school-child h2 { margin: 0 0 12px; font-size: 25px; border-bottom: 2px solid; padding-bottom: 8px; }
    .school-card { border: 1px solid #aaa; border-radius: 6px; padding: 14px; margin-bottom: 12px;
      overflow-wrap: anywhere; font-size: 18px; line-height: 1.4; }
    .school-card h3 { font-size: 19px; margin: 6px 0; }
    .school-card ul { padding-left: 22px; margin: 8px 0; }
    .school-card li + li { margin-top: 6px; }
    .school-card details { font-size: 15px; margin-top: 12px; }
    .school-card summary { cursor: pointer; padding: 4px 0; }
    .school-card blockquote { margin: 8px 0 0; white-space: pre-wrap; }
    .school-review-label { font-size: 18px; margin: 22px 0 10px; }
    .dashboard-canvas { position: relative; width: min(100vw, 141.17647vh); height: min(100vh, 70.83333vw); }
    #school-open { position: absolute; left: 58.4%; top: 66.5%; width: 41.6%; height: 10%;
      border: 0; background: transparent; cursor: pointer; }
    #school-open:focus-visible { outline: 3px solid black; outline-offset: -3px; }
    #school-link { display: block; padding: 8px; text-align: right; color: black; font-size: 16px; }
    @media (max-width: 600px) { .school-group-children { grid-template-columns: 1fr; }
      #school-header { gap: 8px; padding: 10px; } #school-header h1 { font-size: 21px; } }
  </style>
</head>
<body>
  <div id="track">
    <section id="system-page" class="page" aria-label="Raspberry Pi Health">
      <iframe id="system-frame" src="/system" title="Raspberry Pi Health"></iframe>
    </section>

    <section id="dashboard-page" class="page" aria-label="Perheen näyttö">
      <div class="dashboard-canvas">
      <img id="dashboard" src="/dashboard.png?v=0" alt="Perheen näyttö">
      <button id="school-open" type="button" aria-label="Avaa kaikki koulumuistutukset" title="Avaa kaikki koulumuistutukset"></button>
      </div>
    </section>

    <section id="month-page" class="page" aria-label="Kuukausikalenteri">
      <header class="month-header">
        <button id="prev-month" class="month-nav" type="button" aria-label="Edellinen kuukausi">‹</button>
        <h1 id="month-title">Kuukausikalenteri</h1>
        <button id="next-month" class="month-nav" type="button" aria-label="Seuraava kuukausi">›</button>
      </header>
      <a id="school-link" href="/school">Koulumuistutukset →</a>
      <div id="month-scroll">
        <div id="month-status">Ladataan kalenteria…</div>
        <table id="month-table" hidden><thead></thead><tbody></tbody></table>
      </div>
    </section>
    <section id="school-page" class="page" aria-label="Koulumuistutukset">
      <header id="school-header">
        <button id="school-back" class="school-button" type="button">‹ Kalenteri</button>
        <h1>Koulusta muistettavaa</h1>
        <button id="school-home" class="school-button" type="button">Etusivu</button>
      </header>
      <div id="school-scroll">
        <p id="school-status" role="status">Ladataan muistutuksia…</p>
        <div id="school-children"></div>
      </div>
    </section>
  </div>
  <div id="system-hint" class="swipe-hint">Pyyhkäise vasemmalle takaisin</div>
  <div id="month-hint" class="swipe-hint">Pyyhkäise oikealle takaisin</div>

  <script>
    const image = document.getElementById("dashboard");
    const track = document.getElementById("track");
    const monthTitle = document.getElementById("month-title");
    const monthStatus = document.getElementById("month-status");
    const monthTable = document.getElementById("month-table");
    const monthHead = monthTable.querySelector("thead");
    const monthBody = monthTable.querySelector("tbody");
    const monthScroll = document.getElementById("month-scroll");
    const MONTHS_FI = [
      "Tammikuu", "Helmikuu", "Maaliskuu", "Huhtikuu", "Toukokuu", "Kesäkuu",
      "Heinäkuu", "Elokuu", "Syyskuu", "Lokakuu", "Marraskuu", "Joulukuu"
    ];
    const DAYS_FI = ["Su", "Ma", "Ti", "Ke", "To", "Pe", "La"];

    let activeView = "dashboard";
    const now = new Date();
    let shownYear = now.getFullYear();
    let shownMonth = now.getMonth() + 1;
    let loadedKey = "";
    let touchStartX = null;
    let touchStartY = null;

    function showView(view) {
      activeView = view;
      track.classList.remove("system-visible", "month-visible");
      if (view === "system") {
        track.style.transform = "translateX(0)";
        track.classList.add("system-visible");
      } else if (view === "school") {
        track.style.transform = "translateX(-300vw)";
        loadSchool();
      } else if (view === "month") {
        track.style.transform = "translateX(-200vw)";
        track.classList.add("month-visible");
        loadMonth();
      } else {
        track.style.transform = "translateX(-100vw)";
      }
    }

    function schoolElement(tag, text, className) {
      const el = document.createElement(tag);
      if (text !== undefined) el.textContent = text;
      if (className) el.className = className;
      return el;
    }
    function schoolDate(value) {
      if (!value) return "";
      const parsed = new Date(value + "T12:00:00");
      return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString("fi-FI", {
        weekday: "short", day: "numeric", month: "numeric", year: "numeric"
      });
    }
    let schoolLoading = false;
    async function loadSchool() {
      if (schoolLoading) return;
      schoolLoading = true;
      const status = document.getElementById("school-status");
      const container = document.getElementById("school-children");
      try {
        const response = await fetch("/school-reminders.json?v=" + Date.now(), {cache: "no-store"});
        if (!response.ok) throw new Error("fetch failed");
        const data = await response.json();
        if (!Array.isArray(data.items)) throw new Error("invalid response");
        const updated = data.schoolwork_fetched_at ? new Date(data.schoolwork_fetched_at).toLocaleString("fi-FI") : "";
        status.textContent = updated ? "Wilma-tiedot päivitetty " + updated + ". Haku päivittäin klo 12, 13, 14 ja 15." :
          "Läksyjä, kokeita ja merkintöjä ei ole vielä saatu haettua.";
        if (data.schoolwork_stale && updated) status.textContent += " Wilma-haku on viivästynyt tai epäonnistunut – näytetään viimeksi haetut tiedot.";
        if (data.fetched_at) status.textContent += " Viestitiivistelmä: " + new Date(data.fetched_at).toLocaleString("fi-FI") + ".";
        if (data.stale) status.textContent += " Viestitiivistelmän päivitys on viivästynyt.";
        container.replaceChildren();
        const names = [...new Set(["Neve", "Sera", ...data.items.map(item => item.student)])];
        const advice = schoolElement("section", undefined, "school-group");
        advice.appendChild(schoolElement("h2", "Suositukset seuraaville kahdelle päivälle"));
        if (data.recommendations_start && data.recommendations_end) {
          advice.appendChild(schoolElement("p", schoolDate(data.recommendations_start) + " – " + schoolDate(data.recommendations_end)));
        }
        if (data.recommendations_stale && (data.recommendations || []).length) {
          advice.appendChild(schoolElement("p", "Suositusten päivitys on viivästynyt – tarkista yllä oleva ajanjakso."));
        }
        const adviceColumns = schoolElement("div", undefined, "school-group-children");
        for (const name of ["Neve", "Sera"]) {
          const card = schoolElement("article", undefined, "school-card");
          card.appendChild(schoolElement("h3", name));
          const childAdvice = (data.recommendations || []).find(item => item.student === name);
          card.appendChild(schoolElement("p", childAdvice ? childAdvice.sentences.join(" ") : "Suositusta ei ole vielä saatavilla."));
          adviceColumns.appendChild(card);
        }
        advice.appendChild(adviceColumns);
        container.appendChild(advice);
        for (const [key, label] of [["schoolwork", "Läksyt ja kokeet"], ["notes", "Merkinnät"], ["other", "Muut"]]) {
          const group = schoolElement("section", undefined, "school-group");
          group.appendChild(schoolElement("h2", label));
          if (key === "schoolwork") group.appendChild(schoolElement("p", "Läksyt viimeiseltä 14 päivältä ja tulevat kokeet. Annettu-päivä ei ole palautuspäivä. Wilma ei kerro, onko läksy jo tehty."));
          if (key === "notes") group.appendChild(schoolElement("p", "Tuntimerkinnät viimeiseltä 28 päivältä, uusimmat ensin."));
          const columns = schoolElement("div", undefined, "school-group-children");
        for (const name of names) {
          const section = schoolElement("section", undefined, "school-child");
          section.appendChild(schoolElement("h2", name));
          const items = data.items.filter(item => item.student === name && item.category === key).sort((a, b) =>
            Number(a.date_unknown) - Number(b.date_unknown) ||
            ((key === "notes" || (a.kind === "homework" && b.kind === "homework")) ?
              (b.date || "").localeCompare(a.date || "") : (a.date || "").localeCompare(b.date || "")));
          if (!items.length) section.appendChild(schoolElement("p", key !== "other" && !data.schoolwork_fetched_at ? "Tietoja ei vielä saatavilla." : "Ei ajankohtaisia muistutuksia."));
          let reviewHeading = false;
          for (const item of items) {
            if (item.date_unknown && !reviewHeading) {
              section.appendChild(schoolElement("h3", "Tarkistettavaa / ilman määräpäivää", "school-review-label"));
              reviewHeading = true;
            }
            const card = schoolElement("article", undefined, "school-card");
            if (!item.date_unknown) {
              let when = (item.date_label ? item.date_label + " · " : "") + schoolDate(item.date);
              if (item.end_date && item.end_date !== item.date) when += " – " + schoolDate(item.end_date);
              card.appendChild(schoolElement("strong", when));
            }
            card.appendChild(schoolElement("h3", (item.kind === "homework" ? "Läksy · " : "") + item.title));
            if (item.needs_review && !item.date_unknown) card.appendChild(schoolElement("p", "Tarkista tiedot alkuperäisestä viestistä."));
            if (item.remember.length) {
              const list = schoolElement("ul");
              for (const text of item.remember) list.appendChild(schoolElement("li", text));
              card.appendChild(list);
            }
            if (item.evidence) {
              const details = schoolElement("details");
              details.appendChild(schoolElement("summary", "Katkelma Wilma-viestistä"));
              details.appendChild(schoolElement("blockquote", item.evidence));
              card.appendChild(details);
            }
            section.appendChild(card);
          }
          columns.appendChild(section);
        }
          group.appendChild(columns);
          container.appendChild(group);
        }
      } catch (error) {
        status.textContent = "Koulumuistutuksia ei saatu ladattua. Yritetään uudelleen hetken kuluttua.";
      } finally { schoolLoading = false; }
    }
    document.getElementById("school-open").addEventListener("click", () => showView("school"));
    document.getElementById("school-link").addEventListener("click", event => {
      event.preventDefault(); showView("school");
    });
    document.getElementById("school-back").addEventListener("click", () => showView("month"));
    document.getElementById("school-home").addEventListener("click", () => showView("dashboard"));
    if (window.location.pathname === "/school") showView("school");

    function isoDate(year, month, day) {
      return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    }
    function daysInMonth(year, month) { return new Date(year, month, 0).getDate(); }

    function eventText(event) {
      if (event.all_day || !event.time) return event.title || "(ei otsikkoa)";
      let timing = event.time;
      if (event.end_time && event.end_time.length >= 16) {
        const end = event.end_time.slice(11, 16);
        if (end && end !== event.time) timing += `–${end}`;
      }
      return `${timing} ${event.title || "(ei otsikkoa)"}`;
    }

    function renderMonth(data) {
      const names = Array.isArray(data.calendar_names) ? data.calendar_names : [];
      const events = Array.isArray(data.events) ? data.events : [];
      monthTitle.textContent = `${MONTHS_FI[shownMonth - 1]} ${shownYear}`;
      monthHead.replaceChildren();
      monthBody.replaceChildren();

      const headerRow = document.createElement("tr");
      const dayHeader = document.createElement("th");
      dayHeader.className = "day-column";
      dayHeader.textContent = "Päivä";
      headerRow.appendChild(dayHeader);
      names.forEach((name) => {
        const th = document.createElement("th");
        th.textContent = name;
        headerRow.appendChild(th);
      });
      monthHead.appendChild(headerRow);

      const grouped = new Map();
      events.forEach((event) => {
        const key = `${event.date}\n${event.calendar || ""}`;
        if (!grouped.has(key)) grouped.set(key, []);
        grouped.get(key).push(event);
      });

      const todayIso = isoDate(now.getFullYear(), now.getMonth() + 1, now.getDate());
      const count = daysInMonth(shownYear, shownMonth);
      for (let day = 1; day <= count; day += 1) {
        const row = document.createElement("tr");
        const dateIso = isoDate(shownYear, shownMonth, day);
        if (dateIso === todayIso) row.classList.add("today");

        const dayCell = document.createElement("th");
        const weekday = DAYS_FI[new Date(shownYear, shownMonth - 1, day).getDay()];
        dayCell.textContent = `${weekday} ${day}.${shownMonth}.`;
        row.appendChild(dayCell);

        names.forEach((name) => {
          const cell = document.createElement("td");
          const dayEvents = grouped.get(`${dateIso}\n${name}`) || [];
          dayEvents.forEach((event) => {
            const div = document.createElement("div");
            div.className = "event";
            const text = eventText(event);
            if (!event.all_day && event.time) {
              const firstSpace = text.indexOf(" ");
              if (firstSpace > 0) {
                const timeSpan = document.createElement("span");
                timeSpan.className = "event-time";
                timeSpan.textContent = text.slice(0, firstSpace);
                div.appendChild(timeSpan);
                div.appendChild(document.createTextNode(text.slice(firstSpace)));
              } else {
                div.textContent = text;
              }
            } else {
              div.textContent = text;
            }
            cell.appendChild(div);
          });
          row.appendChild(cell);
        });
        monthBody.appendChild(row);
      }

      monthStatus.hidden = true;
      monthTable.hidden = false;
      loadedKey = `${shownYear}-${shownMonth}`;
      if (data._stale) {
        monthStatus.textContent = "Kalenteriyhteys ei vastannut – näytetään viimeksi ladattu kuukausi.";
        monthStatus.hidden = false;
      }
    }

    async function loadMonth(force = false) {
      const key = `${shownYear}-${shownMonth}`;
      if (!force && loadedKey === key) return;
      monthTitle.textContent = `${MONTHS_FI[shownMonth - 1]} ${shownYear}`;
      monthStatus.hidden = false;
      monthStatus.textContent = "Ladataan kalenteria…";
      monthTable.hidden = true;
      try {
        const response = await fetch(
          `/calendar-month.json?year=${shownYear}&month=${shownMonth}&v=${Date.now()}`,
          {cache: "no-store"}
        );
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
        renderMonth(data);
      } catch (error) {
        monthStatus.hidden = false;
        monthStatus.textContent = "Kuukausikalenteria ei saatu ladattua.";
        monthTable.hidden = true;
        console.error(error);
      }
    }

    function shiftMonth(delta) {
      shownMonth += delta;
      if (shownMonth < 1) { shownMonth = 12; shownYear -= 1; }
      if (shownMonth > 12) { shownMonth = 1; shownYear += 1; }
      loadedKey = "";
      monthScroll.scrollTop = 0;
      loadMonth(true);
    }

    document.getElementById("prev-month").addEventListener("click", () => shiftMonth(-1));
    document.getElementById("next-month").addEventListener("click", () => shiftMonth(1));

    document.addEventListener("touchstart", (event) => {
      if (event.touches.length !== 1) return;
      touchStartX = event.touches[0].clientX;
      touchStartY = event.touches[0].clientY;
    }, {passive: true});

    document.addEventListener("touchend", (event) => {
      if (touchStartX === null || touchStartY === null || !event.changedTouches.length) return;
      const dx = event.changedTouches[0].clientX - touchStartX;
      const dy = event.changedTouches[0].clientY - touchStartY;
      touchStartX = null;
      touchStartY = null;
      if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 1.25) return;

      if (activeView === "dashboard" && dx > 0) showView("system");
      else if (activeView === "dashboard" && dx < 0) showView("month");
      else if (activeView === "month" && dx > 0) showView("dashboard");
      else if (activeView === "month" && dx < 0) showView("school");
      else if (activeView === "school" && dx > 0) showView("month");
    }, {passive: true});

    window.addEventListener("message", (event) => {
      if (event.origin !== window.location.origin) return;
      if (event.data && event.data.type === "family-display-system-swipe-left") {
        showView("dashboard");
      }
    });

    setInterval(() => {
      image.src = "/dashboard.png?v=" + Date.now();
      if (activeView === "school") loadSchool();
    }, __BROWSER_REFRESH_MS__);

    setInterval(() => {
      if (activeView === "month") {
        loadedKey = "";
        loadMonth(true);
      }
    }, 5 * 60 * 1000);
  </script>
</body>
</html>
'''
    return page.replace("__BROWSER_REFRESH_MS__", str(browser_refresh_ms)).encode("utf-8")


def make_handler(state, refresh_seconds, config_path, use_cache):
    class DashboardHandler(BaseHTTPRequestHandler):
        def _no_cache_headers(self):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")

        def _send_json(self, status: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._no_cache_headers()
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path

            if path in {"/", "/school"}:
                body = _page(refresh_seconds)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._no_cache_headers()
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/system":
                body = system_page()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._no_cache_headers()
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/system-health.json":
                try:
                    self._send_json(200, collect_system_payload())
                except Exception as exc:
                    log.exception("System health collection failed")
                    self._send_json(503, {"error": str(exc)})
                return

            if path == "/school-reminders.json":
                try:
                    self._send_json(200, school_payload())
                except Exception:
                    log.exception("School summary read failed")
                    self._send_json(503, {"error": "Koulumuistutuksia ei voitu lukea"})
                return

            if path == "/calendar-month.json":
                query = parse_qs(parsed.query)
                now = time.localtime()
                try:
                    year = int((query.get("year") or [now.tm_year])[0])
                    month = int((query.get("month") or [now.tm_mon])[0])
                    if year < 2000 or year > 2100 or month < 1 or month > 12:
                        raise ValueError
                except (TypeError, ValueError):
                    self._send_json(400, {"error": "Invalid year/month"})
                    return

                try:
                    config = _web_mvp_config(load_config(config_path))
                    data = fetch_month(config, year, month, use_cache=use_cache)
                    self._send_json(200, data)
                except Exception as exc:
                    log.exception("Month calendar fetch failed")
                    self._send_json(503, {"error": str(exc)})
                return

            if path == "/dashboard.png":
                if not OUTPUT_PATH.exists():
                    message = "Dashboard image is not available yet."
                    if state.last_error:
                        message += f" Last render error: {state.last_error}"
                    body = message.encode("utf-8")
                    self.send_response(503)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self._no_cache_headers()
                    self.end_headers()
                    self.wfile.write(body)
                    return

                body = OUTPUT_PATH.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self._no_cache_headers()
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/health":
                last_success = (
                    time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(state.last_success))
                    if state.last_success else ""
                )
                body = (
                    f"ok={OUTPUT_PATH.exists()}\n"
                    f"last_success={last_success}\n"
                    f"last_error={state.last_error or ''}\n"
                ).encode("utf-8")
                self.send_response(200 if OUTPUT_PATH.exists() else 503)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._no_cache_headers()
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return

            self.send_error(404)

        def log_message(self, format, *args):
            log.info("HTTP %s - %s", self.address_string(), format % args)

    return DashboardHandler


def parse_args():
    parser = argparse.ArgumentParser(
        description="Serve the family dashboard for an Android/tablet browser"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Listen address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    parser.add_argument(
        "--refresh-seconds", type=int, default=30,
        help="How often to re-render the dashboard (default: 30)",
    )
    parser.add_argument(
        "--config", default="config.yaml", help="Configuration file (default: config.yaml)"
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="Force data refresh on every render"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.refresh_seconds < 10:
        raise SystemExit("--refresh-seconds must be at least 10")

    state = DashboardState()
    try:
        render_once(args.config, use_cache=False)
        state.last_success = time.time()
    except Exception as exc:
        state.last_error = str(exc)
        log.exception("Initial web MVP render failed; server will start and retry")

    stop_event = threading.Event()
    use_cache = not args.no_cache
    render_thread = threading.Thread(
        target=_render_loop,
        args=(stop_event, state, args.config, args.refresh_seconds, use_cache),
        daemon=True,
        name="dashboard-renderer",
    )
    render_thread.start()

    server = ThreadingHTTPServer(
        (args.host, args.port),
        make_handler(state, args.refresh_seconds, args.config, use_cache),
    )
    log.info("Web MVP server listening on http://%s:%s", args.host, args.port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Stopping web MVP server...")
    finally:
        stop_event.set()
        server.server_close()


if __name__ == "__main__":
    main()
