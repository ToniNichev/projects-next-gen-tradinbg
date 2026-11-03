"""Daily copy of the trade database (data/trading.db).

That database is the only record of which pot owns which money. The watchdog
calls maybe_backup() every 10 minutes; it makes at most one copy a day.

- Uses SQLite's own backup, so a copy taken while the bot writes is never
  half-written (copying the file could be).
- Saves backups/daily/trading-YYYY-MM-DD.db.gz and keeps the newest 14.
- Never includes .env (API keys).
- BOT_BACKUP_COPY_DIR (optional, .env): also put a copy there, e.g. a folder
  in iCloud Drive or on another disk, so a dead disk doesn't take both.

    ./venv/bin/python backup_db.py      # make one now
"""

import glob
import gzip
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "data", "trading.db")
BACKUP_DIR = os.path.join(ROOT, "backups", "daily")
KEEP = 14
EVERY_SECONDS = 24 * 3600


def _db_path():
    url = os.environ.get("BOT_DATABASE_URL", "")
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        return path if os.path.isabs(path) else os.path.join(ROOT, path)
    return DB_PATH


def latest(folder=BACKUP_DIR):
    files = sorted(glob.glob(os.path.join(folder, "trading-*.db.gz")))
    return files[-1] if files else None


def make_backup(db_path=None, folder=BACKUP_DIR, keep=KEEP, copy_dir=None) -> str:
    """Make one backup now. Returns its path. Raises on failure."""
    db_path = db_path or _db_path()
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"database not found: {db_path}")
    os.makedirs(folder, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    final = os.path.join(folder, f"trading-{stamp}.db.gz")
    raw = os.path.join(folder, f".trading-{stamp}.db.tmp")

    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    dst = sqlite3.connect(raw)
    try:
        src.backup(dst)
        ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise RuntimeError(f"backup failed its integrity check: {ok}")
    finally:
        dst.close()
        src.close()
    with open(raw, "rb") as fin, gzip.open(final + ".tmp", "wb") as fout:
        shutil.copyfileobj(fin, fout)
    os.replace(final + ".tmp", final)
    os.remove(raw)
    os.chmod(final, 0o600)

    for old in sorted(glob.glob(os.path.join(folder, "trading-*.db.gz")))[:-keep]:
        os.remove(old)

    copy_dir = copy_dir if copy_dir is not None else os.environ.get("BOT_BACKUP_COPY_DIR", "").strip()
    if copy_dir:
        os.makedirs(copy_dir, exist_ok=True)
        shutil.copy2(final, os.path.join(copy_dir, os.path.basename(final)))
        for old in sorted(glob.glob(os.path.join(copy_dir, "trading-*.db.gz")))[:-keep]:
            os.remove(old)
    return final


def maybe_backup(now=None, folder=BACKUP_DIR):
    """Back up if the newest copy is a day old (or missing).
    Returns (path or None, error text or None)."""
    now = now or time.time()
    last = latest(folder)
    if last and now - os.path.getmtime(last) < EVERY_SECONDS:
        return None, None
    try:
        return make_backup(folder=folder), None
    except Exception as exc:
        return None, str(exc)


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except Exception:
        pass
    path = make_backup()
    print(f"Backed up to {path} ({os.path.getsize(path) / 1e6:.1f} MB)")
    sys.exit(0)
