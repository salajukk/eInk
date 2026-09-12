# Perheen näyttö – project context

This file is the short shared context for conversations about the software, hardware and physical frame. More detailed software/deployment instructions are in `FAMILY_DASHBOARD.md`.

## What we are building

A lightweight family information display for the home. The dashboard combines the family's useful daily information into one glanceable view: clock/date, weather, HSL departures, today's and upcoming calendar/school events, reminders and forecast.

The currently deployed product is an Android tablet in the kitchen, served by an always-on Raspberry Pi 5. The original 13.3inch black/white e-paper concept remains a possible later output path, but the successful tablet MVP now justifies using tablet-specific interaction when it adds clear family value.

The **primary family dashboard** must still stay shared and e-paper-compatible: 960x680 target canvas, black/white presentation, glanceable single-screen layout, and no required scrolling or touch interaction. Tablet/browser-only secondary views may now use interaction such as swiping and scrolling without forcing those features into the e-paper renderer. This keeps the main dashboard portable while allowing the tablet installation to evolve beyond a static e-paper preview.

Current priority is to improve the real kitchen-tablet experience while keeping the Raspberry Pi server deployment stable. Preserve the shared 960x680 dashboard and existing e-paper/7.5inch paths, but do not reject useful tablet-only secondary views merely because they cannot be reproduced on e-paper.

## Repository

GitHub repository:

https://github.com/salajukk/eInk

Active development branch:

`family-dashboard-v1`

Keep the current pull request as draft until the real Raspberry Pi + 13.3inch e-paper hardware has been tested successfully. Google Calendar, Wilma and HSL have now been verified through the Raspberry Pi-hosted tablet MVP.

## MVP – Android tablet

The first real-life display uses an existing Android tablet with a stand in the kitchen.

Goals of the current tablet phase:

- keep the continuously visible primary family dashboard fast and glanceable
- continue improving its content/layout based on real family use
- preserve the shared 960x680 black/white primary renderer for optional future e-paper output
- allow useful browser-only secondary views, such as a swipeable monthly calendar and Raspberry Pi health view
- keep data fetching and the core dashboard rendering device-independent as practical

The primary dashboard should still behave like an always-visible information board. Tablet-only interaction should live in the browser shell around it rather than being required by the shared renderer.

The browser output is implemented in `web_dashboard.py`. It reuses the existing data modules and `render_family_13in3.py`, writes the shared 960x680 dashboard to `output/dashboard.png`, and serves it to the Android browser over the trusted home LAN. The primary view remains that rendered PNG.

The tablet web shell now has three horizontal views. The family dashboard stays in the middle. Swiping **right** from it opens Raspberry Pi system health, and swiping **left** on system health returns to the dashboard. Swiping **left** from the dashboard opens the vertically scrollable monthly calendar, and swiping **right** on the calendar returns to the dashboard. The month table shows one row per day and one column per configured iCal calendar, with previous/next-month controls. Month data comes from `data/calendar_month.py`, which is deliberately separate from the compact `data/calendar.py` path used by the main dashboard. See `TABLET_MONTH_CALENDAR.md` and `SYSTEM_HEALTH.md`.

The preferred MVP server launcher is `dashboard_supervisor.py`. It runs `web_dashboard.py`, checks `origin/family-dashboard-v1` every 60 seconds, performs only safe fast-forward pulls when a newer commit is available, and restarts the web dashboard so repository changes take effect automatically. Tracked local edits block an automatic update rather than being overwritten. `config.yaml` and credentials remain local/gitignored. This allows future dashboard changes committed through GitHub (including changes requested from a phone) to propagate to the home server without manually running `git pull`. See `AUTO_UPDATE.md` for details.

The permanent MVP server is now a Raspberry Pi 5 (2 GB) running Raspberry Pi OS Lite 64-bit. The repository is checked out on the Pi from `family-dashboard-v1`, and `dashboard_supervisor.py` runs at boot as a `systemd` service named `family-dashboard.service`. The Pi uses hostname `familydisplay`; the home router has a DHCP reservation for it because `.local` name resolution was not reliable on the Android tablet. The previous Windows/Lenovo server is no longer required for normal dashboard operation.

The Raspberry deployment has been reboot-tested successfully: after power/reboot it rejoins Wi-Fi, starts the supervisor automatically and serves a freshly rendered dashboard to the tablet without a Windows machine or open SSH session.

## Hardware – current Raspberry / optional e-paper phase

Current purchased and deployed Raspberry hardware:

- Raspberry Pi 5, 2 GB RAM
- Kingston 64 GB Canvas Select Plus Gen3 UHS-I microSD card
- official Raspberry Pi 5 27 W USB-C power supply

Possible later display hardware remains:

- Waveshare 13.3inch e-Paper HAT (K), black/white, 960x680, SPI

The Waveshare HAT is intended to connect to the Raspberry Pi GPIO/SPI interface. The finished wall unit should still need only one external power cable to the Raspberry Pi.

A powerbank is **not** part of the first dedicated e-paper version. It can be reconsidered later if wall power placement proves inconvenient.

