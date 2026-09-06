#!/usr/bin/env python3
"""Serve the existing family dashboard as an auto-refreshing web page.

This is the Android-tablet MVP output path. It reuses the same data modules and
960x680 renderer as the e-paper version, but writes the result to a PNG and
serves it over HTTP instead of talking to display hardware.
"""

import argparse
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

# main.py configures a file logger at import time, so ensure the directory exists.
Path("cache").mkdir(exist_ok=True)

from data.hsl import drop_past_departures  # noqa: E402
from main import MODULES, _render_dashboard, feature_enabled, fetch_module, load_config  # noqa: E402

log = logging.getLogger("dashboard.web")
OUTPUT_PATH = Path("output/dashboard.png")


def _web_mvp_config(config: dict) -> dict:
    """Use shorter cache windows for the always-visible tablet MVP.

    Existing config values are respected when they are already shorter. The
    generic cache controls calendar/weather-like data; HSL gets a much shorter
    window because departures become obsolete quickly. This tuning is local to
    web_dashboard.py and does not change the later e-paper deployment policy.
    """
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

    # A cached HSL response can still contain a departure that has passed since
    # the API fetch. Age/filter those rows on every render so the tablet never
    # shows an already-departed bus/train just because the cache is still valid.
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
            # Keep serving the previous successful image if a refresh fails.
            state.last_error = str(exc)
            log.exception("Web MVP refresh failed")


def _page(refresh_seconds: int) -> bytes:
    # Poll at most once per minute so the browser picks up a newly rendered PNG.
    browser_refresh = max(10, min(refresh_seconds, 60))
    page = f"""<!doctype html>
<html lang="fi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#ffffff">
  <title>Perheen näyttö</title>
  <style>
    html, body {{
      margin: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: #fff;
    }}
    body {{
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    #dashboard {{
      width: 100vw;
      height: 100vh;
      object-fit: contain;
      display: block;
    }}
  </style>
</head>
<body>
  <img id="dashboard" src="/dashboard.png?v=0" alt="Perheen näyttö">
  <script>
    const image = document.getElementById("dashboard");
    setInterval(() => {{
      image.src = "/dashboard.png?v=" + Date.now();
    }}, {browser_refresh * 1000});
  </script>
</body>
</html>
"""
    return page.encode("utf-8")


def make_handler(state, refresh_seconds):
    class DashboardHandler(BaseHTTPRequestHandler):
        def _no_cache_headers(self):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")

        def do_GET(self):
            path = urlparse(self.path).path

            if path == "/":
                body = _page(refresh_seconds)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._no_cache_headers()
                self.end_headers()
                self.wfile.write(body)
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
                    if state.last_success
                    else ""
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
        "--refresh-seconds",
        type=int,
        default=30,
        help="How often to re-render the dashboard (default: 30)",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Force data refresh on every render",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.refresh_seconds < 10:
        raise SystemExit("--refresh-seconds must be at least 10")

    state = DashboardState()

    try:
        # Always start the tablet session with fresh data so recent calendar
        # edits are visible immediately after restarting the server.
        render_once(args.config, use_cache=False)
        state.last_success = time.time()
    except Exception as exc:
        state.last_error = str(exc)
        log.exception("Initial web MVP render failed; server will start and retry")

    stop_event = threading.Event()
    render_thread = threading.Thread(
        target=_render_loop,
        args=(stop_event, state, args.config, args.refresh_seconds, not args.no_cache),
        daemon=True,
        name="dashboard-renderer",
    )
    render_thread.start()

    server = ThreadingHTTPServer(
        (args.host, args.port),
        make_handler(state, args.refresh_seconds),
    )
    log.info("Web MVP server listening on http://%s:%s", args.host, args.port)
    log.info(
        "Open it from the Android tablet using this computer's LAN IP, "
        "for example http://192.168.1.10:%s",
        args.port,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Stopping web MVP server...")
    finally:
        stop_event.set()
        server.server_close()


if __name__ == "__main__":
    main()
