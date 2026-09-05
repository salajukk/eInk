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
    PAD,
    FONT_CLOCK72,
    FONT_HERO,
    FONT_MED,
    FONT_REG18,
    FONT_TINY,
    FONT_TINY_R,
    _DAYS_FI,
    _divider,
    _draw_weather_icon,
    _text,
    _vertical_divider,
)
from render_family import (
    _draw_forecast,
    _draw_tasks,
    _draw_today_panel,
    _draw_upcoming_panel,
    _fit_text,
    _hsl_departure_row,
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

    # Weather block in the middle.
    wx = 390
    if weather:
        _draw_weather_icon(draw, wx, mid - 28,
                           weather.get("icon", "unknown"),
                           size=56, ink=BG, paper=FG)
        temp = weather.get("temperature")
        temp_str = f"{temp:.0f}°" if temp is not None else "-°"
        _text(draw, (wx + 68, mid), temp_str, FONT_HERO, fill=BG, anchor="lm")
        tx = wx + 68 + int(draw.textlength(temp_str, font=FONT_HERO)) + 12
        condition = weather.get("condition_fi") or weather.get("condition") or ""
        _text(draw, (tx, mid - 19), _fit_text(draw, condition, FONT_TINY, 120),
              FONT_TINY, fill=BG)
        hi, lo = weather.get("forecast_today_high"), weather.get("forecast_today_low")
        if hi is not None and lo is not None:
            _text(draw, (tx, mid + 4), f"{lo:.0f}° … {hi:.0f}°",
                  FONT_TINY_R, fill=BG)

    # HSL departure board on the right.
    stop_boards = (hsl or {}).get("stops") or []
    if stop_boards:
        rows = []
        for stop in stop_boards[:2]:
            row = _hsl_departure_row(stop)
            rows.append(row or f"{stop.get('name', 'Pysäkki')}  ei lähtöjä")

        right = w - 20
        max_width = 305
        _text(draw, (right, 22), "LÄHDÖT", FONT_TINY_R, fill=BG, anchor="ra")
        for idx, row in enumerate(rows[:2]):
            y = 54 + idx * 35
            _text(draw, (right, y), _fit_text(draw, row, FONT_TINY, max_width),
                  FONT_TINY, fill=BG, anchor="ra")
        return

    # Keep a useful identity block when HSL is disabled.
    _text(draw, (w - 20, mid - 8), title.upper(), FONT_MED, fill=BG, anchor="rm")
    _text(draw, (w - 20, mid + 22), "tänään yhdellä silmäyksellä",
          FONT_TINY_R, fill=BG, anchor="rm")


def render(weather: dict | None = None, calendar: dict | None = None,
           tasks: dict | None = None, school: dict | None = None,
           hsl: dict | None = None, width: int = WIDTH, height: int = HEIGHT,
           title: str = "PERHEEN NÄYTTÖ") -> Image.Image:
    """Render the 13.3inch family dashboard at exactly 960×680 pixels."""
    if width != WIDTH or height != HEIGHT:
        raise ValueError("13.3inch family layout supports only 960×680 displays")

    img = Image.new("L", (width, height), BG)
    draw = ImageDraw.Draw(img)

    _draw_now_band(draw, weather, hsl, title, width)

    _vertical_divider(draw, HALF_W, CONTENT_Y + 10, TASKS_Y - 10)
    _draw_today_panel(draw, calendar, school, 0, CONTENT_Y, HALF_W, CONTENT_H)
    _draw_upcoming_panel(draw, calendar, school, HALF_W + 1, CONTENT_Y,
                         width - HALF_W - 1, CONTENT_H)

    _divider(draw, 0, TASKS_Y, width)
    _draw_tasks(draw, tasks, 0, TASKS_Y, width, TASKS_H)

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
