import math
import platform
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── Font loading ─────────────────────────────────────────────────────────────
#
# Place Inter font files in fonts/ for the best look on both macOS and Pi:
#   fonts/Inter-Regular.ttf  and  fonts/Inter-Bold.ttf
# Download from: https://github.com/rsms/inter/releases
#
# Fallback chain:  Inter → Futura (macOS) → Helvetica (macOS) → DejaVu (Linux)

_FONTS_DIR = Path(__file__).parent / "fonts"


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates: list[tuple[str, int]] = []

    inter = _FONTS_DIR / ("Inter-Bold.ttf" if bold else "Inter-Regular.ttf")
    if inter.exists():
        candidates.append((str(inter), 0))

    if platform.system() == "Darwin":
        candidates += [
            ("/System/Library/Fonts/Supplemental/Futura.ttc", 4 if bold else 0),
            ("/Library/Fonts/Futura.ttc",                      4 if bold else 0),
            ("/System/Library/Fonts/Helvetica.ttc",            1 if bold else 0),
        ]
    else:
        base = "/usr/share/fonts/truetype/"
        candidates += [
            (base + ("inter/Inter-Bold.ttf" if bold else "inter/Inter-Regular.ttf"), 0),
            (base + ("dejavu/DejaVuSans-Bold.ttf" if bold else "dejavu/DejaVuSans.ttf"), 0),
        ]

    for path, index in candidates:
        try:
            return ImageFont.truetype(path, size, index=index)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


# ── Constants ────────────────────────────────────────────────────────────────

WIDTH, HEIGHT = 800, 480
BG      = 0     # black
FG      = 255   # white
GRAY    = 255   # white (same as FG inverse — all text white on black)
DIVIDER = 255   # pure white — mid-grays dither to speckle on the 1-bit panel

PAD = 12   # cell padding

# Layout: inverted NOW band + 3-column content row + stats line + forecast strip
BAND_H  = 118
MID_Y   = BAND_H          # 118 — content row below the band
MID_H   = 190
STATS_Y = MID_Y + MID_H   # 308 — one-line electricity + waste stats
FORECAST_H = 140
FORECAST_Y = HEIGHT - FORECAST_H     # 340
COL_W  = (WIDTH - 2) // 3            # ≈ 266 px  (2 px for dividers)
COL2_X = COL_W + 1                   # 267
COL3_X = COL_W * 2 + 2               # 534

# Fonts
FONT_MED    = _load_font(18, bold=True)   # event titles
FONT_SMALL  = _load_font(17, bold=True)   # detail rows, stats line
FONT_TINY   = _load_font(14, bold=True)   # secondary text
FONT_LABEL  = _load_font(12)              # section labels
FONT_TINY_R = _load_font(14)              # de-emphasized small text (regular)
FONT_CLOCK72 = _load_font(72, bold=True)  # NOW band clock
FONT_HERO    = _load_font(46, bold=True)  # NOW band temp + countdown
FONT_REG18   = _load_font(18)             # NOW band secondary (regular)


# ── Drawing primitives ───────────────────────────────────────────────────────

def _text(draw: ImageDraw.Draw, xy, text: str, font, fill=FG, anchor="la"):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def _divider(draw: ImageDraw.Draw, x1: int, y: int, x2: int):
    draw.line([(x1, y), (x2, y)], fill=DIVIDER, width=1)


def _vertical_divider(draw: ImageDraw.Draw, x: int, y1: int, y2: int):
    draw.line([(x, y1), (x, y2)], fill=DIVIDER, width=1)


