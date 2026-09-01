"""Meta Ad Library — public-website scraper (fallback when the official
Ad Library API isn't authorized on the app yet, or you'd rather not wait
on App Review at all).

Reads the same public page anyone can browse at facebook.com/ads/library.
Two things had to be verified by hand before trusting this, both real
failure modes caught during testing, not hypothetical:

1. The site renders in whatever locale the browser reports — an
   unconfigured headless browser got served Arabic UI, silently breaking
   every English-text-based match below. The browser context is pinned
   to en-US for exactly this reason.
2. A keyword/advertiser search is NOT scoped to one page — searching
   "Vodafone Egypt" also returned ads from "Top casino" and "Let's
   English" (unrelated advertisers whose ads or metadata loosely matched
   the query). Every card's advertiser name is extracted and compared
   against the expected name; anything that doesn't match is dropped
   rather than silently attributed to the wrong competitor.

The DOM itself uses Facebook's generated atomic CSS classes (they change
on every build), so extraction is text-pattern based against the label
sequence Meta renders for every ad card, which is far more stable:

    [Active|Inactive] Library ID: <id> Started running on <date>
    Platforms ... See ad details <Advertiser> Sponsored <ad text> [duration]

If Meta changes that wording, this breaks loudly (empty results) rather
than silently. Same risk profile as any scraper otherwise: fragile to
markup changes, subject to bot detection / rate limiting, and outside
the Ad Library API's terms of service — use it deliberately.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional
from urllib.parse import quote

LIBRARY_URL = "https://www.facebook.com/ads/library/"

_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Runs inside the page via page.evaluate — pulls every ad card's raw text
# and a media-type guess in one pass instead of round-tripping per card.
_EXTRACT_JS = r"""
() => {
  function clean(s) { return s.replace(/​/g, ''); }
  const idNodes = Array.from(document.querySelectorAll('*')).filter(
    el => el.children.length === 0 && clean(el.textContent).trim().startsWith('Library ID:')
  );
  return idNodes.map(idNode => {
    let el = idNode;
    for (let i = 0; i < 15; i++) {
      if (!el.parentElement) break;
      el = el.parentElement;
      if (clean(el.textContent).includes('Sponsored')) break;
    }
    const hasVideo = !!el.querySelector('video');
    const imgCount = el.querySelectorAll('img[referrerpolicy]').length;
    return { text: clean(el.textContent), hasVideo, imgCount };
  });
}
"""


@dataclass
class ScrapedAd:
    ad_id: str
    raw_text: str
    creative_type: str
    media_url: Optional[str]
    days_ago: int
    is_active: bool
    advertiser: str


def _parse_started(text: str) -> Optional[date]:
    m = re.search(r"Started running on ([^P]+?)Platforms", text)
    if not m:
        return None
    parts = m.group(1).strip().split()
    if len(parts) != 3:
        return None
    day, mon, year = parts
    month_num = _MONTHS.get(mon[:3])
    if not month_num:
        return None
    try:
        return date(int(year), month_num, int(day))
    except ValueError:
        return None


def _parse_card(raw: dict) -> Optional[ScrapedAd]:
    text = raw["text"]
    id_match = re.search(r"Library ID: (\d+)", text)
    if not id_match:
        return None
    library_id = id_match.group(1)

    advertiser_match = re.search(r"See ad details(.+?)Sponsored", text, re.DOTALL)
    advertiser = advertiser_match.group(1).strip() if advertiser_match else ""

    started = _parse_started(text)
    days_ago = (date.today() - started).days if started else 0

    ad_text_match = re.search(r"Sponsored(.+)", text, re.DOTALL)
    ad_text = ad_text_match.group(1) if ad_text_match else ""
    # Strip trailing UI chrome: a video duration ("0:00 / 3:02") and
    # anything after it (repeated advertiser name, "See details", ...).
    ad_text = re.sub(r"\d+:\d{2}\s*/\s*\d+:\d{2}.*$", "", ad_text, flags=re.DOTALL).strip()

    if raw["hasVideo"]:
        creative_type = "video"
    elif raw["imgCount"] > 1:
        creative_type = "carousel"
    elif raw["imgCount"] == 1:
        creative_type = "image"
    else:
        creative_type = "unknown"

    return ScrapedAd(
        ad_id=library_id,
        raw_text=ad_text,
        creative_type=creative_type,
        media_url=f"https://www.facebook.com/ads/library/?id={library_id}",
        days_ago=days_ago,
        is_active=text.startswith("Active"),
        advertiser=advertiser,
    )


class MetaScraperClient:
    """fetch_ads(query) takes the advertiser's exact Page name (not a
    numeric id — view_all_page_id lookups proved unreliable in testing),
    searches the public Ad Library for it, and keeps only cards whose
    advertiser name matches that query — see the module docstring for
    why that filter is load-bearing, not defensive paranoia.
    """

    def __init__(
        self,
        countries: Optional[list[str]] = None,
        headless: bool = True,
        scroll_rounds: int = 4,
    ) -> None:
        from .. import config as _config  # local import avoids a config->scraper->config cycle

        self.countries = countries or _config.SCRAPE_COUNTRIES
        self.headless = headless
        self.scroll_rounds = scroll_rounds
        self.dry_run = False

    def fetch_ads(self, query: str):
        from .meta import MetaAd  # local import: keeps Playwright optional for API-only users

        scraped = self._scrape(query)
        return [
            MetaAd(
                ad_id=ad.ad_id,
                raw_text=ad.raw_text,
                creative_type=ad.creative_type,
                media_url=ad.media_url,
                days_ago=ad.days_ago,
            )
            for ad in scraped
        ]

    def _scrape(self, query: str) -> list[ScrapedAd]:
        from playwright.sync_api import sync_playwright

        query_norm = query.strip().lower()
        ads: list[ScrapedAd] = []
        seen_ids = set()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            try:
                for country in self.countries:
                    raw_cards = self._scrape_one_country(browser, query, country)
                    for raw in raw_cards:
                        parsed = _parse_card(raw)
                        if not parsed or parsed.ad_id in seen_ids:
                            continue
                        if parsed.advertiser.strip().lower() != query_norm:
                            continue
                        seen_ids.add(parsed.ad_id)
                        ads.append(parsed)
            finally:
                browser.close()

        return ads

    def _scrape_one_country(self, browser, query: str, country: str) -> list[dict]:
        url = (
            f"{LIBRARY_URL}?active_status=all&ad_type=all&country={country}"
            f"&q={quote(query)}&search_type=page"
        )
        context = browser.new_context(locale="en-US")
        page = context.new_page()
        try:
            page.goto(url, timeout=45_000, wait_until="domcontentloaded")
            page.wait_for_timeout(2_000)
            for _ in range(self.scroll_rounds):
                page.mouse.wheel(0, 4000)
                page.wait_for_timeout(1_200)
            return page.evaluate(_EXTRACT_JS)
        finally:
            context.close()
