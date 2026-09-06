# Perheen näyttö – project context

This file is the short shared context for conversations about the software, hardware and physical frame. More detailed software/deployment instructions are in `FAMILY_DASHBOARD.md`.

## What we are building

A lightweight family information display for the home. The dashboard combines the family's useful daily information into one glanceable view: clock/date, weather, HSL departures, today's and upcoming calendar/school events, reminders and forecast.

The long-term target remains a 13.3inch black/white e-paper panel with a 960x680 dashboard, designed to look more like a framed information board than a conventional tablet. Before purchasing the roughly 250 € e-paper + Raspberry Pi hardware setup, the concept will first be tested in everyday use on an existing Android tablet placed in the kitchen.

The Android phase is an MVP of the **same dashboard**, not a separate tablet product. Keep the dashboard content, layout and visual constraints e-paper-compatible: 960x680 target canvas, black/white presentation, glanceable single-screen layout, and no dependency on animations, scrolling or tablet-only interaction. The MVP can be iterated and improved while running on the tablet. If the family finds that having the view continuously visible is valuable enough to justify the dedicated hardware, the same dashboard should then be moved to Raspberry Pi + 13.3inch e-paper by changing/adapting the display output layer rather than redesigning the view.

Current priority is therefore to validate the usefulness and content of the continuously visible family dashboard on Android while preserving a straightforward migration path to the planned e-paper hardware.

## Repository

GitHub repository:

https://github.com/salajukk/eInk

Active development branch:

`family-dashboard-v1`

Keep the current pull request as draft until Google Calendar, Wilma and HSL have been tested in the MVP and the real Raspberry Pi + 13.3inch e-paper hardware has later been tested successfully.

## MVP – Android tablet

The first real-life deployment uses an existing Android tablet with a stand in the kitchen.

Goals of the MVP:

- test whether a continuously visible family dashboard provides enough everyday value to justify dedicated e-paper hardware
- keep the current dashboard view and continue improving its content/layout during the test
- preserve the 960x680 black/white e-paper design constraints throughout the MVP
- keep data fetching and dashboard rendering as device-independent as practical
- treat Android and future e-paper support as different display/output targets for the same dashboard

The MVP should avoid tablet-specific features that would make later e-paper migration difficult. Prefer a simple full-screen/kiosk-style presentation of the rendered dashboard and automatic refreshes.

The browser output is implemented in `web_dashboard.py`. It reuses the existing data modules and `render_family_13in3.py`, writes the same 960x680 dashboard to `output/dashboard.png`, and serves it to the Android browser over the trusted home LAN. It intentionally does not reimplement the dashboard as an HTML UI. Default render interval is 30 seconds and default HTTP port is 8080. See `FAMILY_DASHBOARD.md` for startup/testing instructions.

The preferred MVP server launcher is now `dashboard_supervisor.py`. It runs `web_dashboard.py`, checks `origin/family-dashboard-v1` every 60 seconds, performs only safe fast-forward pulls when a newer commit is available, and restarts the web dashboard so repository changes take effect automatically. Tracked local edits block an automatic update rather than being overwritten. `config.yaml` and credentials remain local/gitignored. This allows future dashboard changes committed through GitHub (including changes requested from a phone) to propagate to the home server without manually running `git pull`. See `AUTO_UPDATE.md` for details.

The current Windows PC acts as the temporary MVP server. The next hardware step is to replace the Windows PC server role with a Raspberry Pi while continuing to serve the Android tablet. On the Pi, the same supervisor can be run first manually and later configured as a `systemd` service at boot.

Decision gate: only purchase/build the dedicated roughly 250 € Raspberry Pi + 13.3inch e-paper setup if the kitchen-tablet test demonstrates that the always-visible dashboard is genuinely useful to the family.

## Hardware – planned e-paper phase

Primary hardware, if/when the MVP validates the concept:

- Raspberry Pi 3 Model A+
- Waveshare 13.3inch e-Paper HAT (K), black/white, 960x680, SPI
- 32 GB microSD card
- Raspberry Pi compatible 5 V micro-USB power supply (about 12.5 W / 2.5 A class)

The Waveshare HAT connects to the Raspberry Pi GPIO/SPI interface and the display is powered through the Pi/HAT setup. The finished wall unit therefore needs only one external power cable to the Raspberry Pi.

A powerbank is **not** part of the first dedicated e-paper version. It can be reconsidered later if wall power placement proves inconvenient.

The 13.3inch hardware adapter is implemented in `display/epaper_13in3.py`. Partial refresh is intentionally disabled until it has been verified on the physical panel; initial hardware tests use safe whole-screen refreshes.

Keep existing 7.5inch display support intact unless there is a separate reason to change it.

## Frame / enclosure – planned e-paper phase

The first enclosure should contain only:

- the 13.3inch e-paper panel
- Raspberry Pi 3 A+
- Waveshare driver HAT
- the internal display cable
- the single external micro-USB power cable

No powerbank compartment is required.

Preferred direction is to start from a lightweight ready-made picture frame around the 24x30 cm class, mounted horizontally, if the real panel fits its rebate correctly. Glass/acrylic should be removed so the matte e-paper surface remains directly visible. A lightweight custom rear plate holds the Pi and HAT, with a small cable exit at the bottom for the power lead.

If a fully custom frame is needed, the current rough target is about 310 x 236 mm externally and roughly 28–30 mm maximum depth. The exact frame, panel supports and rear electronics positions should be finalized only after the physical Waveshare panel is available for measurement, especially the panel edge and FPC/display-cable routing.

The design goal is a thin, light object that looks like a normal framed picture and can be mounted with a normal picture-frame fixing or suitable removable wall strips, subject to the final measured weight.

## Current software state

The 13.3inch simulator layout is working at 960x680. The Android MVP has a browser-friendly output path in `web_dashboard.py`, which keeps the same renderer and serves the generated PNG to a tablet without invoking e-paper hardware.

Current data sources/features include:

- weather
- Google/family calendars through private iCal feeds
- Wilma school schedules for two children through private iCal feeds
- HSL bus and train departures through Digitransit
- simple reminders/tasks

Today's events remain visible for the whole day, even after their end time. Calendar and school entries are merged chronologically and displayed without calendar-source labels. The TULEVAT panel shows the next six chronological occurrences without suppressing repeated titles, and long event text wraps instead of being truncated.

The Android MVP refreshes the rendered dashboard every 30 seconds. HSL cached departures are aged on every render, with the HSL cache capped at one minute for the web MVP, while the generic calendar/weather-style cache is capped at five minutes. The server session starts with a forced fresh data fetch.

Google Tasks integration is a later backlog item. The intended future behaviour is to merge both users' open personal Google Tasks into one nameless `MUISTETTAVAA` list without owner prefixes.

Software changes for the Android MVP should remain small and controlled. Continue improving the browser/output deployment path around the existing rendering and data logic rather than duplicating the dashboard implementation. The e-paper adapter and existing display support should remain available for the later hardware phase.

## Privacy / secrets

Never commit or paste real credentials into GitHub or chat. Keep the following only in local `config.yaml` / local credential files:

- private Google Calendar iCal URLs
- private Wilma iCal URLs
- Digitransit API key
- future Google OAuth client/token files

`config.yaml` is gitignored.
