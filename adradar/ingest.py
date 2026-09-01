"""Daily ingest job: pull ads for one competitor, upsert into raw_ads.

first_seen is set once, on first observation. last_seen is bumped every
run an ad is still returned by the source. Ads that stop appearing simply
stop getting their last_seen bumped -- that gap is what the failure scan
in queries.py looks for.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from .models import Competitor, RawAd
from .sources.meta import MetaAdLibraryClient


def ingest_competitor(
    session: Session, competitor: Competitor, client: MetaAdLibraryClient, today: date | None = None
) -> dict:
    today = today or date.today()
    ads = client.fetch_ads(competitor.platform_page_id)

    created, updated = 0, 0
    for ad in ads:
        existing = (
            session.query(RawAd)
            .filter_by(platform=competitor.platform, ad_id=ad.ad_id)
            .one_or_none()
        )
        if existing is None:
            first_seen = today - timedelta(days=getattr(ad, "days_ago", 0) or 0)
            session.add(
                RawAd(
                    platform=competitor.platform,
                    ad_id=ad.ad_id,
                    competitor_id=competitor.id,
                    creative_type=ad.creative_type,
                    raw_text=ad.raw_text,
                    media_url=ad.media_url,
                    first_seen=first_seen,
                    last_seen=today,
                )
            )
            created += 1
        else:
            existing.last_seen = today
            updated += 1

    session.commit()
    return {"competitor": competitor.name, "created": created, "updated": updated, "total_seen": len(ads)}
