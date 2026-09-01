"""Smart Swipe File — save/download backend (technical plan, section 3, feature 3).

Phase 0 storage is local disk, organized by creative_type, so folders in
the UI ("فيديو / صورة / كاروسيل") are a filter on that field rather than
real directories on the object store. Swap _write_local for an S3/R2
client later without touching the call site.

Downloading the actual creative (not just its metadata) only gets you a
real image/video file when media_url points straight at the asset, which
is true for a Google/TikTok scraper that reads an <img>/<video> src off
the page. Meta's ad_snapshot_url is a webpage, not the asset itself, so
until the snapshot-parsing follow-up in sources/meta.py lands, downloading
a Meta ad saves that page's HTML under the same name — still useful as a
record, just not the raw creative.
"""

from __future__ import annotations

import io
import json
import mimetypes
import os
import zipfile
from datetime import datetime
from typing import Optional

import requests
from sqlalchemy.orm import Session

from . import config
from .models import RawAd, SavedAd


def _fetch_media(media_url: str) -> Optional[tuple[bytes, str]]:
    try:
        resp = requests.get(media_url, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
    ext = mimetypes.guess_extension(content_type) or ".bin"
    return resp.content, ext


def _metadata(raw_ad: RawAd, media_path: Optional[str]) -> dict:
    return {
        "ad_id": raw_ad.ad_id,
        "platform": raw_ad.platform,
        "competitor": raw_ad.competitor.name,
        "creative_type": raw_ad.creative_type,
        "raw_text": raw_ad.raw_text,
        "media_url": raw_ad.media_url,
        "media_path": media_path,
        "first_seen": raw_ad.first_seen.isoformat(),
        "saved_at": datetime.utcnow().isoformat(),
    }


def save_ad(session: Session, raw_ad: RawAd, base_dir: str | None = None) -> SavedAd:
    existing = session.query(SavedAd).filter_by(raw_ad_id=raw_ad.id).one_or_none()
    if existing:
        return existing

    base_dir = base_dir or config.SWIPE_FILE_DIR
    folder = os.path.join(base_dir, raw_ad.competitor.name, raw_ad.creative_type)
    os.makedirs(folder, exist_ok=True)

    base_name = f"{raw_ad.platform}_{raw_ad.ad_id}"
    media_path = None
    if raw_ad.media_url:
        fetched = _fetch_media(raw_ad.media_url)
        if fetched:
            content, ext = fetched
            media_path = os.path.join(folder, base_name + ext)
            with open(media_path, "wb") as f:
                f.write(content)

    path = os.path.join(folder, base_name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_metadata(raw_ad, media_path), f, ensure_ascii=False, indent=2)

    saved = SavedAd(raw_ad_id=raw_ad.id, storage_path=path)
    session.add(saved)
    session.commit()
    return saved


def unsave_ad(session: Session, raw_ad_id: int) -> bool:
    existing = session.query(SavedAd).filter_by(raw_ad_id=raw_ad_id).one_or_none()
    if not existing:
        return False
    session.delete(existing)
    session.commit()
    return True


def build_export_zip(raw_ads: list[RawAd]) -> bytes:
    """Bulk-download entry point: one ad's media + metadata per zip entry."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for raw_ad in raw_ads:
            base_name = f"{raw_ad.platform}_{raw_ad.ad_id}"
            media_path = None
            if raw_ad.media_url:
                fetched = _fetch_media(raw_ad.media_url)
                if fetched:
                    content, ext = fetched
                    media_path = base_name + ext
                    zf.writestr(media_path, content)
            zf.writestr(
                base_name + ".json",
                json.dumps(_metadata(raw_ad, media_path), ensure_ascii=False, indent=2),
            )
    buffer.seek(0)
    return buffer.getvalue()
