
# Dashboard README (moved)

This README has been moved to the parent directory of the dashboard package for easier sharing and packaging.

Please see the canonical copy at `../README.md` (project root for the operational-dashboard):

```text
../README.md
```

The Streamlit Docs tab will load the parent README automatically if a dashboard-local `README.md` is not present.
- [Setup](#setup)
- [How to run](#how-to-run)
- [Using the Script Runners tab](#using-the-script-runners-tab)
  - [Maintenance tab](#maintenance-tab)
- [Config tab](#config-tab)
- [Auto-reload and file watching](#auto-reload-and-file-watching)
- [Example runner modules](#example-runner-modules)

## Dashboard tabs overview

This dashboard is organized into tabs. Here’s what each tab contains and how to use it:

### Script Runners
- Discover and run modules from the configured “scripts package” (defaults to `runners` or the package(s) defined in `.streamlit/config.toml`).
- Argparse-backed modules: parameters are auto-detected and rendered as inputs.
- Non-argparse modules: enter date tokens (COB_DATE, RUN_DATE, START_DATE, END_DATE) and choose how to pass them (argv tokens or environment variables).
- Environment selector: loads values from `~/.dashboard/config.ini` (e.g., `CONDA_ENV`, `CONFIG_PATH`, `RESULT_PATH`).
- Backend choice: run via Conda (`conda run -n <env> python -m ...`) or via the environment’s Python interpreter path.
- Config preset editor: generate or load a per-module JSON preset; includes a raw JSON editor to modify any node and buttons to Validate, Apply, Save, Create default, Dry run, and Run with Config.
- Detach mode: start long runs asynchronously and view live tails; you can terminate, refresh, or attach the tail to the dashboard log.
- Scripts package selection: if `.streamlit/config.toml` has a list for `runners_package`, pick one from the dropdown or enter a custom value; switching refreshes the discovered module list.
- Historical Log Runs: shows a timeline of executed commands with combined stdout+stderr.

### Monitoring

- Running Processes: interactive table of processes started by the dashboard (and tracked in session). Actions:
  - Refresh Running Processes: forces a refresh/rerun of the app to reflect the current OS process state.
  - Select rows and click "Terminate Selected" to send termination signals to chosen PIDs.
  - "Terminate All" stops all tracked processes started by the dashboard.
  - If a detached run is tracked in session state but not present in ACTIVE_PROCS, the dashboard will attempt to clean up stale entries.

- Dashboard Log (tail): shows a live tail of the centralized dashboard log at `~/.dashboard/logs/dashboard.log`.
  - Refresh (manual) button re-reads the tail.
  - Download Log: downloads the dashboard log; large downloads are written to disk as a zip and served to the browser to avoid excessive memory usage.

- Per-run log tails:
  - Detached runs write stdout/err into `~/.dashboard/logs/runs/` as separate files. The UI shows a merged tail (stdout+stderr) for each run — lines are merged in timestamp/order when possible and shown without injected "STDERR:" headers.
  - Attach tail to dashboard.log: copy current tail contents into the central dashboard log (useful for capturing a snapshot).
  - Auto-attach: when enabled (configurable in Streamlit config), background tailers automatically append new output from running processes into the dashboard.log at a configurable interval.

- Historical Log Runs: timeline of completed runs with captured stdout/stderr. The UI presents combined output for convenience (stderr appended raw), and you can clear the history via "Clear Logs".

- Logs Maintenance: utilities to clear or rotate logs. The app avoids keeping extremely large logs in memory — downloads use disk-backed zip files.

### Config
- Environment Config (`~/.dashboard/config.ini`): edit existing keys for selected env (DEV/UAT/PROD). Save persists to the home config.
- Validation: checks whether the selected env’s `CONDA_ENV` exists.
- Streamlit Config: edit `.streamlit/config.toml` in-place.
  - Supported keys include:
    - `runners_package` (string or array): one or more importable packages to discover modules from.
    - `dashboard_name`: title rendered at the top of the app.
    - `default_notebook_dir`: default folder for starting Jupyter.
    - `auto_attach` (bool): whether new processes auto-stream their logs into dashboard.log.
    - `auto_attach_interval` (float): seconds between tail checks.

### Tools
- Check Environment: runs `check_environment.py` (from a parent `tools/` folder) inside the selected conda env and shows output.
- Jupyter Notebook: start a Jupyter server in a chosen directory and env; detached with live tails.
- Kill Process by PID: send termination signals manually.
- Terminate All: stop all tracked processes started from the dashboard.
- Running Processes: interactive table with multi-select terminate.
- Logs Maintenance: “Clear All Logs” truncates `dashboard.log`, removes rotated logs, and clears `~/.dashboard/logs/runs/*`.

### Docs
- Renders this `README.md` within the app for quick reference (Docs tab).

## Centralized logs
- Main dashboard log: `~/.dashboard/logs/dashboard.log` (rotated).
- Per-run logs: `~/.dashboard/logs/runs/*.out.log` and `*.err.log`.
- Auto-attach tailers: when enabled, background tailers stream new output into the main dashboard log; defaults are controlled via `.streamlit/config.toml`.

### Optional SQLite run registry

- The dashboard can optionally persist run metadata (started runs, status, stdout/stderr paths) to a small SQLite database so multiple Streamlit sessions on the same host can see the same "Running Processes" listing.
- By default the DB location is `~/.dashboard/runs.db`. You can override this in `qf/dashboard/.streamlit/config.toml` with either:
  - `runs_db = "/absolute/path/to/runs.db"` (full path), or
  - `runs_db_name = "my_runs.db"` (a filename placed under `~/.dashboard`).
- The run registry is optional — if SQLite or the DB file is not available the app falls back to in-memory tracking (`ACTIVE_PROCS`) and continues to work.
- Notes and caveats:
  - SQLite is appropriate for single-host, low-to-moderate concurrency. For heavy concurrent writes or multi-host setups consider a centralized DB or service (e.g., PostgreSQL, Redis).
  - Ensure the user running Streamlit has write permissions to the configured DB directory.
  - The dashboard uses Python's stdlib `sqlite3` module (no extra pip package required) but needs a Python build with SQLite enabled (most standard Python builds include this).

#### Example config snippets

Place one of the following entries into `qf/dashboard/.streamlit/config.toml` (or your project `.streamlit/config.toml`) to control where the runs DB is stored:

```toml
[dashboard]
# Absolute path to the DB file
runs_db = "/home/you/.dashboard/runs.db"

# Or, place just a filename under ~/.dashboard
# runs_db_name = "my_runs.db"
```

If you prefer a portable project-local path, set `runs_db` to a relative path (resolved against the dashboard package dir).

#### Backing up the runs DB

Because the run registry is a single-file SQLite database, it's a good idea to back it up periodically. A few safe, simple options:

- Lightweight file copy (best when writes are infrequent):

```bash
mkdir -p ~/.dashboard/backups
cp ~/.dashboard/runs.db ~/.dashboard/backups/runs.db.$(date +%Y%m%d%H%M%S)
```

- Use SQLite's consistent backup (preferred when the DB may be written while backing up):

```bash
mkdir -p ~/.dashboard/backups
sqlite3 ~/.dashboard/runs.db ".backup './.dashboard/backups/runs.db.$(date +%Y%m%d%H%M%S)'"
```

- Example cron entry to rotate a backup daily at 02:00 (edit with `crontab -e`):

```cron
0 2 * * * /bin/sh -lc 'mkdir -p ~/.dashboard/backups && sqlite3 ~/.dashboard/runs.db ".backup '~/.dashboard/backups/runs.db.$(date +\%Y\%m\%d\%H\%M\%S)'"'
```

Notes:
- Copying a live SQLite file can produce inconsistent backups if writes are in-flight; prefer `.backup` or pause heavy activity before copying.
- Ensure your backup directory is writable and, if the DB contains sensitive information, protect it with appropriate filesystem permissions.

#### Restoring from a backup

To restore a backup, you can either copy the backup file back to the active location (recommended when the dashboard is stopped) or use sqlite3 to restore it. Examples:

- Simple copy (stop the dashboard first to avoid races):

```bash
cp ~/.dashboard/backups/runs.db.20250101020000.sqlite ~/.dashboard/runs.db
```

- Use sqlite3's restore/backup methods (works while DB is live but prefer stopping writes):

```bash
# restore into an existing DB (overwrite)
sqlite3 ~/.dashboard/runs.db ".restore '~/.dashboard/backups/runs.db.20250101020000.sqlite'"
```

Notes:
- Always ensure the dashboard process is not actively writing to the DB during a restore to avoid inconsistent state. If you must restore while the dashboard is running, consider stopping the app, restoring, then restarting.
- Verify permissions after restoring so the dashboard user can read/write the DB file.

## Quick start
1. Ensure the <env> conda environment exists with `streamlit` and `watchdog` installed.
2. Launch the app (via VS Code task or):

```bash
conda run -n <env> streamlit run dashboard.py --server.fileWatcherType=watchdog --server.runOnSave=true
```

3. Open Script Runners, pick a module, fill parameters, and run.
4. Check Logs for dashboard.log tail; use Tools for Jupyter or Terminal runs.

## Configuration reference (excerpt)

```toml
[server]
fileWatcherType = "watchdog"
runOnSave = true

[dashboard]
runners_package = [
  "qf.dashboard.runners",
  "qf.tools",
  "qf.scripts"
]
dashboard_name = "Operational Dashboard"
default_notebook_dir = "~"
auto_attach = true
auto_attach_interval = 2.0
```

## Troubleshooting
- Conda env not found: ensure `conda env list` shows your env; update `CONDA_ENV` in `~/.dashboard/config.ini`.
- No modules discovered: check that your scripts reside in the configured `runners_package` and are importable.
- Permission errors on logs: ensure your user can create `~/.dashboard/logs` and `runs` subfolder.
- Streamlit not reloading: verify `fileWatcherType = "watchdog"` and `runOnSave = true` are set; ensure the app is launched via the intended environment.

## Folder layout

- `dashboard.py` — Streamlit UI with tabs (Script Runners, Logs, Config)
- `scripts_runner.py` — Non-UI helpers (discover modules, parse argparse, build commands, run subprocess)
- `runners/` — Package containing your runnable Python modules (e.g., `first_model.py`, `second_model.py`)
- `.streamlit/config.toml` — Streamlit server configuration (auto-reload and watcher)

## Requirements

- Conda (Miniconda or Anaconda) installed and available on PATH
- Conda environment named <env> with Python and dependencies
- Python packages in <env> env:
  - `streamlit`
  - `watchdog` (for robust file watching)

Note: Python 3.11 or newer is recommended so the app can use the stdlib `tomllib` for TOML parsing. If you plan to use the Jupyter integration (start JupyterLab/Notebook from the UI), install `jupyterlab` in the same conda environment as well.

## Setup

1. Ensure the <env> environment exists:

```bash
conda env list
conda create -n <env> python=3.11  # if needed
```

2. Install required packages into <env>:

```bash
conda run -n <env> pip install streamlit watchdog
```

3. (Optional) Verify Streamlit inside <env>:

```bash
conda run -n <env> python -c "import streamlit, watchdog; print('OK')"
```

## How to run

From the dashboard directory:

```bash
cd /Users/yevgeniy/Development/Projects/FinancialEngineering/quant-finance/qf/dashboard

# Option A: Run Streamlit via conda run (recommended for reliability)
conda run -n <env> streamlit run dashboard.py

# Option B: Activate env and run (works if your shell supports conda activate)
# conda activate <env>
# streamlit run dashboard.py
```

## Using the Script Runners tab

- Place your modules in `runners/` (e.g., `runners/first_model.py`).
- Define CLI arguments with `argparse.add_argument(...)` in each runner module.
- In the dashboard:
  - Select a module from the dropdown.
  - Review detected parameters in "Detected Parameters".
  - Fill inputs in the form and click "Run Module".
- The command that will be executed looks like:

```bash
conda run -n <env> python -m runners.<module_name> [args]
```

## Maintenance tab

- Shows a history of recent runs (command, exit code, stdout, stderr).
- Click "Clear Logs" to wipe the history.

## Config tab

- Displays and lets you edit `.streamlit/config.toml`.
- Defaults provided by this project:

```toml
[server]
fileWatcherType = "watchdog"
runOnSave = true
```

- When you click "Save Config", the app writes changes and will auto-reload if the watcher is enabled.

## Auto-reload and file watching

- The dashboard imports runner modules so Streamlit’s watcher detects changes in `runners/` as well as `dashboard.py`.
- With `watchdog` and `runOnSave` enabled, saving files retriggers the app automatically.

## Troubleshooting

- "Import streamlit could not be resolved": install `streamlit` in the <env> environment and run the app via `conda run -n <env>`.
- "conda: command not found": install Miniconda/Anaconda and ensure `conda` is on PATH.
- Env <env> doesn’t exist: create it via `conda create -n <env> python=3.11`.
- Modules not detected: ensure `.py` files are inside `runners/` and that `runners/__init__.py` exists.
- Subprocess fails: check the command shown in the UI; verify dates/args and that required packages are installed in the <env> env.

## Example runner modules

Minimal examples (place in `runners/`):

```python
# runners/first_model.py
import argparse
from datetime import datetime

def _parse_date(s: str):
    return datetime.strptime(s, "%Y-%m-%d").date()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--start-date", required=True, type=_parse_date)
    p.add_argument("--end-date", required=True, type=_parse_date)
    a = p.parse_args()
    print(f"[first_model] start={a.start_date} end={a.end_date}")
```

```python
# runners/second_model.py
import argparse
from datetime import datetime

def _parse_date(s: str):
    return datetime.strptime(s, "%Y-%m-%d").date()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--start-date", required=True, type=_parse_date)
    p.add_argument("--end-date", required=True, type=_parse_date)
    p.add_argument("--operation-type", default=None)
    a = p.parse_args()
    print(f"[second_model] start={a.start_date} end={a.end_date} op={a.operation_type}")
```

Run them from the dashboard UI by selecting the module and providing arguments.
