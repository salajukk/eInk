# Tablet month calendar

The Android/tablet web output has an optional interactive second view in addition
to the shared 960x680 family dashboard.

The primary dashboard remains unchanged and continues to use
`render_family_13in3.py` + `output/dashboard.png`, preserving the later e-paper
output path. The monthly calendar is tablet/browser-only and does not change the
7.5-inch or 13.3-inch e-paper renderers.

## Usage

On the normal family dashboard:

- swipe **right** to open the monthly calendar
- swipe **left** on the monthly calendar to return to the family dashboard
- scroll vertically to move through the days of the month
- use the `‹` / `›` buttons to open the previous or next month

The monthly table uses one row per day and one column per configured entry under
`calendars:` in the local `config.yaml`. Event titles and times are shown in the
column belonging to their source calendar.

No new calendar configuration is required. The private iCal URLs remain only in
the local gitignored `config.yaml`.

## Architecture

`data/calendar.py` remains the compact calendar source for the always-visible
family dashboard.

`data/calendar_month.py` separately fetches every occurrence in one selected
calendar month and keeps a per-month cache under:

```text
cache/calendar_months/
```

`web_dashboard.py` exposes the month data to its own browser UI through:

```text
/calendar-month.json?year=YYYY&month=M
```

The tablet shell renders the table in HTML/JavaScript. Calendar values are added
through DOM `textContent`; raw calendar text is not inserted as HTML.

The web-MVP generic cache cap also applies to month data, so normal tablet use
refreshes monthly data within at most about five minutes. While the month view is
open, the browser asks for refreshed month data every five minutes.

The service must remain on the trusted home LAN because both the PNG dashboard
and the month endpoint can contain private family calendar information.

## Tests

The month data helper has unit tests in:

```text
tests/test_calendar_month.py
```

Run them with the project virtual environment, for example on Raspberry Pi:

```bash
venv/bin/python -m unittest tests.test_calendar_month -v
```
