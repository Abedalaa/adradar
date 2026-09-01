"""Round-trips adradar.db between the live site and a CI runner over HTTPS.

Why the round trip matters: RawAd.first_seen is written once, on an ad's
first observation, and every longevity and failure number is derived from
it. A pipeline run starting from an empty database would reset that
history each time, so the runner pulls the live database, appends to it,
and pushes it back.

Why HTTPS and not FTP: the shared host firewalls port 21 off from outside
(it timed out from a GitHub runner and answers only intermittently even
from a home connection), while 443 serves the dashboard reliably. The
matching endpoint lives in adradar/web.py as /sync/db.
"""

import os
import sys

import requests

BASE_URL = os.environ["SYNC_URL"].rstrip("/")
TOKEN = os.environ["SYNC_TOKEN"]
LOCAL_PATH = os.environ.get("LOCAL_DB", "adradar.db")
TIMEOUT = 120


def _headers() -> dict:
    return {"X-Sync-Token": TOKEN}


def download() -> None:
    resp = requests.get(f"{BASE_URL}/sync/db", headers=_headers(), timeout=TIMEOUT)

    if resp.status_code == 404:
        sys.exit(
            "404 from /sync/db — either SYNC_TOKEN doesn't match the server's, "
            "or the server has none set. Both must match; restart the app after "
            "editing .env."
        )
    resp.raise_for_status()

    if resp.status_code == 204 or not resp.content:
        # Server has no database yet. Leave nothing behind, so the pipeline
        # builds a fresh one and upload publishes it.
        if os.path.exists(LOCAL_PATH):
            os.remove(LOCAL_PATH)
        print("no remote database yet — starting fresh")
        return

    with open(LOCAL_PATH, "wb") as f:
        f.write(resp.content)
    print(f"downloaded {len(resp.content)} bytes -> {LOCAL_PATH}")


def upload() -> None:
    if not os.path.exists(LOCAL_PATH):
        sys.exit(f"{LOCAL_PATH} does not exist — the pipeline produced nothing to upload")

    with open(LOCAL_PATH, "rb") as f:
        payload = f.read()

    resp = requests.post(
        f"{BASE_URL}/sync/db",
        headers={**_headers(), "Content-Type": "application/octet-stream"},
        data=payload,
        timeout=TIMEOUT,
    )
    if resp.status_code == 404:
        sys.exit("404 from /sync/db — SYNC_TOKEN mismatch (see download() note)")
    resp.raise_for_status()
    print(f"uploaded {len(payload)} bytes -> {BASE_URL} ({resp.text.strip()})")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "download":
        download()
    elif action == "upload":
        upload()
    else:
        sys.exit("usage: sync_db.py [download|upload]")