The 13.3inch hardware adapter is implemented in `display/epaper_13in3.py`. Partial refresh is intentionally disabled until it has been verified on the physical panel; initial hardware tests use safe whole-screen refreshes. The existing 13.3inch software path was originally prepared before the final Pi purchase, so the Waveshare driver/GPIO path must be verified specifically on the Raspberry Pi 5 before assuming physical-display support is complete.

Keep existing 7.5inch display support intact unless there is a separate reason to change it.

## Frame / enclosure – possible e-paper phase

If the e-paper phase is pursued, the first enclosure should contain only:

- the 13.3inch e-paper panel
- Raspberry Pi 5 (2 GB)
- Waveshare driver HAT
- the internal display cable
- the single external USB-C power cable

No powerbank compartment is required. Because the final computer is a Raspberry Pi 5 rather than the earlier Pi 3 A+ plan, thermal management and clearance around the Pi must be considered before the rear layout and enclosure depth are finalized.

Preferred direction is to start from a lightweight ready-made picture frame around the 24x30 cm class, mounted horizontally, if the real panel fits its rebate correctly. Glass/acrylic should be removed so the matte e-paper surface remains directly visible. A lightweight custom rear plate holds the Pi and HAT, with a small cable exit at the bottom for the power lead.

If a fully custom frame is needed, the current rough target is about 310 x 236 mm externally and roughly 28–30 mm maximum depth. The exact frame, panel supports, cooling/airflow and rear electronics positions should be finalized only after the physical Waveshare panel is available for measurement, especially the panel edge and FPC/display-cable routing.

The design goal is a thin, light object that looks like a normal framed picture and can be mounted with a normal picture-frame fixing or suitable removable wall strips, subject to the final measured weight.

## Current software state

The shared family layout is working at 960x680. The Android/tablet path in `web_dashboard.py` serves the same rendered PNG as its primary view without invoking e-paper hardware.

The browser/tablet path is running successfully on the Raspberry Pi 5. The Pi installation uses a project virtual environment, local gitignored `config.yaml`, `dashboard_supervisor.py`, and a boot-enabled `family-dashboard.service`. The full data/render path has been verified after reboot on the Raspberry-hosted server.

Current data sources/features include:

- weather
- Google/family calendars through private iCal feeds
- Wilma school schedules for two children through private iCal feeds
- HSL bus and train departures through Digitransit
- simple reminders/tasks
- actionable reminders extracted conservatively from live Wilma messages

Today's events remain visible for the whole day, even after their end time. Calendar and school entries are merged chronologically and displayed without calendar-source labels. The TULEVAT panel groups the next three future dates that have content under weekday/date headings; repeated event titles are allowed and long event text wraps instead of being truncated.

The tablet web shell also has a separate full-month calendar. It fetches every occurrence for the selected month from all configured `calendars:` sources and presents them as calendar columns with day rows. The month view is intentionally allowed to scroll vertically and is not part of the e-paper renderer.

A read-only Raspberry Pi health monitor is also available. `system_health.py` collects CPU temperature, throttling flags, one-minute load, RAM, disk, uptime, `family-dashboard.service`, the local web health endpoint and internet connectivity. It writes `cache/health/health.json` and a compact rolling `cache/health/history.json`. `web_dashboard.py` exposes `/system`, with current status plus 24-hour temperature/RAM/disk charts, and also embeds that page as the right-swipe secondary view next to the family dashboard. While system health is open it refreshes every five minutes; an always-on systemd health timer has deliberately not been added yet. See `SYSTEM_HEALTH.md`.

The Android/tablet primary dashboard refreshes the rendered image every 30 seconds. HSL cached departures are aged on every render, with the HSL cache capped at one minute for the web MVP, while the generic calendar/weather-style cache is capped at five minutes. The monthly calendar uses the same generic web cache cap and refreshes while open. The server session starts with a forced fresh primary-dashboard data fetch.

The Wilma-message reminder MVP is wired into the shared data/render path for the 960x680 layout. `integrations/wilma_messages.py` contains fixture and live message-source adapters, `analysis/wilma_reminders.py` contains conservative replaceable Finnish text analysis, and `data/school_reminders.py` contains expiry plus local hash/reminder state. Raw Wilma message bodies are analyzed in memory and are not persisted. `main.py` reconciles active reminders with the already-fetched family calendar at presentation time: safe matches enrich the existing calendar event with remember-items, while unmatched reminders appear in a compact `KOULUSTA MUISTETTAVAA` area. At most two standalone school reminders are shown. The 7.5-inch renderer remains unchanged. See `WILMA_REMINDERS.md`.

Google Tasks integration is a later backlog item. The intended future behaviour is to merge both users' open personal Google Tasks into one nameless `MUISTETTAVAA` list without owner prefixes.

Software changes should remain small and controlled. Keep the shared primary renderer and data modules reusable, while allowing clearly separated tablet/browser enhancements in `web_dashboard.py` and dedicated web-only helpers. The e-paper adapter and existing display support should remain available rather than constraining the tablet experience.

## Privacy / secrets

Never commit or paste real credentials into GitHub or chat. Keep the following only in local `config.yaml` / local credential files:

- private Google Calendar iCal URLs
- private Wilma iCal URLs
- Wilma message login base URL, username and password
- Digitransit API key
- future Google OAuth client/token files

`config.yaml` is gitignored.
