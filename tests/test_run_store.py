import os
import sys
# Ensure the dashboard package directory is on sys.path so tests can import modules
_THIS_DIR = os.path.dirname(__file__)
_DASHBOARD_DIR = os.path.abspath(os.path.join(_THIS_DIR, "..", "dashboard"))
if _DASHBOARD_DIR not in sys.path:
    sys.path.insert(0, _DASHBOARD_DIR)

import importlib
run_store = importlib.import_module("run_store")


def test_add_and_get_run_with_extra_env(tmp_path):
    # Use a temporary DB location to avoid clobbering the user's real DB
    dbpath = tmp_path / "runs.db"
    run_store.DB_FILENAME = str(dbpath)
    # Ensure directory exists and initialize schema
    os.makedirs(os.path.dirname(run_store.DB_FILENAME), exist_ok=True)
    run_store.init_db()

    pid = 123456
    extra = {"FOO": "bar", "NUM": "42"}
    run_store.add_run(pid, "echo hi", "/tmp", "/tmp/out.log", "/tmp/err.log", extra_env=extra)

    row = run_store.get_run(pid)
    assert row is not None
    assert int(row.get("pid")) == pid
    assert row.get("extra_env") == extra

    # list_runs should include our running PID when active_only=True
    active = run_store.list_runs(active_only=True)
    assert any(int(r.get("pid")) == pid for r in active)
