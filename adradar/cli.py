import argparse

from . import classify as classify_mod
from . import queries
from .db import get_session, init_db
from .demo import seed_demo
from .ingest import ingest_competitor
from .models import Competitor
from .pipeline import run_pipeline
from .sources.meta import MetaAdLibraryClient, MetaAdLibraryError
from .swipe_file import save_ad


def cmd_init_db(_args):
    init_db()
    print("تم إنشاء الجداول.")


def cmd_add_competitor(args):
    session = get_session()
    existing = (
        session.query(Competitor)
        .filter_by(platform=args.platform, platform_page_id=args.page_id)
        .one_or_none()
    )
    if existing:
        print(f"المنافس موجود بالفعل: id={existing.id}")
        return
    comp = Competitor(name=args.name, platform=args.platform, platform_page_id=args.page_id)
    session.add(comp)
    session.commit()
    print(f"تمت إضافة المنافس: id={comp.id} name={comp.name}")


def cmd_ingest(args):
    session = get_session()
    client = MetaAdLibraryClient()
    if client.dry_run:
        print("(وضع تجريبي: لا يوجد META_ACCESS_TOKEN، سيتم استخدام بيانات وهمية)")

    q = session.query(Competitor).filter_by(platform="meta")
    if args.competitor_id:
        q = q.filter_by(id=args.competitor_id)
    competitors = q.all()

    if not competitors:
        print("لا يوجد منافسون مسجّلون على منصة meta. استخدم add-competitor أولاً.")
        return

    for comp in competitors:
        try:
            result = ingest_competitor(session, comp, client)
            print(result)
        except MetaAdLibraryError as e:
            print(f"فشل سحب بيانات {comp.name}: {e}")


def cmd_classify(_args):
    session = get_session()
    result = classify_mod.classify_unclassified(session)
    print(result)


def cmd_scan_failures(_args):
    session = get_session()
    print(queries.failure_scan(session))


def cmd_scan_trends(_args):
    session = get_session()
    print(queries.trend_alert_scan(session))


def cmd_save(args):
    session = get_session()
    from .models import RawAd

    ad = session.query(RawAd).filter_by(id=args.raw_ad_id).one_or_none()
    if not ad:
        print(f"لا يوجد إعلان بالمعرّف {args.raw_ad_id}")
        return
    saved = save_ad(session, ad)
    print(f"تم الحفظ في: {saved.storage_path}")


def cmd_seed_demo(_args):
    session = get_session()
    print(seed_demo(session))


def cmd_pipeline(_args):
    session = get_session()
    try:
        result = run_pipeline(session)
    finally:
        session.close()
    print(result)


def cmd_report(args):
    session = get_session()
    if args.kind == "longevity":
        for ad in queries.longevity_leaderboard(session):
            print(f"[id={ad.id}] {ad.competitor.name} — {ad.lifespan_days} يوم — {ad.raw_text[:60]}")
    elif args.kind == "failures":
        for f in queries.failure_log(session):
            print(f"[raw_ad_id={f.raw_ad_id}] عمر {f.lifespan_days} يوم — اختفى في {f.disappeared_at}")
    elif args.kind == "angles":
        for angle, pct in queries.angle_breakdown(session).items():
            print(f"{angle}: {pct}%")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adradar")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db").set_defaults(func=cmd_init_db)

    p = sub.add_parser("add-competitor")
    p.add_argument("--name", required=True)
    p.add_argument("--page-id", required=True)
    p.add_argument("--platform", default="meta")
    p.set_defaults(func=cmd_add_competitor)

    p = sub.add_parser("ingest")
    p.add_argument("--competitor-id", type=int, default=None)
    p.set_defaults(func=cmd_ingest)

    sub.add_parser("classify").set_defaults(func=cmd_classify)
    sub.add_parser("seed-demo").set_defaults(func=cmd_seed_demo)
    sub.add_parser("scan-failures").set_defaults(func=cmd_scan_failures)
    sub.add_parser("scan-trends").set_defaults(func=cmd_scan_trends)
    sub.add_parser("pipeline").set_defaults(func=cmd_pipeline)

    p = sub.add_parser("save")
    p.add_argument("raw_ad_id", type=int)
    p.set_defaults(func=cmd_save)

    p = sub.add_parser("report")
    p.add_argument("kind", choices=["longevity", "failures", "angles"])
    p.set_defaults(func=cmd_report)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
