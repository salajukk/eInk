"""Wilma message source adapter boundary.

Phase 1 intentionally supports only synthetic JSON fixtures. The live Wilma
client can later be added behind :func:`fetch_messages` without leaking Wilma-
specific response shapes into the analyzer or dashboard.
"""

from __future__ import annotations

import json
from pathlib import Path


class WilmaMessageSourceError(Exception):
    pass


def _normalize(raw: dict) -> dict:
    return {
        "id": str(raw.get("id") or ""),
        "sent_at": str(raw.get("sent_at") or ""),
        "sender": str(raw.get("sender") or ""),
        "subject": str(raw.get("subject") or ""),
        "body": str(raw.get("body") or ""),
        "student": raw.get("student"),
    }


def load_fixture_messages(path: str | Path) -> list[dict]:
    fixture_path = Path(path)
    try:
        raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WilmaMessageSourceError(f"Could not read Wilma fixture {fixture_path}: {exc}") from exc

    messages = raw.get("messages") if isinstance(raw, dict) else raw
    if not isinstance(messages, list):
        raise WilmaMessageSourceError("Wilma fixture must contain a message list")
    return [_normalize(item) for item in messages if isinstance(item, dict)]


def fetch_messages(config: dict) -> list[dict]:
    """Fetch messages from the configured adapter.

    Only the fixture adapter is enabled in phase 1. Real Wilma credentials are
    deliberately not part of this MVP commit.
    """
    cfg = config.get("wilma_messages") or {}
    provider = str(cfg.get("provider") or "").strip().lower()

    if provider == "fixture":
        path = cfg.get("fixture_path") or "tests/fixtures/wilma_messages.json"
        return load_fixture_messages(path)

    raise WilmaMessageSourceError(
        "Wilma message provider is not configured. Phase 1 supports provider: fixture only."
    )
