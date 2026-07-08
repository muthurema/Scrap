"""SQLite persistence layer: cameras, violations and app settings."""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

DATA_DIR = os.environ.get("SAFETYWATCH_DATA", "data")
DB_PATH = os.path.join(DATA_DIR, "safetywatch.db")
SNAPSHOT_DIR = os.path.join(DATA_DIR, "snapshots")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cameras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location TEXT DEFAULT '',
    source TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'rtsp',
    enabled INTEGER NOT NULL DEFAULT 1,
    zone_json TEXT DEFAULT '{}',
    last_status TEXT DEFAULT 'never_tested',
    last_verified_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL,
    camera_name TEXT NOT NULL,
    vtype TEXT NOT NULL,
    message TEXT NOT NULL,
    confidence REAL DEFAULT 0,
    snapshot_path TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (camera_id) REFERENCES cameras (id)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


@contextmanager
def _conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db():
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with _conn() as con:
        con.executescript(_SCHEMA)


def _now():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- cameras
def add_camera(name, source, source_type="rtsp", location="", enabled=True, zone=None):
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO cameras (name, location, source, source_type, enabled, zone_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, location, source, source_type, int(enabled), json.dumps(zone or {}), _now()),
        )
        return cur.lastrowid


def update_camera(camera_id, **fields):
    allowed = {"name", "location", "source", "source_type", "enabled", "zone_json",
               "last_status", "last_verified_at"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    sets = ", ".join(f"{k} = ?" for k in updates)
    with _conn() as con:
        con.execute(f"UPDATE cameras SET {sets} WHERE id = ?", (*updates.values(), camera_id))


def delete_camera(camera_id):
    with _conn() as con:
        con.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))


def get_camera(camera_id):
    with _conn() as con:
        row = con.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone()
        return dict(row) if row else None


def list_cameras(enabled_only=False):
    q = "SELECT * FROM cameras"
    if enabled_only:
        q += " WHERE enabled = 1"
    q += " ORDER BY id"
    with _conn() as con:
        return [dict(r) for r in con.execute(q).fetchall()]


def set_camera_status(camera_id, status):
    update_camera(camera_id, last_status=status, last_verified_at=_now())


def get_camera_zone(camera):
    try:
        return json.loads(camera.get("zone_json") or "{}")
    except (TypeError, ValueError):
        return {}


# ------------------------------------------------------------- violations
def log_violation(camera_id, camera_name, vtype, message, confidence=0.0, snapshot_path=None):
    with _conn() as con:
        con.execute(
            "INSERT INTO violations (camera_id, camera_name, vtype, message, confidence,"
            " snapshot_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (camera_id, camera_name, vtype, message, confidence, snapshot_path, _now()),
        )


def list_violations(camera_id=None, vtype=None, since=None, limit=500):
    q = "SELECT * FROM violations WHERE 1=1"
    args = []
    if camera_id:
        q += " AND camera_id = ?"
        args.append(camera_id)
    if vtype:
        q += " AND vtype = ?"
        args.append(vtype)
    if since:
        q += " AND created_at >= ?"
        args.append(since)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with _conn() as con:
        return [dict(r) for r in con.execute(q, args).fetchall()]


def violation_counts_by_type(since=None):
    q = "SELECT vtype, COUNT(*) AS n FROM violations"
    args = []
    if since:
        q += " WHERE created_at >= ?"
        args.append(since)
    q += " GROUP BY vtype ORDER BY n DESC"
    with _conn() as con:
        return {r["vtype"]: r["n"] for r in con.execute(q, args).fetchall()}


# --------------------------------------------------------------- settings
def get_setting(key, default=None):
    with _conn() as con:
        row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with _conn() as con:
        con.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