def _wrap_text(draw: ImageDraw.Draw, text: str, font, max_width: int) -> list[str]:
    """Word-wraps text to fit within max_width pixels. Returns a list of lines."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        w = draw.textlength(candidate, font=font)
        if w <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            # If a single word is wider than max_width, truncate it with ellipsis
            if draw.textlength(word, font=font) > max_width:
                while word and draw.textlength(word + "…", font=font) > max_width:
                    word = word[:-1]
                word = word + "…"
            current = word
    if current:
        lines.append(current)
    return lines


def _label(draw: ImageDraw.Draw, x: int, y: int, text: str, stale: bool = False) -> int:
    """Draws the small gray section label. Returns y-coordinate for content start."""
    _text(draw, (x + PAD, y + PAD), text, FONT_LABEL, fill=GRAY)
    if stale:
        _text(draw, (x + PAD + 5 + len(text) * 7, y + PAD), "*", FONT_LABEL, fill=GRAY)
    return y + PAD + 16   # label height (11px) + 5px gap


def _badge(draw: ImageDraw.Draw, x: int, y: int, text: str) -> int:
    """Black pill with white text. Returns the badge width."""
    bbox = draw.textbbox((0, 0), text, font=FONT_SMALL)
    bw = bbox[2] - bbox[0] + 18
    bh = bbox[3] - bbox[1] + 10
    draw.rectangle([x, y, x + bw, y + bh], fill=FG)
    draw.text((x + 9, y + 5), text, font=FONT_SMALL, fill=BG)
    return bw


_DAYS_FI = ["ma", "ti", "ke", "to", "pe", "la", "su"]


def _date_str(iso: str, weekday: bool = False) -> str:
    """'2026-03-22' → '22.3.'  (or 'su 22.3.' if weekday=True)"""
    try:
        d = date.fromisoformat(iso)
        s = f"{d.day}.{d.month}."
        if weekday:
            s = f"{_DAYS_FI[d.weekday()]} {s}"
        return s
    except ValueError:
        return iso[5:]


# ── Weather icons (geometric, drawn with Pillow) ─────────────────────────────

def _draw_mode_icon(draw: ImageDraw.Draw, x: int, y: int, mode: str, size: int = 14, fill=FG):
    """Draws a small geometric transport mode icon. Top-left corner at (x, y)."""
    w, h = size, size
    r = max(2, size // 7)   # wheel radius

    if mode == "BUS":
        # Squat rectangle body + two wheels
        draw.rectangle([x, y + 1, x + w, y + h - r * 2 - 1], fill=fill)
        draw.ellipse([x + 1,         y + h - r * 2, x + 1 + r * 2,     y + h], fill=fill)
        draw.ellipse([x + w - r * 2, y + h - r * 2, x + w,              y + h], fill=fill)

    elif mode == "TRAM":
        # Like bus but with a thin overhead wire bar on top
        draw.rectangle([x + 2, y,     x + w - 2, y + 2],              fill=fill)  # pantograph
        draw.rectangle([x,     y + 3, x + w,     y + h - r * 2 - 1], fill=fill)  # body
        draw.ellipse([x + 1,         y + h - r * 2, x + 1 + r * 2, y + h], fill=fill)
        draw.ellipse([x + w - r * 2, y + h - r * 2, x + w,          y + h], fill=fill)

    elif mode in ("RAIL", "SUBWAY"):
        # Locomotive silhouette: rectangle with pointed nose on the right
        nose_x = x + w
        mid_y  = y + h // 2
        body = [
            (x,          y + 1),
            (nose_x - 3, y + 1),
            (nose_x,     mid_y),
            (nose_x - 3, y + h - r * 2 - 1),
            (x,          y + h - r * 2 - 1),
        ]
        draw.polygon(body, fill=fill)
        draw.ellipse([x + 2,         y + h - r * 2, x + 2 + r * 2,     y + h], fill=fill)
        draw.ellipse([x + w - r * 2 - 3, y + h - r * 2, x + w - 3, y + h], fill=fill)

    elif mode == "FERRY":
        # Boat hull (trapezoid) + small deck rectangle
        mid_y = y + h // 2
        hull  = [(x, mid_y), (x + 2, y + h), (x + w - 2, y + h), (x + w, mid_y)]
        draw.polygon(hull, fill=fill)
        draw.rectangle([x + 3, y + 2, x + w - 3, mid_y], fill=fill)

    else:
        # Unknown: simple square
        draw.rectangle([x, y + 2, x + w, y + h - 2], fill=fill)


def _cloud(draw: ImageDraw.Draw, ox: int, oy: int, s: int, fill=FG):
    w, h = s, s
    draw.ellipse([ox + int(0.12*w), oy + int(0.52*h), ox + int(0.52*w), oy + int(0.82*h)], fill=fill)
    draw.ellipse([ox + int(0.25*w), oy + int(0.30*h), ox + int(0.70*w), oy + int(0.72*h)], fill=fill)
    draw.ellipse([ox + int(0.44*w), oy + int(0.46*h), ox + int(0.84*w), oy + int(0.78*h)], fill=fill)
    draw.rectangle([ox + int(0.12*w), oy + int(0.64*h), ox + int(0.84*w), oy + int(0.82*h)], fill=fill)


def _sun(draw: ImageDraw.Draw, cx: int, cy: int, r: int, rays: int = 8, fill=FG):
    ri, ro = int(r * 0.55), r
    draw.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill=fill)
    for i in range(rays):
        angle = math.radians(i * 360 / rays)
        x1 = cx + int(math.cos(angle) * (ri + 3))
        y1 = cy + int(math.sin(angle) * (ri + 3))
        x2 = cx + int(math.cos(angle) * ro)
        y2 = cy + int(math.sin(angle) * ro)
        draw.line([x1, y1, x2, y2], fill=fill, width=2)


def _draw_weather_icon(draw: ImageDraw.Draw, ox: int, oy: int, icon_key: str,
                       size: int = 44, ink=FG, paper=BG):
    s = size
    if icon_key in ("clear", "mainly_clear"):
        _sun(draw, ox + s // 2, oy + s // 2, s // 2 - 2, fill=ink)
    elif icon_key == "partly_cloudy":
        _sun(draw, ox + int(s * 0.32), oy + int(s * 0.30), int(s * 0.26), fill=ink)
        _cloud(draw, ox + int(s * 0.18), oy + int(s * 0.38), int(s * 0.82), fill=paper)
        _cloud(draw, ox + int(s * 0.18), oy + int(s * 0.38), int(s * 0.82), fill=ink)
    elif icon_key == "overcast":
        _cloud(draw, ox + int(s * 0.05), oy + int(s * 0.14), int(s * 0.90), fill=ink)
    elif icon_key == "fog":
        for i in range(4):
            fy = oy + int(s * (0.22 + i * 0.18))
            fw = int(s * (0.85 - i * 0.10))
            fx = ox + (s - fw) // 2
            draw.rectangle([fx, fy, fx + fw, fy + 3], fill=ink)
    elif icon_key in ("drizzle", "rain"):
        _cloud(draw, ox, oy, int(s * 0.80), fill=ink)
        dy0 = oy + int(s * 0.70)
        for i in range(5):
            dx = ox + int(s * (0.15 + i * 0.18))
            draw.line([dx, dy0, dx - 3, dy0 + int(s * 0.22)], fill=ink, width=2)
    elif icon_key == "snow":
        _cloud(draw, ox, oy, int(s * 0.80), fill=ink)
        dy = oy + int(s * 0.78)
        for i in range(4):
            cx2 = ox + int(s * (0.18 + i * 0.22))
            r2 = 3
            draw.ellipse([cx2 - r2, dy - r2, cx2 + r2, dy + r2], fill=ink)
    elif icon_key == "thunderstorm":
        _cloud(draw, ox, oy, int(s * 0.80), fill=ink)
        bx, by = ox + int(s * 0.40), oy + int(s * 0.68)
        bolt = [
            (bx,                   by),
            (bx - int(s * 0.14),   by + int(s * 0.18)),
            (bx + int(s * 0.04),   by + int(s * 0.16)),
            (bx - int(s * 0.12),   by + int(s * 0.34)),
            (bx + int(s * 0.14),   by + int(s * 0.12)),
            (bx,                   by + int(s * 0.13)),
        ]
        draw.polygon(bolt, fill=ink)
    else:
        _cloud(draw, ox + int(s * 0.10), oy + int(s * 0.20), int(s * 0.80), fill=ink)


# ── Section drawers ──────────────────────────────────────────────────────────
#
# Each drawer receives (draw, data, x, y, w, h) where (x, y) is the top-left
# corner of the cell, w is the usable column width, h is the row height.


def _draw_forecast(draw: ImageDraw.Draw, data: dict | None,
                   x: int, y: int, w: int, h: int):
    """Full-width strip: coming days as columns (day, icon, high/low)."""
    cy = _label(draw, x, y, "ENNUSTE", stale=bool(data and data.get("_stale")))

    days = (data or {}).get("forecast", [])[:7]
    if not days:
        _text(draw, (x + PAD, cy), "Ei saatavilla", FONT_SMALL, fill=GRAY)
        return

    col_w = w // len(days)
    icon_size = 44

    for i, day in enumerate(days):
        cx = x + i * col_w + col_w // 2   # column center

        title = f"{day.get('day', '')} {day.get('date', '')}".strip()
        _text(draw, (cx, cy), title, FONT_TINY, fill=GRAY, anchor="ma")

        _draw_weather_icon(draw, cx - icon_size // 2, cy + 20,
                           day.get("icon", "unknown"), size=icon_size)

        hi, lo = day.get("high"), day.get("low")
        temp_y = cy + 20 + icon_size + 8
        if hi is not None and lo is not None:
            # High leads, low whispers — size does the hi/lo split (gray can't)
            _text(draw, (cx - 3, temp_y), f"{hi:.0f}°", FONT_SMALL, anchor="ra")
            _text(draw, (cx + 3, temp_y + 3), f"{lo:.0f}°", FONT_TINY_R, fill=GRAY, anchor="la")
        elif hi is not None:
            _text(draw, (cx, temp_y), f"{hi:.0f}°", FONT_SMALL, anchor="ma")



def _draw_calendar(draw: ImageDraw.Draw, data: dict | None,
                   x: int, y: int, w: int, h: int):
    cy = _label(draw, x, y, "KALENTERI", stale=bool(data and data.get("_stale")))

    if not data:
        _text(draw, (x + PAD, cy), "Ei saatavilla", FONT_SMALL, fill=GRAY)
        return

    events = data.get("events", [])
    if not events:
        _text(draw, (x + PAD, cy), "Ei tulevia tapahtumia", FONT_TINY, fill=GRAY)
        return

    row_h1  = 15   # date+time row
    row_h2  = 21   # title row
    row_gap = 6    # gap between events
    block_h = row_h1 + row_h2 + row_gap

    for ev in events:
        if cy + block_h > y + h - PAD:
            break
        dt  = _date_str(ev.get("date", ""), weekday=True)
        t   = ev.get("time")
        if t:
            dt += f"  {t[:5]}"
        title = ev.get("title", "")

        _text(draw, (x + PAD, cy),          dt,        FONT_TINY,  fill=GRAY)
        _text(draw, (x + PAD, cy + row_h1), title[:26], FONT_MED)
        cy += block_h


def _shorten_route(draw: ImageDraw.Draw, route: str, max_w: int) -> str:
    """Collapses middle legs to '…' when the route is too wide: 'A -> … -> Z'.

    Keeps the first line(s) and the arrival time (last segment) — the middle
    transfer chain is the expendable part.
    """
    if draw.textlength(route, font=FONT_SMALL) <= max_w:
        return route
    segs = route.split(" -> ")
    for keep in range(len(segs) - 2, 0, -1):
        candidate = " -> ".join(segs[:keep] + ["…"] + [segs[-1]])
        if draw.textlength(candidate, font=FONT_SMALL) <= max_w:
            return candidate
    # Even 'first -> … -> last' is too wide — hard-truncate from the end
    while route and draw.textlength(route + "…", font=FONT_SMALL) > max_w:
        route = route[:-1]
    return route.rstrip() + "…"


def _draw_hsl(draw: ImageDraw.Draw, data: dict | None,
              x: int, y: int, w: int, h: int):
    cy = _label(draw, x, y, "HSL lähdöt", stale=bool(data and data.get("_stale")))

    if not data:
        _text(draw, (x + PAD, cy), "Ei saatavilla", FONT_SMALL, fill=GRAY)
        return

    connections = data.get("connections", [])
    if not connections:
        _text(draw, (x + PAD, cy), "Ei yhteyksiä", FONT_SMALL, fill=GRAY)
        return

    # First connection lives in the NOW band — list the alternatives here
    connections = connections[1:]

    # Fixed column width for "HH:MM" so line names align vertically
    time_col = int(draw.textlength("00:00 ", font=FONT_SMALL)) + 4
    line_h   = 22

    for conn in connections:
        if cy + line_h > y + h - PAD:
            break
        arr2   = conn.get("arrival", "")
        lines2 = conn.get("lines", "")
        fdep2  = conn.get("first_depart", "")

        route = lines2
        if arr2:
            route += f" -> {arr2}"
        route = _shorten_route(draw, route, w - 2 * PAD - time_col)

        _text(draw, (x + PAD,            cy), fdep2,  FONT_SMALL)
        _text(draw, (x + PAD + time_col, cy), route,  FONT_SMALL, fill=GRAY)
        cy += line_h


def _draw_daycare(draw: ImageDraw.Draw, data: dict | None,
                  x: int, y: int, w: int, h: int):
    cy = _label(draw, x, y, "PÄIVÄKOTI", stale=bool(data and data.get("_stale")))

    if not data:
        _text(draw, (x + PAD, cy), "Ei saatavilla", FONT_SMALL, fill=GRAY)
        return

    events = data.get("events", [])
    if not events:
        _text(draw, (x + PAD, cy), "Ei tulevia tapahtumia", FONT_TINY, fill=GRAY)
        return

    row_h1   = 13   # date row
    row_h2   = 19   # title row (bold)
    desc_lh  = 12   # height per description line (FONT_LABEL size)
    row_gap  = 5

    for ev in events:
        dt    = _date_str(ev.get("date", ""), weekday=True)
        title = ev.get("title", "")
        desc  = ev.get("description", "")

        desc_lines = _wrap_text(draw, desc, FONT_LABEL, w - 2 * PAD)[:2] if desc else []
        block_h = row_h1 + row_h2 + len(desc_lines) * desc_lh + row_gap

        if cy + block_h > y + h - PAD:
            break

        _text(draw, (x + PAD, cy),           dt,    FONT_TINY, fill=GRAY)
        _text(draw, (x + PAD, cy + row_h1),  title, FONT_MED)
        for i, line in enumerate(desc_lines):
            _text(draw, (x + PAD, cy + row_h1 + row_h2 + i * desc_lh), line, FONT_LABEL, fill=GRAY)
        cy += block_h



# ── NOW band + stats line (V2) ──────────────────────────────────────────────

def _draw_now_band(draw: ImageDraw.Draw, weather: dict | None,
                   hsl: dict | None, w: int, h: int = BAND_H):
    """Inverted departure-board band: clock, current weather, leave-in countdown."""
    draw.rectangle([0, 0, w, h - 1], fill=FG)
    now = datetime.now()
    mid = h // 2

    # Clock + date
    time_str = now.strftime("%H:%M")
    _text(draw, (16, mid), time_str, FONT_CLOCK72, fill=BG, anchor="lm")
    dx = 16 + int(draw.textlength(time_str, font=FONT_CLOCK72)) + 18
    _text(draw, (dx, mid - 14), _DAYS_FI[now.weekday()], FONT_REG18, fill=BG, anchor="ls")
    _text(draw, (dx, mid + 26), f"{now.day}.{now.month}.", FONT_MED, fill=BG, anchor="ls")

    # Current weather
    wx = 350
    if weather:
        _draw_weather_icon(draw, wx, mid - 28, weather.get("icon", "unknown"),
                           size=56, ink=BG, paper=FG)
        temp = weather.get("temperature")
        temp_str = f"{temp:.0f}°" if temp is not None else "-°"
        _text(draw, (wx + 68, mid), temp_str, FONT_HERO, fill=BG, anchor="lm")
        tx2 = wx + 68 + int(draw.textlength(temp_str, font=FONT_HERO)) + 14
        _text(draw, (tx2, mid - 20), weather.get("condition_fi") or "", FONT_TINY, fill=BG)
        hi, lo = weather.get("forecast_today_high"), weather.get("forecast_today_low")
        if hi is not None and lo is not None:
            _text(draw, (tx2, mid + 2), f"{lo:.0f}° … {hi:.0f}°", FONT_TINY_R, fill=BG)

    # Leave-in countdown for the next connection
    conns = (hsl or {}).get("connections") or []
    first = conns[0] if conns else None
    if first and first.get("minutes_until") is not None:
        line1 = first.get("lines", "").split(" -> ")[0]
        dest  = first.get("to", "")
        _text(draw, (w - 16, 14), f"{line1} -> {dest} · lähtö {first.get('first_depart', '')}",
              FONT_TINY_R, fill=BG, anchor="ra")
        _text(draw, (w - 16, mid + 12), f"{first['minutes_until']} min",
              FONT_HERO, fill=BG, anchor="rm")


def _draw_stats_line(draw: ImageDraw.Draw, electricity: dict | None,
                     waste: dict | None, y: int):
    """Single quiet line for ambient stats: yesterday's kWh + waste pickups."""
    parts = []
    if electricity and electricity.get("yesterday_kwh") is not None:
        parts.append(f"Sähkö {electricity['yesterday_kwh']:.1f} kWh eilen")
    for col in (waste or {}).get("next_collections", [])[:2]:
        days = col.get("days_until")
        if days == 0:   days_str = "tänään"
        elif days == 1: days_str = "huomenna"
        elif days is not None: days_str = f"{days} pv"
        else:           days_str = col.get("date", "")[5:]
        parts.append(f"{col.get('type', '')} {days_str}")
    if parts:
        _text(draw, (PAD, y + 6), "   ·   ".join(parts), FONT_SMALL, fill=GRAY)



