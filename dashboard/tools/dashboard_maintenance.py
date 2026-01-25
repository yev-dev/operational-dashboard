"""Maintenance helpers for the Operational Dashboard.

Provides a safe backup function for the runs SQLite DB and simple rotation of old
backups. Designed to be imported by the Streamlit UI or used as a standalone
script.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from datetime import datetime
import shutil
from typing import Optional


def backup_runs_db(db_path: Optional[str] = None, backups_dir: Optional[str] = None, keep: int = 7) -> str:
    """Create a consistent backup of the SQLite runs DB and rotate older backups.

    Args:
        db_path: path to the source runs DB. If None, defaults to ~/.dashboard/runs.db
        backups_dir: directory where backups are stored. If None, defaults to ~/.dashboard/backups
        keep: how many most-recent backups to keep; older files will be removed.

    Returns:
        The absolute path to the created backup file.

    Raises:
        FileNotFoundError: if the source DB does not exist.
        Exception: on unexpected errors while creating the backup.
    """
    src = Path(db_path or os.path.expanduser("~/.dashboard/runs.db"))
    if not src.exists():
        raise FileNotFoundError(f"Runs DB not found at: {src}")

    backups_dir_path = Path(backups_dir or os.path.expanduser("~/.dashboard/backups"))
    backups_dir_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_name = f"runs.db.{timestamp}.sqlite"
    backup_path = backups_dir_path.joinpath(backup_name)

    # Use sqlite3's backup API for a consistent copy even while DB is live
    src_conn = None
    dst_conn = None
    try:
        src_conn = sqlite3.connect(str(src))
        dst_conn = sqlite3.connect(str(backup_path))
        # source_conn.backup(destination_conn)
        src_conn.backup(dst_conn)
    finally:
        if dst_conn:
            try:
                dst_conn.close()
            except Exception:
                pass
        if src_conn:
            try:
                src_conn.close()
            except Exception:
                pass

    # Rotate older backups: keep only the `keep` newest files
    try:
        files = sorted([p for p in backups_dir_path.iterdir() if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            try:
                old.unlink()
            except Exception:
                # Best-effort: ignore deletion errors
                pass
    except Exception:
        # Ignore rotation failures; backup was created successfully above
        pass

    return str(backup_path)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Create a backup of the dashboard runs DB and rotate older backups.")
    p.add_argument("--db", default=None, help="Path to runs DB (defaults to ~/.dashboard/runs.db)")
    p.add_argument("--backups-dir", default=None, help="Directory to store backups (defaults to ~/.dashboard/backups)")
    p.add_argument("--keep", type=int, default=7, help="Number of backups to keep")
    args = p.parse_args()

    try:
        out = backup_runs_db(db_path=args.db, backups_dir=args.backups_dir, keep=args.keep)
        print(out)
    except Exception as e:
        print(f"Backup failed: {e}")
        raise
