"""Entry point for cPanel's "Setup Python App" (Phusion Passenger).

Passenger imports this file and looks for a WSGI callable named
`application` — unlike gunicorn (deploy/adradar-web.service), which is
pointed at wsgi.py:app explicitly. Both wrap the same create_app().

The sys.path insert makes the import work regardless of the working
directory Passenger happens to start us in.
"""

import os
import sys

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

# SQLite's default relative path (sqlite:///adradar.db) resolves against
# the current working directory, which Passenger doesn't guarantee — pin
# it to the app root so the dashboard and the cron pipeline always open
# the same file.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(APP_ROOT, 'adradar.db')}")

from adradar.web import create_app  # noqa: E402

application = create_app()
