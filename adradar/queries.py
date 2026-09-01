"""Feature queries derived from raw_ads — no extra tables needed beyond
failed_ads and alerts, which are logs written by the scan jobs below.
See technical plan, section 3, features 1, 4, 6.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import config
from .models import Alert, Classification, Competitor, FailedAd, RawAd, SavedAd


def longevity_leaderboard(session: Session, limit: int = 20) -> list[RawAd]:
    latest_seen = session.query(func.max(RawAd.last_seen)).scalar()
    if latest_seen is None:
        return []
    ads = session.query(RawAd).filter(RawAd.last_seen == latest_seen).all()
    ads.sort(key=lambda a: a.lifespan_days, reverse=True)
    return ads[:limit]


def failure_scan(session: Session, today: date | None = None) -> dict:
    today = today or date.today()
    cutoff = today - timedelta(days=config.FAILURE_ABSENCE_DAYS)

    already_flagged = {f.raw_ad_id for f in session.query(FailedAd.raw_ad_id).all()}
    candidates = (
        session.query(RawAd)
        .filter(RawAd.last_seen <= cutoff)
        .all()
    )

    flagged = 0
    for ad in candidates:
        if ad.id in already_flagged:
            continue
        if ad.lifespan_days >= config.FAILURE_MAX_LIFESPAN_DAYS:
            continue
        session.add(
            FailedAd(raw_ad_id=ad.id, lifespan_days=ad.lifespan_days, disappeared_at=ad.last_seen)
        )
        flagged += 1

    session.commit()
    return {"newly_flagged": flagged}


def failure_log(session: Session, limit: int = 50, include_dismissed: bool = False) -> list[FailedAd]:
    q = session.query(FailedAd)
    if not include_dismissed:
        q = q.filter(FailedAd.dismissed.is_(False))
    return q.order_by(FailedAd.flagged_at.desc()).limit(limit).all()


def dismiss_failure(session: Session, failed_ad_id: int) -> bool:
    row = session.query(FailedAd).filter_by(id=failed_ad_id).one_or_none()
    if not row:
        return False
    row.dismissed = True
    session.commit()
    return True


def trend_alert_scan(session: Session, today: date | None = None) -> dict:
    today = today or date.today()
    week_start = today - timedelta(days=7)
    baseline_start = today - timedelta(days=35)

    competitors = session.query(Competitor).all()
    created = 0
    for comp in competitors:
        current = (
            session.query(func.count(RawAd.id))
            .filter(
                RawAd.competitor_id == comp.id,
                RawAd.first_seen >= week_start,
                RawAd.first_seen < today,
            )
            .scalar()
            or 0
        )
        baseline_total = (
            session.query(func.count(RawAd.id))
            .filter(
                RawAd.competitor_id == comp.id,
                RawAd.first_seen >= baseline_start,
                RawAd.first_seen < week_start,
            )
            .scalar()
            or 0
        )
        baseline_avg = baseline_total / 4

        if baseline_avg > 0 and current >= baseline_avg * config.TREND_ALERT_MULTIPLIER:
            session.add(
                Alert(
                    competitor_id=comp.id,
                    type="volume_spike",
                    detail=f"{comp.name}: {current} إعلان جديد هذا الأسبوع مقابل متوسط {baseline_avg:.1f}",
                )
            )
            created += 1

    session.commit()
    return {"alerts_created": created}


def angle_breakdown(session: Session, competitor_id: int | None = None) -> dict:
    q = session.query(Classification.angle, func.count(Classification.id)).join(RawAd)
    if competitor_id is not None:
        q = q.filter(RawAd.competitor_id == competitor_id)
    counts = dict(q.group_by(Classification.angle).all())
    total = sum(counts.values())
    if total == 0:
        return {}
    return {angle: round(n / total * 100, 1) for angle, n in counts.items()}


def recent_alerts(session: Session, limit: int = 10) -> list[Alert]:
    return session.query(Alert).order_by(Alert.created_at.desc()).limit(limit).all()


def mark_alert_read(session: Session, alert_id: int) -> bool:
    row = session.query(Alert).filter_by(id=alert_id).one_or_none()
    if not row:
        return False
    row.read = True
    session.commit()
    return True


def saved_ads(session: Session, creative_type: str | None = None) -> list[SavedAd]:
    q = session.query(SavedAd).join(RawAd)
    if creative_type:
        q = q.filter(RawAd.creative_type == creative_type)
    return q.order_by(SavedAd.saved_at.desc()).all()


def saved_raw_ad_ids(session: Session) -> set[int]:
    return {row[0] for row in session.query(SavedAd.raw_ad_id).all()}


def campaign_timeline(session: Session) -> list[dict]:
    rows = (
        session.query(Competitor.id, Competitor.name, func.min(RawAd.first_seen))
        .join(RawAd, RawAd.competitor_id == Competitor.id)
        .group_by(Competitor.id, Competitor.name)
        .all()
    )
    return [{"competitor_id": cid, "name": name, "first_seen": first_seen} for cid, name, first_seen in rows]


def dashboard_stats(session: Session) -> dict:
    latest_seen = session.query(func.max(RawAd.last_seen)).scalar()
    active_ads = (
        session.query(func.count(RawAd.id)).filter(RawAd.last_seen == latest_seen).scalar()
        if latest_seen
        else 0
    )
    return {
        "competitors": session.query(func.count(Competitor.id)).scalar() or 0,
        "tracked_ads": session.query(func.count(RawAd.id)).scalar() or 0,
        "active_ads": active_ads or 0,
        "failed_ads": session.query(func.count(FailedAd.id)).filter(FailedAd.dismissed.is_(False)).scalar() or 0,
        "last_ingest": latest_seen,
    }
