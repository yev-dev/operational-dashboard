import os
import time
import sys
import shlex
# Make dashboard package importable for tests
_THIS_DIR = os.path.dirname(__file__)
_DASHBOARD_DIR = os.path.abspath(os.path.join(_THIS_DIR, "..", "dashboard"))
if _DASHBOARD_DIR not in sys.path:
    sys.path.insert(0, _DASHBOARD_DIR)

import importlib
run_store = importlib.import_module("run_store")
scripts_runner = importlib.import_module("scripts_runner")
start_subprocess = scripts_runner.start_subprocess
terminate_process = scripts_runner.terminate_process
ACTIVE_PROCS = scripts_runner.ACTIVE_PROCS


def test_start_preserve_and_restart(tmp_path):
    # Use a temporary DB so we don't touch the user's real data
    dbpath = tmp_path / "runs.db"
    run_store.DB_FILENAME = str(dbpath)
    os.makedirs(os.path.dirname(run_store.DB_FILENAME), exist_ok=True)
    run_store.init_db()

    # Build a short-lived python command that sleeps long enough for the test
    cmd = [sys.executable, "-c", "import time; time.sleep(5)"]
    extra = {"TEST_RUN": "1"}

    # Start the process
    res = start_subprocess(cmd, cwd=None, extra_env=extra, log_prefix="unittest_restart")
    pid1 = int(res.get("pid"))
    assert pid1 in ACTIVE_PROCS

    # Ensure DB recorded the run and extra_env
    row = run_store.get_run(pid1)
    assert row is not None
    assert row.get("extra_env") == extra

    # Now restart: terminate the first process, then start a new one using stored command
    try:
        ok = terminate_process(pid1)
    except Exception:
        ok = False
    assert ok is True

    # Wait for the process to be removed from ACTIVE_PROCS
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if pid1 not in ACTIVE_PROCS:
            break
        time.sleep(0.1)
    assert pid1 not in ACTIVE_PROCS

    # Use the stored command string from DB to reconstruct args
    row_after = run_store.get_run(pid1)
    assert row_after is not None
    cmd_str = row_after.get("command")
    assert cmd_str
    cmd_list = shlex.split(cmd_str)

    # Start restarted process
    res2 = start_subprocess(cmd_list, cwd=None, extra_env=extra, log_prefix=f"restart_{pid1}")
    pid2 = int(res2.get("pid"))
    assert pid2 in ACTIVE_PROCS

    # DB should have an entry for the new PID and preserve the extra_env when provided
    row2 = run_store.get_run(pid2)
    assert row2 is not None
    assert row2.get("extra_env") == extra

    # Cleanup: terminate the restarted process
    try:
        terminate_process(pid2)
    except Exception:
        pass
