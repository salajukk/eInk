"""Family-focused renderer for Waveshare 13.3inch e-Paper HAT (K).

Target resolution: 960×680. The 7.5inch 800×480 renderer stays untouched in
`render_family.py`; this module reuses its family-data drawing helpers while
using the extra vertical space for a roomier wall-dashboard layout.
"""

from datetime import datetime

from PIL import Image, ImageDraw

from render import (
    BG,
    FG,
    GRAY,
    PAD,
    FONT_CLOCK72,
    FONT_HERO,
    FONT_MED,
    FONT_REG18,
    FONT_TINY,
    FONT_TINY_R,
    _DAYS_FI,
    _date_str,
    _divider,
    _draw_weather_icon,
    _load_font,
    _text,
    _vertical_divider,
)
from render_family import (
    _draw_forecast,
    _draw_tasks,
    _fit_text,
    _section_label,
)
from render_family_schedule import (
    _draw_today_panel,
    _draw_upcoming_panel,
)

WIDTH, HEIGHT = 960, 680
BAND_H = 150
CONTENT_Y = BAND_H
CONTENT_H = 300
TASKS_Y = CONTENT_Y + CONTENT_H
TASKS_H = 70
FORECAST_Y = TASKS_Y + TASKS_H
FORECAST_H = HEIGHT - FORECAST_Y
HALF_W = WIDTH // 2
TASKS_SPLIT_X = 560

# The departure board is intentionally larger than the secondary dashboard text.
# It should be possible to glance at the next bus/train times from a few metres away.
FONT_HSL = _load_font(20, bold=True)
FONT_HSL_LABEL = _load_font(15)


def _hsl_departure_row(stop: dict) -> str | None:
    """Build one HSL row using clock times instead of minute countdowns.

    Bus rows show line, destination and three clock times. Rail rows deliberately
    omit train letters because every configured departure is towards Helsinki.
    """
    departures = (stop or {}).get("departures") or []
    departures = [dep for dep in departures[:3] if dep.get("departure")]
    if not departures:
        return None

    first = departures[0]
    destination = str(first.get("headsign") or stop.get("name") or "").strip()
    lines = [str(dep.get("line") or "?").strip() for dep in departures]
    times = [str(dep.get("departure") or "").strip() for dep in departures]

    stop_type = str(stop.get("type") or "").strip().lower()
    rail_only = all(str(dep.get("mode") or "").upper() == "RAIL" for dep in departures)
    if stop_type == "station" or rail_only:
        # Example: "Juna HKI 18:04 · 18:11 · 18:19"
        return f"Juna HKI  {' · '.join(times)}"

    if len(set(lines)) == 1:
        # Example: "41A Kamppi 18:03 · 18:23 · 18:43"
        return f"{lines[0]} {destination}  {' · '.join(times)}".strip()

    # Fallback for a stop serving several bus lines.
    pairs = " · ".join(f"{line} {time}" for line, time in zip(lines, times))
    return f"{destination}  {pairs}".strip()


def _draw_now_band(draw: ImageDraw.Draw, weather: dict | None, hsl: dict | None,
                   title: str, w: int, h: int = BAND_H):
    """Roomier 13.3inch top band: clock, weather and two HSL departure rows."""
    draw.rectangle([0, 0, w, h - 1], fill=FG)
    now = datetime.now()
    mid = h // 2

    # Clock/date block.
    time_str = now.strftime("%H:%M")
    _text(draw, (20, mid), time_str, FONT_CLOCK72, fill=BG, anchor="lm")
    dx = 20 + int(draw.textlength(time_str, font=FONT_CLOCK72)) + 20
    _text(draw, (dx, mid - 14), _DAYS_FI[now.weekday()], FONT_REG18,
          fill=BG, anchor="ls")
    _text(draw, (dx, mid + 26), f"{now.day}.{now.month}.", FONT_MED,
          fill=BG, anchor="ls")

    # Weather block in the middle. Keep it compact enough to give the departure
    # board more horizontal room without changing the overall top-band structure.
    wx = 350
    if weather:
        _draw_weather_icon(draw, wx, mid - 28,
                           weather.get("icon", "unknown"),
                           size=56, ink=BG, paper=FG)
        temp = weather.get("temperature")
        temp_str = f"{temp:.0f}°" if temp is not None else "-°"
        _text(draw, (wx + 68, mid), temp_str, FONT_HERO, fill=BG, anchor="lm")
        tx = wx + 68 + int(draw.textlength(temp_str, font=FONT_HERO)) + 12
        condition = weather.get("condition_fi") or weather.get("condition") or ""
        _text(draw, (tx, mid - 19), _fit_text(draw, condition, FONT_TINY, 90),
              FONT_TINY, fill=BG)
        hi, lo = weather.get("forecast_today_high"), weather.get("forecast_today_low")
        if hi is not None and lo is not None:
            _text(draw, (tx, mid + 4), f"{lo:.0f}° … {hi:.0f}°",
                  FONT_TINY_R, fill=BG)

    # HSL departure board on the right. The larger type is a deliberate MVP
    # choice: these are among the most distance-critical values on the screen.
    stop_boards = (hsl or {}).get("stops") or []
    if stop_boards:
        rows = []
        for stop in stop_boards[:2]:
            row = _hsl_departure_row(stop)
            rows.append(row or f"{stop.get('name', 'Pysäkki')}  ei lähtöjä")

        right = w - 20
        max_width = 340
        _text(draw, (right, 18), "LÄHDÖT", FONT_HSL_LABEL, fill=BG, anchor="ra")
        for idx, row in enumerate(rows[:2]):
            y = 48 + idx * 42
            _text(draw, (right, y), _fit_text(draw, row, FONT_HSL, max_width),
                  FONT_HSL, fill=BG, anchor="ra")
        return

    # Keep a useful identity block when HSL is disabled.
    _text(draw, (w - 20, mid - 8), title.upper(), FONT_MED, fill=BG, anchor="rm")
    _text(draw, (w - 20, mid + 22), "tänään yhdellä silmäyksellä",
          FONT_TINY_R, fill=BG, anchor="rm")


