"""Daily database backup: a consistent copy, at most one a day, 14 kept."""

import gzip
import os
import sqlite3

import backup_db


def make_db(path):
    con = sqlite3.connect(path)
    con.execute("create table trades (id integer primary key, side text)")
    con.executemany("insert into trades (side) values (?)", [("buy",), ("sell",)])
    con.commit()
    return con


def test_backup_is_a_readable_copy(tmp_path):
    db = tmp_path / "trading.db"
    con = make_db(db)          # left open, as when the bot is running
    out = backup_db.make_backup(str(db), folder=str(tmp_path / "b"), copy_dir=str(tmp_path / "c"))
    con.close()
    restored = tmp_path / "restored.db"
    with gzip.open(out) as fin, open(restored, "wb") as fout:
        fout.write(fin.read())
    rows = sqlite3.connect(restored).execute("select side from trades order by id").fetchall()
    assert rows == [("buy",), ("sell",)]
    assert oct(os.stat(out).st_mode & 0o777) == "0o600"
    assert os.listdir(tmp_path / "c") == [os.path.basename(out)]


def test_keeps_only_the_newest(tmp_path):
    folder = tmp_path / "b"
    folder.mkdir()
    for d in range(1, 20):
        (folder / f"trading-2026-10-{d:02d}.db.gz").write_bytes(b"x")
    db = tmp_path / "trading.db"
    make_db(db).close()
    backup_db.make_backup(str(db), folder=str(folder), keep=14, copy_dir="")
    names = sorted(os.listdir(folder))
    assert len(names) == 14 and names[0] == "trading-2026-10-07.db.gz"


def test_at_most_once_a_day(tmp_path, monkeypatch):
    folder = tmp_path / "b"
    db = tmp_path / "trading.db"
    make_db(db).close()
    monkeypatch.setattr(backup_db, "_db_path", lambda: str(db))
    monkeypatch.setenv("BOT_BACKUP_COPY_DIR", "")
    path, err = backup_db.maybe_backup(folder=str(folder))
    assert path and err is None
    assert backup_db.maybe_backup(folder=str(folder)) == (None, None)
