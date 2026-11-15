#!/usr/bin/env python3
"""Safely test Wilma message reminder extraction without changing the dashboard.

Loads the local gitignored config.yaml, fetches/analyzes Wilma messages and
prints only structured reminder output. Raw Wilma message bodies are never
printed by this diagnostic.
"""

import argparse
import json

from data.school_reminders import fetch
from main import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Wilma reminder extraction")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    data = fetch(config, use_cache=not args.no_cache)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
