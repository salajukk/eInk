"""Wilma message source adapters.

The dashboard depends only on the normalized message dictionaries returned by
``fetch_messages``. Wilma-specific HTTP/login details stay in this module so the
transport can be replaced later without changing analysis or rendering code.

The live adapter uses the community-observed Wilma web endpoints. Credentials
must come from the local, gitignored config.yaml; they are never persisted by
this module.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import requests


class WilmaMessageSourceError(Exception):
    pass


class _LoginPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.session_id: str | None = None

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() != "input":
            return
        values = {str(key).lower(): value for key, value in attrs}
        if str(values.get("name") or "").upper() == "SESSIONID":
            value = values.get("value")
            if value:
                self.session_id = str(value)


class _ChildLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.children: list[dict] = []
        self._current_id: str | None = None
        self._current_text: list[str] = []
        self._seen: set[str] = set()

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() != "a":
            return
        values = {str(key).lower(): value for key, value in attrs}
        href = str(values.get("href") or "")
        match = re.match(r"^/!(\d+)/", href)
        if match:
            self._current_id = match.group(1)
            self._current_text = []

    def handle_data(self, data: str):
        if self._current_id is not None and data.strip():
            self._current_text.append(data.strip())

    def handle_endtag(self, tag: str):
        if tag.lower() != "a" or self._current_id is None:
            return
        child_id = self._current_id
        name = " ".join(self._current_text).strip()
        if child_id not in self._seen and name:
            self.children.append({"id": child_id, "name": name})
            self._seen.add(child_id)
        self._current_id = None
        self._current_text = []


class _MessageBodyParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if self._depth:
            if tag.lower() in {"br", "p", "li", "div"}:
                self._parts.append("\n")
            # Void elements such as <br> have no matching end tag.
            if tag.lower() not in {"br", "hr", "img", "input", "meta", "link"}:
                self._depth += 1
            return

        if tag.lower() != "div":
            return
        values = {str(key).lower(): value for key, value in attrs}
        classes = str(values.get("class") or "").split()
        if "ckeditor" in classes:
            self._depth = 1

    def handle_endtag(self, tag: str):
        if not self._depth:
            return
        if tag.lower() in {"p", "li", "div"}:
            self._parts.append("\n")
        self._depth -= 1

    def handle_data(self, data: str):
        if self._depth and data.strip():
            self._parts.append(data.strip())

    def text(self) -> str:
        joined = " ".join(self._parts)
        joined = re.sub(r"[ \t]*\n[ \t]*", "\n", joined)
        joined = re.sub(r"[ \t]{2,}", " ", joined)
        return "\n".join(line.strip() for line in joined.splitlines() if line.strip())


def _normalize(raw: dict) -> dict:
    return {
        "id": str(raw.get("id") or ""),
        "sent_at": str(raw.get("sent_at") or ""),
        "sender": str(raw.get("sender") or ""),
        "subject": str(raw.get("subject") or ""),
        "body": str(raw.get("body") or ""),
        "student": raw.get("student"),
        "student_id": raw.get("student_id"),
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


def _extract_session_id(html: str) -> str | None:
    parser = _LoginPageParser()
    parser.feed(html)
    return parser.session_id


def _extract_children(html: str) -> list[dict]:
    parser = _ChildLinkParser()
    parser.feed(html)
    return parser.children


def _extract_message_body(html: str) -> str:
    parser = _MessageBodyParser()
    parser.feed(html)
    return parser.text()


class _WilmaWebClient:
    """Minimal synchronous Wilma web client used only by this adapter."""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (compatible; FamilyDashboard/1.0)",
        "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.7",
    }

    def __init__(self, base_url: str, username: str, password: str, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def login(self) -> None:
        # Start each poll with a new session; Wilma sessions can expire and stale
        # cookies may otherwise redirect the login page unexpectedly.
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

        response = self.session.get(f"{self.base_url}/login", timeout=self.timeout)
        response.raise_for_status()
        session_id = _extract_session_id(response.text)
        if not session_id:
            raise WilmaMessageSourceError(
                "Wilma login page did not contain SESSIONID; the Wilma login flow may have changed"
            )

        response = self.session.post(
            f"{self.base_url}/login",
            data={
                "Login": self.username,
                "Password": self.password,
                "SESSIONID": session_id,
                "returnpath": "",
                "submit": "Kirjaudu sisään",
            },
            allow_redirects=True,
            timeout=self.timeout,
        )
        response.raise_for_status()
        if "name=\"Login\"" in response.text or "name='Login'" in response.text:
            raise WilmaMessageSourceError("Wilma login failed; check the local username/password")

    def children(self) -> list[dict]:
        response = self.session.get(f"{self.base_url}/", timeout=self.timeout)
        response.raise_for_status()
        return _extract_children(response.text)

    def message_list(self, child_id: str) -> list[dict]:
        response = self.session.get(
            f"{self.base_url}/!{child_id}/messages/list",
            timeout=self.timeout,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise WilmaMessageSourceError("Wilma message list was not valid JSON") from exc

        if payload.get("Status") != 200:
            raise WilmaMessageSourceError(
                f"Wilma message list returned status {payload.get('Status')}"
            )

        messages = payload.get("Messages") or []
        if not isinstance(messages, list):
            return []
        return sorted(
            [item for item in messages if isinstance(item, dict)],
            key=lambda item: str(item.get("TimeStamp") or ""),
            reverse=True,
        )

    def message_body(self, child_id: str, message_id: str) -> str:
        response = self.session.get(
            f"{self.base_url}/!{child_id}/messages/{message_id}",
            timeout=self.timeout,
        )
        if response.status_code == 403:
            return ""
        response.raise_for_status()
        return _extract_message_body(response.text)


def _require_live_config(cfg: dict) -> tuple[str, str, str]:
    base_url = str(cfg.get("base_url") or "").strip()
    username = str(cfg.get("username") or "").strip()
    password = str(cfg.get("password") or "").strip()
    missing = [
        name
        for name, value in (("base_url", base_url), ("username", username), ("password", password))
        if not value
    ]
    if missing:
        raise WilmaMessageSourceError(
            "Wilma live provider is missing local config values: " + ", ".join(missing)
        )
    if not re.match(r"^https://[^/]+", base_url, re.I):
        raise WilmaMessageSourceError("Wilma base_url must be an https:// address")
    return base_url, username, password


def fetch_live_messages(cfg: dict) -> list[dict]:
    """Fetch a bounded set of recent messages for configured/linked children."""
    base_url, username, password = _require_live_config(cfg)
    try:
        limit = int(cfg.get("limit_per_child", 20))
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 50))

    requested_ids = {
        str(value).strip()
        for value in (cfg.get("child_ids") or [])
        if str(value).strip()
    }

    client = _WilmaWebClient(base_url, username, password)
    try:
        client.login()
        children = client.children()
        if requested_ids:
            children = [child for child in children if str(child.get("id")) in requested_ids]
            missing = requested_ids - {str(child.get("id")) for child in children}
            if missing:
                raise WilmaMessageSourceError(
                    "Configured Wilma child_ids were not found on the logged-in account"
                )
        if not children:
            raise WilmaMessageSourceError("No Wilma children were found for the logged-in account")

        normalized: list[dict] = []
        for child in children:
            child_id = str(child.get("id") or "").strip()
            child_name = str(child.get("name") or "").strip() or None
            if not child_id:
                continue
            for item in client.message_list(child_id)[:limit]:
                message_id = str(item.get("Id") or "").strip()
                if not message_id:
                    continue
                body = client.message_body(child_id, message_id)
                if not body:
                    continue
                normalized.append(
                    _normalize(
                        {
                            "id": f"{child_id}:{message_id}",
                            "sent_at": item.get("TimeStamp") or "",
                            "sender": item.get("Sender") or "",
                            "subject": item.get("Subject") or "",
                            "body": body,
                            "student": child_name,
                            "student_id": child_id,
                        }
                    )
                )
        normalized.sort(key=lambda item: item.get("sent_at") or "", reverse=True)
        return normalized
    except requests.RequestException as exc:
        raise WilmaMessageSourceError(f"Wilma network request failed: {exc}") from exc


def fetch_messages(config: dict) -> list[dict]:
    """Fetch messages from the configured replaceable adapter."""
    cfg = config.get("wilma_messages") or {}
    provider = str(cfg.get("provider") or "").strip().lower()

    if provider == "fixture":
        path = cfg.get("fixture_path") or "tests/fixtures/wilma_messages.json"
        return load_fixture_messages(path)
    if provider in {"live", "wilma"}:
        return fetch_live_messages(cfg)

    raise WilmaMessageSourceError(
        "Wilma message provider is not configured. Supported providers: fixture, live."
    )
