#!/usr/bin/env python3
"""
main.py – E-ink dashboard main program.
Fetches data, renders the image and displays it.
"""

import argparse
import importlib
import json
import logging
import platform
import sys
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("cache/error.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("dashboard")

MODULES = (
    "weather",
    "electricity",
    "waste",
    "calendar",
    "evaka",
    "hsl",
    "tasks",
    "school",
    "school_reminders",
)


def load_config(path: str = "config.yaml") -> dict:
    cfg_path = Path(path)
    if not cfg_path.exists():
        log.warning(
            "config.yaml not found. Copy config.example.yaml → config.yaml and fill in the details."
        )
        return {}
    with cfg_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _is_raspberry_pi() -> bool:
    """Return True when running on an actual Raspberry Pi."""
    if platform.system() != "Linux":
        return False

    for model_path in (
        Path("/proc/device-tree/model"),
        Path("/sys/firmware/devicetree/base/model"),
    ):
        try:
            if model_path.exists() and "raspberry pi" in model_path.read_text(errors="ignore").lower():
                return True
        except OSError:
            pass
    return False


def get_display(config: dict):
    """Select simulator or the configured Raspberry Pi display adapter."""
    if not _is_raspberry_pi():
        from display.simulator import SimulatorDisplay
        return SimulatorDisplay()

    display_cfg = config.get("display", {})
    layout = display_cfg.get("layout", "legacy")
    model = str(display_cfg.get("model") or "").strip().lower()

    # Preserve old configs that did not have display.model yet.
    if not model:
        model = "waveshare_13in3k" if layout == "family_13in3" else "waveshare_7in5_v2"

    if model in ("waveshare_13in3k", "13in3k", "13.3k"):
        from display.epaper_13in3 import EPaper13in3Display
        return EPaper13in3Display()

    if model in ("waveshare_7in5_v2", "waveshare_7in5", "7in5", "7.5"):
        from display.epaper import EPaperDisplay
        return EPaperDisplay()

    raise RuntimeError(
        f"Unknown display.model '{model}'. Supported models: "
        "waveshare_13in3k, waveshare_7in5_v2"
    )


def feature_enabled(config: dict, name: str) -> bool:
    """Return whether a data module should run.

    When the new `features` section is absent, preserve the original repository's
    behaviour for backwards compatibility with existing config.yaml files.

    `school_reminders` has an additional migration-friendly rule: if the feature
    flag is not present but a wilma_messages provider is configured locally, the
    module is enabled. Adding `features.school_reminders: false` always disables
    it explicitly.
    """
    features = config.get("features")
    if features is not None:
        if name in features:
            return bool(features.get(name, False))
        if name == "school_reminders":
            return bool((config.get("wilma_messages") or {}).get("provider"))
        return False

    if name in ("weather", "electricity", "waste", "calendar"):
        return True
    if name == "evaka":
        return bool(config.get("evaka", {}).get("username"))
    if name == "hsl":
        return bool(config.get("hsl", {}).get("api_key"))
    if name == "school_reminders":
        return bool((config.get("wilma_messages") or {}).get("provider"))
    return False


def fetch_module(name: str, config: dict, use_cache: bool) -> "dict | None":
    """Fetches data for a single module. Returns None if fetching fails."""
    try:
        if name not in MODULES:
            log.error("Unknown module: %s", name)
            return None
        fetch = importlib.import_module(f"data.{name}").fetch
        data = fetch(config, use_cache=use_cache)
        if not data:
            return data
        stale = data.get("_stale", False)
        status = " (stale cache)" if stale else ""
        log.info("✓ %s%s", name, status)
        return data
    except Exception as e:
        log.error("✗ %s failed: %s", name, e)
        return None


def _renderer(config: dict):
    layout = config.get("display", {}).get("layout", "legacy")
    if layout == "family":
        module_name = "render_family"
    elif layout == "family_13in3":
        module_name = "render_family_13in3"
    else:
        module_name = "render"
    return importlib.import_module(module_name)


def _school_reminder_view(data: dict) -> dict | None:
    """Reconcile active Wilma reminders with the already-fetched calendar.

    The source module stays independent from calendars. Reconciliation happens
    only at presentation time so a matching calendar event can be enriched while
    unmatched reminders remain available for the compact school-reminder strip.
    """
    source = data.get("school_reminders")
    if not source:
        return None

    from data.school_reminders import reconcile_with_calendar

    reconciled = reconcile_with_calendar(source.get("items") or [], data.get("calendar"))
    return {
        **source,
        "standalone": reconciled["standalone"],
        "enrichments": reconciled["enrichments"],
    }


def _render_dashboard(config: dict, data: dict, width: int, height: int):
    renderer = _renderer(config)
    layout = config.get("display", {}).get("layout", "legacy")

    if layout == "family_13in3":
        return renderer.render(
            weather=data.get("weather"),
            calendar=data.get("calendar"),
            tasks=data.get("tasks"),
            school=data.get("school"),
            school_reminders=_school_reminder_view(data),
            hsl=data.get("hsl"),
            width=width,
            height=height,
            title=config.get("dashboard", {}).get("title", "PERHEEN NÄYTTÖ"),
        )

    # Keep the original 7.5inch family renderer API unchanged.
    if layout == "family":
        return renderer.render(
            weather=data.get("weather"),
            calendar=data.get("calendar"),
            tasks=data.get("tasks"),
            school=data.get("school"),
            hsl=data.get("hsl"),
            width=width,
            height=height,
            title=config.get("dashboard", {}).get("title", "PERHEEN NÄYTTÖ"),
        )

    return renderer.render(
        weather=data.get("weather"),
        electricity=data.get("electricity"),
        waste=data.get("waste"),
        calendar=data.get("calendar"),
        daycare=data.get("evaka"),
        hsl=data.get("hsl"),
        width=width,
        height=height,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="E-ink dashboard")
    parser.add_argument("--preview", action="store_true", help="Open the rendered image in Preview (Mac only)")
    parser.add_argument("--no-cache", action="store_true", help="Force data refresh, ignore cache")
    parser.add_argument("--only", choices=MODULES, help="Run only one module (for testing)")
    parser.add_argument("--full-refresh", action="store_true", help="Use a true full refresh instead of fast refresh")
    parser.add_argument("--partial-only", action="store_true", help="Partial-refresh configured cells")
    parser.add_argument("--config", default="config.yaml", help="Configuration file (default: config.yaml)")
    return parser.parse_args()


def main():
    args = parse_args()
    Path("cache").mkdir(exist_ok=True)

    config = load_config(args.config)
    use_cache = not args.no_cache
    display_cfg = config.get("display", {})
    width = display_cfg.get("width", 800)
    height = display_cfg.get("height", 480)

    if args.only:
        data = fetch_module(args.only, config, use_cache)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if args.partial_only:
        renderer = _renderer(config)
        partial_cells = renderer.PARTIAL_CELLS
        enabled_cfg = config.get("partial_updates") or {}
        enabled = [name for name, on in enabled_cfg.items() if on and name in partial_cells]
        if not enabled:
            log.warning("partial_updates: no cells enabled in config; nothing to do")
            return

        display = get_display(config)
        if not getattr(display, "supports_partials", True):
            log.warning(
                "Partial refresh is disabled for display model %s; skipping this tick",
                getattr(display, "model", "configured display"),
            )
            return

        def _load_cache(name):
            path = Path(f"cache/{name}.json")
            if not path.exists():
                return None
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning("cache/%s.json unreadable: %s", name, e)
                return None

        def _resolve_filter(spec: str):
            mod_name, fn_name = spec.split(":", 1)
            return getattr(importlib.import_module(mod_name), fn_name)

        data = {name: _load_cache(name) for name in MODULES}
        for name in enabled:
            cell = partial_cells[name]
            if cell["filter"] and cell["data_key"]:
                fn = _resolve_filter(cell["filter"])
                data[cell["data_key"]] = fn(data[cell["data_key"]])

        image = _render_dashboard(config, data, width, height)
        regions = [(image.crop(partial_cells[name]["region"]), partial_cells[name]["region"])
                   for name in enabled]
        log.info("Partial-refresh: %s", ", ".join(enabled))
        display.show_partials(regions, open_preview=args.preview)
        log.info("Done.")
        return

    log.info("Fetching data...")
    data = {}
    for name in MODULES:
        data[name] = fetch_module(name, config, use_cache) if feature_enabled(config, name) else None

    log.info("Rendering image...")
    image = _render_dashboard(config, data, width, height)

    display = get_display(config)
    if args.full_refresh and hasattr(display, "show_full"):
        display.show_full(image, open_preview=args.preview)
    else:
        display.show(image, open_preview=args.preview)
    log.info("Done.")


if __name__ == "__main__":
    main()
