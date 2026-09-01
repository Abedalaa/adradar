"""Meta Ad Library API client.

Docs: https://www.facebook.com/ads/library/api
Requires an access token from an app with Ad Library access approved.
With no token configured, `fetch_ads` returns fixture data so the rest
of the pipeline (ingest -> classify -> reports) can be exercised without
live credentials.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import requests

from .. import config

GRAPH_URL = "https://graph.facebook.com/v26.0/ads_archive"

# Each entry maps to one page_id's fixture set for dry-run mode. Ad ids are
# namespaced by page_id so two different competitors never collide on the
# same (platform, ad_id) — they used to, before every dry-run page returned
# the identical fx_001/002/003 ids, which corrupted multi-competitor demos.
# days_ago backdates first_seen on first ingest so a fresh demo already
# shows realistic "N يوم" longevity numbers instead of starting at zero.
_FIXTURE_SETS: dict[str, list[dict]] = {
    "demo_1": [
        {"ad_id": "d1_01", "raw_text": "باقي كمية محدودة من التخفيض الكبير — اطلب قبل النفاذ", "creative_type": "video", "days_ago": 62},
        {"ad_id": "d1_02", "raw_text": "خصم يصل إلى 40% على تشكيلة الخريف الجديدة", "creative_type": "carousel", "days_ago": 38},
        {"ad_id": "d1_03", "raw_text": "تجربتي الكاملة مع المنتج بعد شهر من الاستخدام", "creative_type": "video", "days_ago": 9},
    ],
    "demo_2": [
        {"ad_id": "d2_01", "raw_text": "شهادة حقيقية من عميلة استخدمت المنتج لمدة شهرين", "creative_type": "image", "days_ago": 47},
        {"ad_id": "d2_02", "raw_text": "قارن بنفسك: قبل وبعد استخدام المنتج", "creative_type": "image", "days_ago": 21},
        {"ad_id": "d2_03", "raw_text": "آخر فرصة قبل انتهاء العرض الليلة", "creative_type": "carousel", "days_ago": 5},
    ],
    "demo_3": [
        {"ad_id": "d3_01", "raw_text": "تعبان من نفس الروتين؟ جرب الحل في 7 أيام", "creative_type": "video", "days_ago": 29},
        {"ad_id": "d3_02", "raw_text": "عرض نهاية الأسبوع — خصم 25% على كل الطلبات", "creative_type": "image", "days_ago": 14},
        {"ad_id": "d3_03", "raw_text": "تعرف على فريقنا وقصة بداية المشروع", "creative_type": "image", "days_ago": 3},
    ],
}


class MetaAdLibraryError(Exception):
    """A clean, token-free error message from the Graph API."""


@dataclass
class MetaAd:
    ad_id: str
    raw_text: str
    creative_type: str
    media_url: str | None
    days_ago: int = 0


class MetaAdLibraryClient:
    def __init__(self, access_token: str | None = None) -> None:
        self.access_token = access_token or config.META_ACCESS_TOKEN
        self.dry_run = config.DEMO_MODE or not bool(self.access_token)

    def fetch_ads(self, page_id: str) -> list[MetaAd]:
        if self.dry_run:
            fixtures = _FIXTURE_SETS.get(page_id, _FIXTURE_SETS["demo_1"])
            return [
                MetaAd(
                    ad_id=f"{page_id}_{ad['ad_id']}",
                    raw_text=ad["raw_text"],
                    creative_type=ad["creative_type"],
                    media_url=f"https://example.com/snapshot/{page_id}_{ad['ad_id']}",
                    days_ago=ad.get("days_ago", 0),
                )
                for ad in fixtures
            ]
        return list(self._fetch_live(page_id))

    def _fetch_live(self, page_id: str):
        params = {
            "search_page_ids": json.dumps([page_id]),
            "ad_reached_countries": json.dumps(config.AD_REACHED_COUNTRIES),
            "ad_active_status": "ALL",
            "fields": "id,ad_creative_bodies,ad_delivery_start_time,ad_snapshot_url",
            "access_token": self.access_token,
            "limit": 100,
        }
        url = GRAPH_URL
        while url:
            resp = requests.get(url, params=params, timeout=30)
            try:
                payload = resp.json()
            except ValueError:
                # Response wasn't JSON at all (e.g. a proxy error page) — the
                # URL/token must never reach the exception message, so raise
                # on status alone rather than resp.raise_for_status(), which
                # would echo the full request URL including access_token.
                raise MetaAdLibraryError(f"Meta API returned HTTP {resp.status_code} with a non-JSON body")

            if "error" in payload:
                err = payload["error"]
                msg = err.get("error_user_msg") or err.get("message") or "Unknown Meta API error"
                raise MetaAdLibraryError(msg)

            for item in payload.get("data", []):
                bodies = item.get("ad_creative_bodies") or []
                yield MetaAd(
                    ad_id=item["id"],
                    raw_text=" ".join(bodies),
                    # The Ad Library API doesn't expose creative type directly;
                    # classifying image/video/carousel needs parsing ad_snapshot_url,
                    # left as a follow-up (see technical plan, section 3, feature 1).
                    creative_type="unknown",
                    media_url=item.get("ad_snapshot_url"),
                )
            next_url = payload.get("paging", {}).get("next")
            url = next_url
            params = {}  # next_url already carries the query string
