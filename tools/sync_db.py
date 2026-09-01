"""Round-trips adradar.db between the cPanel host and a CI runner over FTP.

Why the round trip matters: RawAd.first_seen is written once, on an ad's
first observation, and every longevity/failure number is derived from it.
A pipeline run that starts from an empty database would reset that history
on every run, so the runner must pull the live database, append to it, and
push it back.

Missing remote file is treated as "first run": download exits quietly and
the pipeline builds a fresh database, which upload then publishes.
"""

import os
import ssl
import sys
from ftplib import FTP, FTP_TLS, error_perm

HOST = os.environ["FTP_HOST"]
USER = os.environ["FTP_USER"]
PASSWORD = os.environ["FTP_PASS"]
# Directory on the server holding adradar.db, e.g. /adradar.dreamers.cv
REMOTE_DIR = os.environ.get("FTP_DIR", "/adradar.dreamers.cv")
REMOTE_NAME = os.environ.get("FTP_DB_NAME", "adradar.db")
LOCAL_PATH = os.environ.get("LOCAL_DB", "adradar.db")


def connect():
    """Explicit FTPS if the server offers it, plain FTP otherwise.

    Shared hosts vary: some require TLS, some present a certificate that
    fails verification, some only speak plain FTP. Trying in this order
    keeps credentials encrypted whenever the server allows it.
    """
    try:
        ftp = FTP_TLS(context=ssl._create_unverified_context())
        ftp.connect(HOST, 21, timeout=60)
        ftp.login(USER, PASSWORD)
        ftp.prot_p()
        print("connected: FTPS")
    except Exception as e:
        print(f"FTPS unavailable ({e}) — falling back to plain FTP")
        ftp = FTP()
        ftp.connect(HOST, 21, timeout=60)
        ftp.login(USER, PASSWORD)
        print("connected: FTP")
    ftp.set_pasv(True)
    ftp.cwd(REMOTE_DIR)
    return ftp


def download():
    ftp = connect()
    try:
        with open(LOCAL_PATH, "wb") as f:
            ftp.retrbinary(f"RETR {REMOTE_NAME}", f.write)
        print(f"downloaded {REMOTE_NAME} -> {LOCAL_PATH} ({os.path.getsize(LOCAL_PATH)} bytes)")
    except error_perm as e:
        # 550 = no such file. Anything else is a real problem worth failing on.
        if not str(e).startswith("550"):
            raise
        if os.path.exists(LOCAL_PATH):
            os.remove(LOCAL_PATH)
        print("no remote database yet — starting fresh")
    finally:
        ftp.quit()


def upload():
    if not os.path.exists(LOCAL_PATH):
        sys.exit(f"{LOCAL_PATH} does not exist — the pipeline produced nothing to upload")

    ftp = connect()
    try:
        # Upload to a temp name, then rename over the live file, so a
        # dashboard request mid-transfer never reads a half-written database.
        tmp_name = REMOTE_NAME + ".uploading"
        with open(LOCAL_PATH, "rb") as f:
            ftp.storbinary(f"STOR {tmp_name}", f)
        try:
            ftp.delete(REMOTE_NAME)
        except error_perm:
            pass
        ftp.rename(tmp_name, REMOTE_NAME)
        print(f"uploaded {LOCAL_PATH} -> {REMOTE_DIR}/{REMOTE_NAME} ({os.path.getsize(LOCAL_PATH)} bytes)")
    finally:
        ftp.quit()


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "download":
        download()
    elif action == "upload":
        upload()
    else:
        sys.exit("usage: sync_db.py [download|upload]")