# ── Main render function ─────────────────────────────────────────────────────

def render(
    weather:     dict | None = None,
    electricity: dict | None = None,
    waste:       dict | None = None,
    calendar:    dict | None = None,
    daycare:     dict | None = None,
    hsl:         dict | None = None,
    width:  int = WIDTH,
    height: int = HEIGHT,
) -> Image.Image:
    """
    Renders the dashboard and returns a PIL Image (mode L, 800×480).

    Layout — inverted NOW band + content row + stats line + forecast strip:

      ┌──────────────────────────────────────────────────────────┐
      │  07:42  to 6.8.   [icon] 18° Pilvistä       12 min      │  NOW band (118px,
      ├──────────────────┬──────────────────┬────────────────────┤   inverted)
      │  PÄIVÄKOTI       │  KALENTERI       │  HSL lähdöt       │  CONTENT (190px)
      ├──────────────────┴──────────────────┴────────────────────┤
      │  Sähkö 32.0 kWh eilen · Sekajäte 7 pv · Biojäte 26 pv   │  STATS (32px)
      ├──────────────────────────────────────────────────────────┤
      │  ENNUSTE  (7 days as columns)                            │  STRIP (140px)
      └──────────────────────────────────────────────────────────┘
       COL_W ≈ 266 px each
    """
    img  = Image.new("L", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # NOW band: clock + current weather + leave-in countdown
    _draw_now_band(draw, weather, hsl, width)

    # Middle row: daycare | calendar | later HSL departures
    _vertical_divider(draw, COL_W,         MID_Y + 8, STATS_Y - 8)
    _vertical_divider(draw, COL_W * 2 + 1, MID_Y + 8, STATS_Y - 8)
    _draw_daycare (draw, daycare,  0,      MID_Y, COL_W,          MID_H)
    _draw_calendar(draw, calendar, COL2_X, MID_Y, COL_W,          MID_H)
    _draw_hsl     (draw, hsl,      COL3_X, MID_Y, width - COL3_X, MID_H)

    # One-line ambient stats: electricity + waste
    _draw_stats_line(draw, electricity, waste, STATS_Y)

    # Forecast strip
    _divider(draw, 0, FORECAST_Y, width)
    _draw_forecast(draw, weather, 0, FORECAST_Y, width, FORECAST_H)

    return img


# ── Partial: clock region ────────────────────────────────────────────────────
#
# Box is 8-px aligned on x so the 1bpp framebuffer slice is byte-aligned for
# the Waveshare 7.5" V2 partial-display API.

CLOCK_REGION = (0, 0, 240, BAND_H)    # NOW band: clock + date (left side)
HSL_REGION   = (624, 0, 800, BAND_H)  # NOW band: leave-in countdown (right side)

# Registry of cells eligible for partial refresh. Keys match config.yaml's
# `partial_updates` dict. Each entry has a region (x-aligned to 8) and an
# optional pre-render filter (`module:function`) applied to the cell's data.
PARTIAL_CELLS = {
    "clock": {"region": CLOCK_REGION, "data_key": None,        "filter": None},
    "hsl":   {"region": HSL_REGION,   "data_key": "hsl",       "filter": "data.hsl:drop_past_departures"},
}
