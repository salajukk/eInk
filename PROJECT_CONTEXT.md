# Perheen näyttö – project context

This file is the short shared context for conversations about the software, hardware and physical frame. More detailed software/deployment instructions are in `FAMILY_DASHBOARD.md`.

## What we are building

A lightweight wall-mounted family information display for the home. The display uses e-paper so it looks more like a framed information board than a conventional tablet. The dashboard combines the family's useful daily information into one glanceable view: clock/date, weather, HSL departures, today's and upcoming calendar/school events, reminders and forecast.

The current target is a 13.3inch black/white e-paper panel with a 960x680 dashboard. Layout details can be refined later; the current priority is to get the complete software + Raspberry Pi + display hardware chain working reliably.

## Repository

GitHub repository:

https://github.com/salajukk/eInk

Active development branch:

`family-dashboard-v1`

Keep the current pull request as draft until the real Raspberry Pi + 13.3inch e-paper hardware has been tested successfully.

## Hardware – current plan

Primary hardware:

- Raspberry Pi 3 Model A+
- Waveshare 13.3inch e-Paper HAT (K), black/white, 960x680, SPI
- 32 GB microSD card
- Raspberry Pi compatible 5 V micro-USB power supply (about 12.5 W / 2.5 A class)

The Waveshare HAT connects to the Raspberry Pi GPIO/SPI interface and the display is powered through the Pi/HAT setup. The finished wall unit therefore needs only one external power cable to the Raspberry Pi.

A powerbank is **not** part of the first version. It can be reconsidered later if wall power placement proves inconvenient.

The 13.3inch hardware adapter is implemented in `display/epaper_13in3.py`. Partial refresh is intentionally disabled until it has been verified on the physical panel; initial hardware tests use safe whole-screen refreshes.

## Frame / enclosure – current plan

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

The 13.3inch simulator layout is working at 960x680. Current data sources/features include:

- weather
- Google/family calendars through private iCal feeds
- Wilma school schedules for two children through private iCal feeds
- HSL bus and train departures through Digitransit
- simple reminders/tasks

Today's events remain visible for the whole day, even after their end time. Calendar and school entries are merged chronologically and displayed without calendar-source labels.

Google Tasks integration is a later backlog item. The intended future behaviour is to merge both users' open personal Google Tasks into one nameless `MUISTETTAVAA` list without owner prefixes.

## Privacy / secrets

Never commit or paste real credentials into GitHub or chat. Keep the following only in local `config.yaml` / local credential files:

- private Google Calendar iCal URLs
- private Wilma iCal URLs
- Digitransit API key
- future Google OAuth client/token files

`config.yaml` is gitignored.
