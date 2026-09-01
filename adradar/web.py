from __future__ import annotations

import io
import os

from flask import Flask, flash, get_flashed_messages, redirect, request, render_template, send_file, url_for

from . import classify as classify_mod
from . import queries
from .db import get_session, init_db
from .models import Competitor, RawAd
from .pipeline import run_pipeline
from .sources.meta import MetaAdLibraryClient
from .swipe_file import build_export_zip, save_ad, unsave_ad
from .utils import is_numeric_page_id, parse_page_id


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "adradar-local-dev")
    init_db()

    def common_context() -> dict:
        client = MetaAdLibraryClient()
        return {
            "dry_run": client.dry_run,
            "flashed": get_flashed_messages(),
            "angle_labels": classify_mod.ANGLE_LABELS_AR,
        }

    def safe_redirect(default_endpoint: str = "overview"):
        target = request.form.get("next") or request.args.get("next")
        if target and target.startswith("/"):
            return redirect(target)
        return redirect(url_for(default_endpoint))

    @app.route("/")
    def overview():
        session = get_session()
        try:
            ctx = common_context()
            ctx.update(
                stats=queries.dashboard_stats(session),
                longevity=queries.longevity_leaderboard(session, limit=5),
                alerts=queries.recent_alerts(session, limit=4),
                failures=queries.failure_log(session, limit=4),
            )
            return render_template("overview.html", **ctx)
        finally:
            session.close()

    @app.route("/longevity")
    def longevity():
        session = get_session()
        try:
            ctx = common_context()
            ctx.update(
                ads=queries.longevity_leaderboard(session, limit=200),
                saved_ids=queries.saved_raw_ad_ids(session),
            )
            return render_template("longevity.html", **ctx)
        finally:
            session.close()

    @app.route("/angles")
    def angles():
        session = get_session()
        try:
            competitor_raw = request.args.get("competitor", "").strip()
            competitor_id = int(competitor_raw) if competitor_raw.isdigit() else None
            ctx = common_context()
            ctx.update(
                competitors=session.query(Competitor).order_by(Competitor.name).all(),
                selected_competitor=competitor_id,
                breakdown=queries.angle_breakdown(session, competitor_id=competitor_id),
            )
            return render_template("angles.html", **ctx)
        finally:
            session.close()

    @app.route("/swipe")
    def swipe():
        session = get_session()
        try:
            active_type = request.args.get("type") or None
            ctx = common_context()
            ctx.update(
                items=queries.saved_ads(session, creative_type=active_type),
                active_type=active_type,
            )
            return render_template("swipe.html", **ctx)
        finally:
            session.close()

    @app.route("/alerts")
    def alerts():
        session = get_session()
        try:
            ctx = common_context()
            ctx.update(alerts=queries.recent_alerts(session, limit=100))
            return render_template("alerts.html", **ctx)
        finally:
            session.close()

    @app.route("/calendar")
    def calendar():
        session = get_session()
        try:
            from datetime import date as date_cls

            month_names = [
                "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
                "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
            ]
            rows = []
            for row in queries.campaign_timeline(session):
                fs = row["first_seen"]
                day_of_year = (fs - date_cls(fs.year, 1, 1)).days
                pct = round(day_of_year / 365 * 100, 1)
                rows.append(
                    {
                        "name": row["name"],
                        "pct": pct,
                        "date_label": f"{fs.day} {month_names[fs.month - 1]}",
                    }
                )
            ctx = common_context()
            ctx.update(rows=rows)
            return render_template("calendar.html", **ctx)
        finally:
            session.close()

    @app.route("/failures")
    def failures():
        session = get_session()
        try:
            ctx = common_context()
            ctx.update(failures=queries.failure_log(session, limit=100))
            return render_template("failures.html", **ctx)
        finally:
            session.close()

    @app.route("/competitors")
    def competitors_page():
        session = get_session()
        try:
            ctx = common_context()
            ctx.update(competitors=session.query(Competitor).order_by(Competitor.name).all())
            return render_template("competitors.html", **ctx)
        finally:
            session.close()

    @app.route("/competitors", methods=["POST"])
    def add_competitor():
        session = get_session()
        try:
            name = request.form.get("name", "").strip()
            platform = request.form.get("platform", "meta").strip()
            raw_page_id = request.form.get("page_id", "")

            if platform == "meta_scrape":
                # The scraper searches by the Page's exact display name, not a numeric id.
                page_id = raw_page_id.strip()
                if not name or not page_id:
                    return redirect(url_for("competitors_page"))
            else:
                platform = "meta"
                page_id = parse_page_id(raw_page_id)
                if not is_numeric_page_id(page_id):
                    flash(f'"{page_id}" مش رقم — Ad Library محتاج معرّف الصفحة الرقمي، مش الاسم المخصص.')
                    return redirect(url_for("competitors_page"))

            if name and page_id:
                exists = (
                    session.query(Competitor)
                    .filter_by(platform=platform, platform_page_id=page_id)
                    .one_or_none()
                )
                if not exists:
                    session.add(Competitor(name=name, platform=platform, platform_page_id=page_id))
                    session.commit()
        finally:
            session.close()
        return redirect(url_for("competitors_page"))

    @app.route("/competitors/<int:competitor_id>/delete", methods=["POST"])
    def delete_competitor(competitor_id):
        session = get_session()
        try:
            comp = session.query(Competitor).filter_by(id=competitor_id).one_or_none()
            if comp:
                if comp.raw_ads:
                    flash(f'مش هينحذف "{comp.name}" — عنده إعلانات متتبَّعة بالفعل، بلاش نسيب بيانات يتيمة.')
                else:
                    session.delete(comp)
                    session.commit()
        finally:
            session.close()
        return redirect(url_for("competitors_page"))

    @app.route("/refresh", methods=["POST"])
    def refresh():
        session = get_session()
        try:
            result = run_pipeline(session)
            for err in result["ingest_errors"]:
                flash(f"فشل تحديث {err['competitor']}: {err['error']}")
        finally:
            session.close()
        return safe_redirect()

    @app.route("/ads/<int:raw_ad_id>/save", methods=["POST"])
    def save_ad_route(raw_ad_id):
        session = get_session()
        try:
            ad = session.query(RawAd).filter_by(id=raw_ad_id).one_or_none()
            if ad:
                save_ad(session, ad)
        finally:
            session.close()
        return safe_redirect()

    @app.route("/ads/<int:raw_ad_id>/unsave", methods=["POST"])
    def unsave(raw_ad_id):
        session = get_session()
        try:
            unsave_ad(session, raw_ad_id)
        finally:
            session.close()
        return safe_redirect("swipe")

    @app.route("/ads/<int:raw_ad_id>/download")
    def download_one(raw_ad_id):
        session = get_session()
        try:
            ad = session.query(RawAd).filter_by(id=raw_ad_id).one_or_none()
            if not ad:
                return safe_redirect()
            zip_bytes = build_export_zip([ad])
        finally:
            session.close()
        return send_file(
            io.BytesIO(zip_bytes),
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"adradar_{ad.platform}_{ad.ad_id}.zip",
        )

    @app.route("/download", methods=["POST"])
    def download():
        session = get_session()
        try:
            ids = [int(x) for x in request.form.getlist("raw_ad_ids") if x.isdigit()]
            if not ids:
                return safe_redirect()
            ads = session.query(RawAd).filter(RawAd.id.in_(ids)).all()
            zip_bytes = build_export_zip(ads)
        finally:
            session.close()
        return send_file(
            io.BytesIO(zip_bytes),
            mimetype="application/zip",
            as_attachment=True,
            download_name="adradar_export.zip",
        )

    @app.route("/alerts/<int:alert_id>/read", methods=["POST"])
    def mark_read(alert_id):
        session = get_session()
        try:
            queries.mark_alert_read(session, alert_id)
        finally:
            session.close()
        return safe_redirect("alerts")

    @app.route("/failures/<int:failed_ad_id>/dismiss", methods=["POST"])
    def dismiss(failed_ad_id):
        session = get_session()
        try:
            queries.dismiss_failure(session, failed_ad_id)
        finally:
            session.close()
        return safe_redirect("failures")

    return app