def _school_reminder_text(item: dict) -> str:
    """Compact one-line representation for the school-reminder strip."""
    day = _date_str(str(item.get("date") or ""), weekday=True).capitalize()
    student = str(item.get("student") or "").strip()
    title = str(item.get("title") or "").strip()
    remember = [str(value).strip() for value in item.get("remember") or [] if str(value).strip()]

    head = " ".join(part for part in (day, student) if part)
    if student and title:
        text = f"{head} · {title}"
    else:
        text = " ".join(part for part in (head, title) if part)

    if remember:
        text += (" · " if text else "") + " · ".join(remember)
    return text


def _draw_school_reminders(draw: ImageDraw.Draw, data: dict | None,
                           x: int, y: int, w: int, h: int):
    """Show at most two nearest standalone Wilma-message reminders."""
    stale = bool(data and data.get("_stale"))
    _section_label(draw, x, y, "KOULUSTA MUISTETTAVAA", stale=stale)
    items = list((data or {}).get("standalone") or [])
    items.sort(
        key=lambda item: (
            str(item.get("date") or ""),
            str(item.get("student") or ""),
            str(item.get("title") or ""),
        )
    )
    items = items[:2]

    cy = y + 29
    max_width = w - 2 * PAD
    if not items:
        _text(draw, (x + PAD, cy), "Ei koulumuistutuksia", FONT_TINY_R, fill=GRAY)
        return

    for item in items:
        text = _fit_text(draw, _school_reminder_text(item), FONT_TINY, max_width)
        _text(draw, (x + PAD, cy), text, FONT_TINY)
        cy += 20


def render(weather: dict | None = None, calendar: dict | None = None,
           tasks: dict | None = None, school: dict | None = None,
           school_reminders: dict | None = None,
           hsl: dict | None = None, width: int = WIDTH, height: int = HEIGHT,
           title: str = "PERHEEN NÄYTTÖ") -> Image.Image:
    """Render the 13.3inch family dashboard at exactly 960×680 pixels."""
    if width != WIDTH or height != HEIGHT:
        raise ValueError("13.3inch family layout supports only 960×680 displays")

    img = Image.new("L", (width, height), BG)
    draw = ImageDraw.Draw(img)

    _draw_now_band(draw, weather, hsl, title, width)

    _vertical_divider(draw, HALF_W, CONTENT_Y + 10, TASKS_Y - 10)
    _draw_today_panel(
        draw, calendar, school, 0, CONTENT_Y, HALF_W, CONTENT_H,
        school_reminders=school_reminders,
    )
    _draw_upcoming_panel(
        draw, calendar, school, HALF_W + 1, CONTENT_Y,
        width - HALF_W - 1, CONTENT_H,
        school_reminders=school_reminders,
    )

    _divider(draw, 0, TASKS_Y, width)
    _vertical_divider(draw, TASKS_SPLIT_X, TASKS_Y + 8, FORECAST_Y - 8)
    _draw_tasks(draw, tasks, 0, TASKS_Y, TASKS_SPLIT_X, TASKS_H)
    _draw_school_reminders(
        draw, school_reminders, TASKS_SPLIT_X + 1, TASKS_Y,
        width - TASKS_SPLIT_X - 1, TASKS_H,
    )

    _divider(draw, 0, FORECAST_Y, width)
    _draw_forecast(draw, weather, 0, FORECAST_Y, width, FORECAST_H)
    return img


# Partial-refresh areas are 8-pixel aligned so the hardware adapter can later
# use the panel's partial-update mode safely.
CLOCK_REGION = (0, 0, 288, BAND_H)
HSL_REGION = (640, 0, 960, BAND_H)
PARTIAL_CELLS = {
    "clock": {"region": CLOCK_REGION, "data_key": None, "filter": None},
    "hsl": {
        "region": HSL_REGION,
        "data_key": "hsl",
        "filter": "data.hsl:drop_past_departures",
    },
}
