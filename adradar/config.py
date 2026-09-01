import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///adradar.db")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
AD_REACHED_COUNTRIES = [
    c.strip() for c in os.getenv("AD_REACHED_COUNTRIES", "US").split(",") if c.strip()
]
SWIPE_FILE_DIR = os.getenv("SWIPE_FILE_DIR", "./swipe_file")

# Countries the Meta Ad Library *scraper* searches in (adradar/sources/meta_scraper.py).
# Separate from AD_REACHED_COUNTRIES, which is the official API's filter.
# Meta's country selector doesn't accept a combined value (comma-separated
# country=IL,PS silently falls back to a default) — the scraper runs one
# full search per country and merges results, so list every country a
# tracked page might be geo-classified under (Hebron/West Bank pages have
# shown up under both "Israel" and "Palestine" on Meta's own Page info).
SCRAPE_COUNTRIES = [
    c.strip() for c in os.getenv("SCRAPE_COUNTRIES", os.getenv("SCRAPE_COUNTRY", "EG")).split(",") if c.strip()
]

# When set, MetaAdLibraryClient always returns fixture data, even if a real
# META_ACCESS_TOKEN is configured — used to run a guaranteed-to-work demo
# without depending on live API access. See Demo.command / adradar/demo.py.
DEMO_MODE = os.getenv("ADRADAR_DEMO", "").strip().lower() in ("1", "true", "yes")

# Feature-log thresholds (see AdRadar technical plan, section 3).
FAILURE_MAX_LIFESPAN_DAYS = 5
FAILURE_ABSENCE_DAYS = 3
TREND_ALERT_MULTIPLIER = 3.0
