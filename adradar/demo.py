"""Seeds a realistic demo dataset through the real pipeline.

Runs the actual ingest -> classify -> failure-scan code paths against the
built-in dry-run fixtures (see sources/meta.py), so a demo shows genuine
app behavior rather than a hand-faked screen. The only two things it adds
directly are failed ads and trend alerts: both describe things that
happened *before* the demo started (an ad that already disappeared, a
volume spike from last week) which a single fresh seeding run has no real
history to produce on its own.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import queries
from .classify import classify_unclassified
from .ingest import ingest_competitor
from .models import Alert, Competitor, RawAd
from .sources.meta import MetaAdLibraryClient

_COMPETITORS = [
    {"name": "متجر لمسة", "page_id": "demo_1"},
    {"name": "بيوتي هب", "page_id": "demo_2"},
    {"name": "فاست فيت", "page_id": "demo_3"},
]

_STALE_ADS = [
    # days_ago_seen must clear config.FAILURE_ABSENCE_DAYS (3) or failure_scan
    # won't flag it yet — it's still within the "might just be paused" window.
    {"page_id": "demo_2", "ad_id": "d2_99", "text": "عرض نهاية الأسبوع الفائت — خصم سريع", "type": "image", "days_ago_seen": 3, "lifespan": 2},
    {"page_id": "demo_1", "ad_id": "d1_99", "text": "بوست تعريفي عن المنتج الجديد", "type": "image", "days_ago_seen": 4, "lifespan": 1},
    {"page_id": "demo_3", "ad_id": "d3_99", "text": "قارن الأسعار بنفسك قبل الطلب", "type": "video", "days_ago_seen": 5, "lifespan": 3},
]

_ALERTS = [
    ("فاست فيت", "فاست فيت: 11 إعلان جديد هذا الأسبوع مقابل متوسط 3.2"),
    ("متجر لمسة", "متجر لمسة: أول ظهور لعرض موسمي جديد"),
]


def seed_demo(session: Session) -> dict:
    client = MetaAdLibraryClient()
    client.dry_run = True  # always fixtures for a demo, regardless of .env token state
    competitors = {}
    for c in _COMPETITORS:
        comp = (
            session.query(Competitor)
            .filter_by(platform="meta", platform_page_id=c["page_id"])
            .one_or_none()
        )
        if comp is None:
            comp = Competitor(name=c["name"], platform="meta", platform_page_id=c["page_id"])
            session.add(comp)
            session.commit()
        competitors[c["page_id"]] = comp

    for comp in competitors.values():
        ingest_competitor(session, comp, client)

    today = date.today()
    for stale in _STALE_ADS:
        comp = competitors[stale["page_id"]]
        exists = session.query(RawAd).filter_by(platform="meta", ad_id=stale["ad_id"]).one_or_none()
        if exists is None:
            last_seen = today - timedelta(days=stale["days_ago_seen"])
            session.add(
                RawAd(
                    platform="meta",
                    ad_id=stale["ad_id"],
                    competitor_id=comp.id,
                    creative_type=stale["type"],
                    raw_text=stale["text"],
                    media_url=f"https://example.com/snapshot/{stale['ad_id']}",
                    first_seen=last_seen - timedelta(days=stale["lifespan"]),
                    last_seen=last_seen,
                )
            )
    session.commit()

    classify_unclassified(session)
    queries.failure_scan(session)

    if session.query(Alert).count() == 0:
        for comp_name, detail in _ALERTS:
            comp = next(c for c in competitors.values() if c.name == comp_name)
            session.add(Alert(competitor_id=comp.id, type="volume_spike", detail=detail))
        session.commit()

    return {
        "competitors": len(competitors),
        "raw_ads": session.query(RawAd).count(),
        "alerts": session.query(Alert).count(),
    }
