"""Simple SQLite-backed run registry for the dashboard.

This module provides a small schema that stores per-run metadata and
optionally persists the environment variables (extra_env) used to start
the run. extra_env is saved as JSON in the `env_json` column so we can
recreate restarts with the same environment when needed.

API (important functions):
  - init_db()
  - add_run(pid, command, cwd, stdout_path, stderr_path, extra_env=None, started_at=None)
  - update_run_status(pid, status, returncode=None, ended_at=None)
  - get_run(pid) -> Optional[Dict]
  - list_runs(active_only=False) -> List[Dict]
"""
from __future__ import annotations

import os
import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional


def _resolve_db_filename() -> str:
    pkg_dir = os.path.dirname(__file__)
    cfg_path = os.path.join(pkg_dir, ".streamlit", "config.toml")
    db_val: Optional[str] = None
    default_dir = os.path.join(os.path.expanduser("~"), ".dashboard")

    # Prefer stdlib tomllib on Python 3.11+, otherwise fall back to tomli if present
    toml_loader = None
    try:
        import tomllib as toml_loader  # type: ignore
    except Exception:
        try:
            import tomli as toml_loader  # type: ignore
        except Exception:
            toml_loader = None

    if toml_loader is not None and os.path.exists(cfg_path):
        try:
            with open(cfg_path, "rb") as f:
                data = toml_loader.load(f)
            if isinstance(data, dict):
                db_val = data.get("runs_db")
                if db_val is None and isinstance(data.get("dashboard"), dict):
                    db_val = data["dashboard"].get("runs_db")
                if db_val is None:
                    db_name = data.get("runs_db_name")
                    if db_name is None and isinstance(data.get("dashboard"), dict):
                        db_name = data["dashboard"].get("runs_db_name")
                    if db_name:
                        db_name = str(db_name)
                        db_val = db_name if os.path.isabs(db_name) else os.path.join(default_dir, db_name)
        except Exception:
            db_val = None

    if db_val:
        try:
            db_path = str(db_val)
            db_path = os.path.expanduser(os.path.expandvars(db_path))
            if not os.path.isabs(db_path):
                db_path = os.path.abspath(os.path.join(pkg_dir, db_path))
            return db_path
        except Exception:
            pass

    try:
        os.makedirs(default_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(default_dir, "runs.db")


DB_FILENAME = _resolve_db_filename()


def _conn():
    d = os.path.dirname(DB_FILENAME)
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    conn = sqlite3.connect(DB_FILENAME, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            pid INTEGER PRIMARY KEY,
            command TEXT,
            cwd TEXT,
            status TEXT,
            started_at TEXT,
            ended_at TEXT,
            returncode INTEGER,
            stdout_path TEXT,
            stderr_path TEXT,
            env_json TEXT
        )
        """
    )
    # Lightweight migration: add env_json column if missing
    try:
        cur.execute("PRAGMA table_info(runs)")
        cols = [r[1] for r in cur.fetchall()]
        if "env_json" not in cols:
            try:
                cur.execute("ALTER TABLE runs ADD COLUMN env_json TEXT")
            except Exception:
                # Non-fatal; continue
                pass
    except Exception:
        pass
    conn.commit()
    conn.close()

    # Backfill started_at for any older rows that lack it (NULL or empty)
    try:
        conn = _conn()
        cur = conn.cursor()
        now = datetime.now().isoformat(timespec="seconds")
        cur.execute("UPDATE runs SET started_at = ? WHERE started_at IS NULL OR started_at = ''", (now,))
        conn.commit()
        conn.close()
    except Exception:
        # Non-fatal; continue
        pass


def add_run(
    pid: int,
    command: str,
    cwd: Optional[str],
    stdout_path: Optional[str],
    stderr_path: Optional[str],
    extra_env: Optional[Dict] = None,
    started_at: Optional[str] = None,
) -> None:
    """Record a started run. Persists extra_env as JSON when provided."""
    init_db()
    conn = _conn()
    cur = conn.cursor()
    if started_at is None:
        started_at = datetime.now().isoformat(timespec="seconds")
    env_json = None
    try:
        if extra_env:
            env_json = json.dumps(extra_env)
    except Exception:
        env_json = None
    cur.execute(
        """
        INSERT OR REPLACE INTO runs (pid, command, cwd, status, started_at, stdout_path, stderr_path, env_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (pid, command, cwd or "", "running", started_at, stdout_path or "", stderr_path or "", env_json),
    )
    conn.commit()
    conn.close()


def update_run_status(pid: int, status: str, returncode: Optional[int] = None, ended_at: Optional[str] = None) -> None:
    init_db()
    conn = _conn()
    cur = conn.cursor()
    if ended_at is None:
        ended_at = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        """
        UPDATE runs SET status = ?, returncode = ?, ended_at = ? WHERE pid = ?
        """,
        (status, returncode, ended_at, pid),
    )
    conn.commit()
    conn.close()


def _row_to_dict(row: sqlite3.Row) -> Dict:
    d: Dict[str, Optional[str]] = {}
    for k in row.keys():
        d[k] = row[k]
    # Parse env_json if present
    env_raw = d.get("env_json")
    try:
        d["extra_env"] = json.loads(env_raw) if env_raw else None
    except Exception:
        d["extra_env"] = None
    return d


def get_run(pid: int) -> Optional[Dict]:
    init_db()
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM runs WHERE pid = ?", (pid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_dict(row)


def list_runs(active_only: bool = False) -> List[Dict]:
    init_db()
    conn = _conn()
    cur = conn.cursor()
    if active_only:
        cur.execute("SELECT * FROM runs WHERE status = 'running' ORDER BY started_at DESC")
    else:
        cur.execute("SELECT * FROM runs ORDER BY started_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]

