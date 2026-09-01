"""Small shared helpers used by both the CLI and the web routes."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


def parse_page_id(raw: str) -> str:
    """Accepts a bare numeric ID, a vanity name, or a full Facebook URL
    (profile.php?id=... or facebook.com/<vanity-name>) and returns just
    the id/name Meta's API expects — pasting a full page link "just works"
    instead of silently breaking search_page_ids downstream.
    """
    raw = raw.strip()
    if "facebook.com" not in raw:
        return raw

    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    qs_id = parse_qs(parsed.query).get("id")
    if qs_id:
        return qs_id[0]

    segment = parsed.path.strip("/").split("/")[0]
    return segment or raw


def is_numeric_page_id(page_id: str) -> bool:
    return bool(re.fullmatch(r"\d+", page_id))
