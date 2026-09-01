"""One-shot deployment check, run from cPanel > Setup Python App >
Execute python script (path: tools/diag.py).

It answers the question File Manager can't: is the code on disk the code
the dashboard is actually running? This process loads fresh from disk, so
anything it reports as correct while the dashboard still misbehaves means
Passenger is serving a stale in-memory copy, not that the file is wrong.
"""

import importlib.util
import inspect
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

print("=" * 60)
print("app root :", ROOT)
print("cwd      :", os.getcwd())
print("python   :", sys.version.split()[0])
print()

print("--- .env ---")
env_path = os.path.join(ROOT, ".env")
print("exists   :", os.path.exists(env_path))

from adradar import config  # noqa: E402

print("SYNC_TOKEN read      :", bool(os.getenv("SYNC_TOKEN", "").strip()))
print("DATABASE_URL         :", config.DATABASE_URL)
print("SCRAPE_COUNTRIES     :", config.SCRAPE_COUNTRIES)
print()

print("--- playwright ---")
spec = importlib.util.find_spec("playwright")
print("installed:", spec is not None, "->", getattr(spec, "origin", None))
print()

print("--- loaded modules ---")
from adradar import pipeline, web  # noqa: E402

for mod in (pipeline, web):
    path = mod.__file__
    age = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path)))
    print(f"{mod.__name__:22} {path}  (modified {age})")
print()

print("--- expected fixes present? ---")
pipeline_src = inspect.getsource(pipeline.run_pipeline)
web_src = inspect.getsource(web.create_app)
print("pipeline uses find_spec        :", "find_spec" in pipeline_src)
print("pipeline sets scrape_skipped   :", "scrape_skipped" in pipeline_src)
print("web flashes scrape_skipped     :", "scrape_skipped" in web_src)
print()

print("--- what run_pipeline would do ---")
if spec is None:
    print("playwright missing -> meta_scrape competitors SKIPPED with a notice")
else:
    print("playwright present -> meta_scrape competitors WILL be scraped")
print("=" * 60)
