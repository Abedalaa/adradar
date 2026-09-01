"""The full ingest -> classify -> scan cycle, run as one unit.

Used by the CLI's `pipeline` command (for cron/systemd) and the web
dashboard's refresh button, so both stay in sync with one code path.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import classify as classify_mod
from . import queries
from .ingest import ingest_competitor
from .models import Competitor
from .sources.meta import MetaAdLibraryClient, MetaAdLibraryError


def _scraper_client():
    # Imported lazily: playwright is an optional dependency, only needed
    # by accounts actually using the "meta_scrape" platform.
    from .sources.meta_scraper import MetaScraperClient

    return MetaScraperClient()  # countries default to config.SCRAPE_COUNTRIES


def run_pipeline(session: Session) -> dict:
    ingested, failed = [], []

    meta_client = MetaAdLibraryClient()
    for comp in session.query(Competitor).filter_by(platform="meta").all():
        try:
            ingested.append(ingest_competitor(session, comp, meta_client))
        except MetaAdLibraryError as e:
            failed.append({"competitor": comp.name, "error": str(e)})

    scrape_competitors = session.query(Competitor).filter_by(platform="meta_scrape").all()
    scrape_skipped = None
    if scrape_competitors:
        # Playwright is only imported here — a plain "meta" (API) setup
        # never needs it installed.
        try:
            scrape_client = _scraper_client()
        except ImportError:
            # Expected on shared hosting, which can't install Playwright or
            # a browser: the dashboard runs there, the scraper runs in CI
            # (.github/workflows/pipeline.yml). Report this once, as a
            # status line, rather than as one alarming failure per
            # competitor — nothing here is actually broken.
            scrape_client = None
            scrape_skipped = (
                f"تم تخطي {len(scrape_competitors)} منافس (سحب من مكتبة الإعلانات) — "
                "بيتحدّثوا تلقائياً كل 12 ساعة من GitHub Actions، مش من السيرفر ده."
            )

        if scrape_client is not None:
            for comp in scrape_competitors:
                try:
                    ingested.append(ingest_competitor(session, comp, scrape_client))
                except Exception as e:  # scraper failures aren't a typed exception yet
                    failed.append({"competitor": comp.name, "error": f"فشل السحب: {e}"})

    classify_result = classify_mod.classify_unclassified(session)
    failure_result = queries.failure_scan(session)
    trend_result = queries.trend_alert_scan(session)

    return {
        "dry_run": meta_client.dry_run,
        "ingested": ingested,
        "ingest_errors": failed,
        "scrape_skipped": scrape_skipped,
        "classify": classify_result,
        "failure_scan": failure_result,
        "trend_scan": trend_result,
    }
