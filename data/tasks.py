"""Simple family reminders from config.yaml.

V1 deliberately keeps reminders local and dependency-free. Later the same
`fetch()` contract can be backed by Google Tasks, Todoist or another source
without changing the renderer.
"""

from datetime import datetime


def fetch(config: dict, use_cache: bool = True) -> dict:
    raw_items = config.get("tasks", {}).get("items", [])
    items = []
    for item in raw_items:
        if isinstance(item, str):
            title = item.strip()
            done = False
        elif isinstance(item, dict):
            title = str(item.get("title", "")).strip()
            done = bool(item.get("done", False))
        else:
            continue
        if title and not done:
            items.append({"title": title})

    return {
        "items": items,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
