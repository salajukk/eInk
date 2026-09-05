"""Family-focused 800×480 renderer.

This renderer lives beside the original `render.py` so the upstream layout can
still be used with `display.layout: legacy`. It reuses the shared drawing
primitives and fonts but gives most screen space to family calendar information.
"""

from datetime import date, datetime

from PIL import Image, ImageDraw

from render import (
    BG,
    FG,
    GRAY,
    PAD,
    FONT_CLOCK72,
    FONT_HERO,
    FONT_LABEL,
    FONT_MED,
    FONT_REG18,
    FONT_SMALL,
    FONT_TINY,
    FONT_TINY_R,
    _DAYS_FI,
    _date_str,
    _divider,
    _draw_weather_icon,
    _text,
    _vertical_divider,
)

WIDTH, HEIGHT = 800, 480
BAND_H = 118
CONTENT_Y = BAND_H
CONTENT_H = 190
TASKS_Y = CONTENT_Y + CONTENT_H
TASKS_H = 52
FORECAST_Y = TASKS_Y + TASKS_H
FORECAST_H = HEIGHT - FORECAST_Y
HALF_W = WIDTH // 2


def _fit_text(draw: ImageDraw.Draw, text: str, font, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    value = text
    while value and draw.textlength(value + "…", font=font) > max_width:
        value = value[:-1]
    return value.rstrip() + "…"


def _section_label(draw: ImageDraw.Draw, x: int, y: int, text: str, stale: bool = False):
    _text(draw, (x + PAD, y + PAD), text, FONT_LABEL, fill=GRAY)
    if stale:
        _text(draw, (x + PAD + int(draw.textlength(text, font=FONT_LABEL)) + 6, y + PAD),
              "*", FONT_LABEL, fill=GRAY)


def _draw_now_band(draw: ImageDraw.Draw, weather: dict | None, hsl: dict | None,
                   title: str, w: int, h: int = BAND_H):
    draw.rectangle([0, 0, w, h - 1], fill=FG)
    now = datetime.now()
    mid = h // 2

    time_str = now.strftime("%H:%M")
    _text(draw, (16, mid), time_str, FONT_CLOCK72, fill=BG, anchor="lm")
    dx = 16 + int(draw.textlength(time_str, font=FONT_CLOCK72)) + 18
    _text(draw, (dx, mid - 14), _DAYS_FI[now.weekday()], FONT_REG18, fill=BG, anchor="ls")
    _text(draw, (dx, mid + 26), f"{now.day}.{now.month}.", FONT_MED, fill=BG, anchor="ls")

    wx = 338
    if weather:
        _draw_weather_icon(draw, wx, mid - 26, weather.get("icon", "unknown"),
                           size=52, ink=BG, paper=FG)
        temp = weather.get("temperature")
        temp_str = f"{temp:.0f}°" if temp is not None else "-°"
        _text(draw, (wx + 62, mid), temp_str, FONT_HERO, fill=BG, anchor="lm")
        tx = wx + 62 + int(draw.textlength(temp_str, font=FONT_HERO)) + 10
        condition = weather.get("condition_fi") or weather.get("condition") or ""
        _text(draw, (tx, mid - 18), _fit_text(draw, condition, FONT_TINY, 126),
              FONT_TINY, fill=BG)
        hi, lo = weather.get("forecast_today_high"), weather.get("forecast_today_low")
        if hi is not None and lo is not None:
            _text(draw, (tx, mid + 3), f"{lo:.0f}° … {hi:.0f}°", FONT_TINY_R, fill=BG)

    conns = (hsl or {}).get("connections") or []
    first = conns[0] if conns else None
    if first and first.get("minutes_until") is not None:
        line = first.get("lines", "").split(" -> ")[0]
        dest = first.get("to", "")
        _text(draw, (w - 16, 14), f"{line} -> {dest} · {first.get('first_depart', '')}",
              FONT_TINY_R, fill=BG, anchor="ra")
        _text(draw, (w - 16, mid + 12), f"{first['minutes_until']} min",
              FONT_HERO, fill=BG, anchor="rm")
    else:
        _text(draw, (w - 16, mid - 5), title.upper(), FONT_MED, fill=BG, anchor="rm")
        _text(draw, (w - 16, mid + 22), "tänään yhdellä silmäyksellä",
              FONT_TINY_R, fill=BG, anchor="rm")


def _event_meta(ev: dict, today: bool) -> str:
    cal = ev.get("calendar", "")
    time_str = ev.get("time")
    if today:
        when = time_str[:5] if time_str else "koko päivä"
    else:
        when = _date_str(ev.get("date", ""), weekday=True)
        if time_str:
            when += f"  {time_str[:5]}"
    return f"{when}  ·  {cal}" if cal else when


def _draw_events(draw: ImageDraw.Draw, data: dict | None, x: int, y: int,
                 w: int, h: int, today: bool):
    label = "TÄNÄÄN" if today else "TULEVAT"
    stale = bool(data and data.get("_stale"))
    _section_label(draw, x, y, label, stale=stale)
    cy = y + PAD + 20

    events = (data or {}).get("events", [])
    today_iso = date.today().isoformat()
    if today:
        events = [ev for ev in events if ev.get("date") == today_iso]
        empty = "Ei menoja tänään"
    else:
        events = [ev for ev in events if ev.get("date", "") > today_iso]
        empty = "Ei tulevia tapahtumia"

    if not events:
        _text(draw, (x + PAD, cy + 4), empty, FONT_SMALL, fill=GRAY)
        return

    block_h = 39
    for ev in events:
        if cy + block_h > y + h - 6:
            break
        meta = _event_meta(ev, today)
        title = str(ev.get("title", ""))
        title = _fit_text(draw, title, FONT_MED, w - 2 * PAD)
        _text(draw, (x + PAD, cy), meta, FONT_TINY_R, fill=GRAY)
        _text(draw, (x + PAD, cy + 17), title, FONT_MED)
        cy += block_h


def _draw_tasks(draw: ImageDraw.Draw, data: dict | None, x: int, y: int, w: int, h: int):
    _section_label(draw, x, y, "MUISTETTAVAA")
    items = (data or {}).get("items", [])[:3]
    if not items:
        _text(draw, (x + 126, y + PAD), "Ei muistettavaa", FONT_LABEL, fill=GRAY)
        return

    cy = y + 29
    slot_w = w // len(items)
    for i, item in enumerate(items):
        sx = x + i * slot_w + PAD
        box_y = cy + 2
        draw.rectangle([sx, box_y, sx + 10, box_y + 10], outline=FG, width=1)
        title = item.get("title", "") if isinstance(item, dict) else str(item)
        title = _fit_text(draw, title, FONT_TINY, slot_w - PAD - 20)
        _text(draw, (sx + 17, cy), title, FONT_TINY)


def _draw_forecast(draw: ImageDraw.Draw, data: dict | None, x: int, y: int, w: int, h: int):
    _section_label(draw, x, y, "ENNUSTE", stale=bool(data and data.get("_stale")))
    days = (data or {}).get("forecast", [])[:7]
    if not days:
        _text(draw, (x + PAD, y + 34), "Ei saatavilla", FONT_SMALL, fill=GRAY)
        return

    col_w = w // len(days)
    icon_size = 34
    top = y + 27
    for i, day in enumerate(days):
        cx = x + i * col_w + col_w // 2
        heading = f"{day.get('day', '')} {day.get('date', '')}".strip()
        _text(draw, (cx, top), heading, FONT_TINY, fill=GRAY, anchor="ma")
        _draw_weather_icon(draw, cx - icon_size // 2, top + 18,
                           day.get("icon", "unknown"), size=icon_size)
        hi, lo = day.get("high"), day.get("low")
        if hi is not None and lo is not None:
            _text(draw, (cx - 2, top + 58), f"{hi:.0f}°", FONT_SMALL, anchor="ra")
            _text(draw, (cx + 3, top + 61), f"{lo:.0f}°", FONT_TINY_R, fill=GRAY, anchor="la")


def render(weather: dict | None = None, calendar: dict | None = None,
           tasks: dict | None = None, hsl: dict | None = None,
           width: int = WIDTH, height: int = HEIGHT,
           title: str = "PERHEEN NÄYTTÖ") -> Image.Image:
    """Render the family dashboard.

    The current layout is designed for the Waveshare 7.5" V2 (800×480).
    """
    if width != WIDTH or height != HEIGHT:
        raise ValueError("Family layout currently supports only 800×480 displays")

    img = Image.new("L", (width, height), BG)
    draw = ImageDraw.Draw(img)

    _draw_now_band(draw, weather, hsl, title, width)
    _vertical_divider(draw, HALF_W, CONTENT_Y + 8, TASKS_Y - 8)
    _draw_events(draw, calendar, 0, CONTENT_Y, HALF_W, CONTENT_H, today=True)
    _draw_events(draw, calendar, HALF_W + 1, CONTENT_Y, width - HALF_W - 1, CONTENT_H, today=False)

    _divider(draw, 0, TASKS_Y, width)
    _draw_tasks(draw, tasks, 0, TASKS_Y, width, TASKS_H)

    _divider(draw, 0, FORECAST_Y, width)
    _draw_forecast(draw, weather, 0, FORECAST_Y, width, FORECAST_H)
    return img


CLOCK_REGION = (0, 0, 240, BAND_H)
HSL_REGION = (624, 0, 800, BAND_H)
PARTIAL_CELLS = {
    "clock": {"region": CLOCK_REGION, "data_key": None, "filter": None},
    "hsl": {"region": HSL_REGION, "data_key": "hsl", "filter": "data.hsl:drop_past_departures"},
}
