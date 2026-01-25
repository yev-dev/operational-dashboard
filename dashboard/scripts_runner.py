#!/usr/bin/env python3
"""
scripts_runner.py

Non-UI logic used by the Streamlit dashboard:
- Discover Python scripts in a directory
- Parse argparse add_argument() calls to infer CLI parameters
- Build command lines from parameter values
- Run scripts in a subprocess and return results
"""

import os
import ast
import shlex
import subprocess
import logging
import configparser
import shutil
import json
import signal
import time
import threading
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import importlib
try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None


@dataclass
class ArgSpec:
    name: str
    flags: List[str]
    positional: bool
    arg_type: str = "str"  # "str" | "int" | "float" | "bool"
    default: Optional[Any] = None
    choices: Optional[List[Any]] = None
    help_text: Optional[str] = None
    action: Optional[str] = None  # e.g., "store_true"

    def preferred_flag(self) -> Optional[str]:
        if self.positional:
            return None
        long_flags = [f for f in self.flags if f.startswith("--")]
        if long_flags:
            return sorted(long_flags, key=len, reverse=True)[0]
        return self.flags[0] if self.flags else None


SELF_NAME = os.path.basename(__file__)

def _get_streamlit_config() -> Dict[str, Any]:
    """Read .streamlit/config.toml if available and return a dict."""
    cfg_path = os.path.join(os.path.dirname(__file__), ".streamlit", "config.toml")
    if not os.path.exists(cfg_path) or tomllib is None:
        return {}
    try:
        with open(cfg_path, "rb") as f:
            data = tomllib.load(f)
        return data or {}
    except Exception:
        return {}

def get_runners_packages_list() -> List[str]:
    """Return a list of configured runners packages from config.toml.

    Supports `runners_package` as either a single string or a TOML array, at the top level
    or under the legacy `[dashboard]` table. Falls back to ['runners'] if undefined.
    """
    data = _get_streamlit_config()
    pkgs: List[str] = []
    try:
        if isinstance(data, dict):
            raw = data.get("runners_package")
            if raw is None and isinstance(data.get("dashboard"), dict):
                raw = data["dashboard"].get("runners_package")
            if isinstance(raw, list):
                pkgs = [str(x).strip() for x in raw if str(x).strip()]
            elif isinstance(raw, str):
                val = raw.strip()
                if val:
                    pkgs = [val]
    except Exception:
        pkgs = []
    if not pkgs:
        pkgs = ["runners"]
    return pkgs


def get_runners_package() -> str:
    """Return the preferred runners package (first from list)."""
    pkgs = get_runners_packages_list()
    return pkgs[0] if pkgs else "runners"

RUNNERS_PACKAGE = get_runners_package()
CONDA_ENV_NAME = "qf"
HOME_CONFIG_DIRNAME = ".dashboard"
OLD_HOME_CONFIG_DIRNAME = ".qf_dashboard"
HOME_CONFIG_FILENAME = "config.ini"
def _resolve_package_dir(pkg_name: str) -> str:
    """Resolve a package/module name to its filesystem directory.

    Imports the package and returns its path. If resolution fails, fall back to a local path.
    """
    try:
        mod = importlib.import_module(pkg_name)
        if hasattr(mod, "__path__") and mod.__path__:
            return mod.__path__[0]
        if hasattr(mod, "__file__") and mod.__file__:
            return os.path.dirname(mod.__file__)
    except Exception:
        pass
    # Fallback: treat dots as directory separators relative to dashboard
    return os.path.join(os.path.dirname(__file__), pkg_name.replace(".", os.sep))

RUNNERS_DIR = _resolve_package_dir(RUNNERS_PACKAGE)
# Store logs under user's home: ~/.dashboard/logs and runs under ~/.dashboard/logs/runs
HOME_BASE_DIR = os.path.join(os.path.expanduser("~"), HOME_CONFIG_DIRNAME)
LOGS_DIR = os.path.join(HOME_BASE_DIR, "logs")
RUN_LOGS_DIR = os.path.join(LOGS_DIR, "runs")

# Optional sqlite-backed run store to persist run metadata across sessions
try:
    from run_store import add_run, update_run_status
except Exception:
    # If importing fails, provide no-op fallbacks so existing code continues to work
    def add_run(pid: int, command: str, cwd: Optional[str], stdout_path: Optional[str], stderr_path: Optional[str], extra_env: Optional[Dict] = None, started_at: Optional[str] = None) -> None:  # type: ignore
        return None

    def update_run_status(pid: int, status: str, returncode: Optional[int] = None, ended_at: Optional[str] = None) -> None:  # type: ignore
        return None

def set_runners_package(pkg_name: str) -> None:
    """Override the runners package at runtime and recompute the directory.

    This affects discovery (list_runner_modules), argparse parsing, and command builds.
    """
    global RUNNERS_PACKAGE, RUNNERS_DIR
    pkg_name = (pkg_name or "runners").strip()
    RUNNERS_PACKAGE = pkg_name or "runners"
    RUNNERS_DIR = _resolve_package_dir(RUNNERS_PACKAGE)

from typing import Tuple

def validate_runners_package(pkg_name: str) -> Tuple[bool, str, str, List[str]]:
    """Validate that a runners package can be located and list modules under it.

    Returns (ok, detail, directory, modules).
    - ok: True if directory exists and at least one module is found; False otherwise
    - detail: status message including import/resolve info
    - directory: resolved filesystem directory for the package
    - modules: discovered module names (without .py)
    """
    name = (pkg_name or "").strip()
    if not name:
        return False, "Empty package name", "", []
    # Try import for visibility on sys.path
    imported_ok = True
    try:
        importlib.import_module(name)
    except Exception as e:
        imported_ok = False
        import_err = str(e)
    # Resolve directory (works even if import failed when using local path fallback)
    pkg_dir = _resolve_package_dir(name)
    if not os.path.isdir(pkg_dir):
        msg = f"Package directory not found: {pkg_dir}"
        if not imported_ok:
            msg += f"; import failed: {import_err}"
        return False, msg, pkg_dir, []
    # List python modules
    mods: List[str] = []
    try:
        for entry in os.listdir(pkg_dir):
            if entry.endswith(".py") and not entry.startswith("__"):
                mods.append(entry[:-3])
    except Exception as e:
        return False, f"Failed to list modules: {e}", pkg_dir, []
    if not mods:
        msg = "No modules (*.py) found in package directory"
        if not imported_ok:
            msg += f"; import failed: {import_err}"
        return False, msg, pkg_dir, []
    detail = f"Resolved to {pkg_dir}. {'Import OK' if imported_ok else 'Import failed'}; {len(mods)} module(s) found"
    return True, detail, pkg_dir, sorted(mods)


def _resolve_package_dir_in_conda_env(env_name: str, pkg_name: str) -> Tuple[bool, str, str]:
    """Resolve a package directory inside a specific conda environment.

    Returns (ok, directory, error_message).
    """
    env_name = (env_name or "").strip()
    pkg_name = (pkg_name or "").strip()
    if not env_name or not pkg_name:
        return False, "", "Environment name or package name is empty"
    py = (
        "import importlib, os; "
        f"m=importlib.import_module('{pkg_name}'); "
        "d=os.path.dirname(getattr(m,'__file__','')) if getattr(m,'__file__', None) else list(m.__path__)[0]; "
        "print(d)"
    )
    try:
        proc = subprocess.run(
            ["conda", "run", "-n", env_name, "python", "-c", py],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False, "", "conda executable not found on PATH"
    except Exception as e:
        return False, "", f"Failed to run conda: {e}"
    if proc.returncode != 0:
        return False, "", f"conda run returned {proc.returncode}: {proc.stderr.strip()}"
    directory = proc.stdout.strip().splitlines()[-1] if proc.stdout else ""
    if not directory or not os.path.isdir(directory):
        return False, directory, f"Resolved path invalid or not a directory: {directory}"
    return True, directory, ""


def set_runners_source_from_env(env_name: str, pkg_name: str) -> Tuple[bool, str]:
    """Set the runners package and directory using a specific conda environment.

    Attempts to resolve the package directory inside the given conda env; on success,
    updates globals so discovery and parsing use that directory. Returns (ok, detail).
    """
    ok, directory, err = _resolve_package_dir_in_conda_env(env_name, pkg_name)
    if not ok:
        # Fallback to default resolution while returning error detail
        set_runners_package(pkg_name)
        return False, f"Fallback to local resolution. Reason: {err}"
    # Apply
    global RUNNERS_PACKAGE, RUNNERS_DIR
    RUNNERS_PACKAGE = (pkg_name or "runners").strip() or "runners"
    RUNNERS_DIR = directory
    return True, f"Using {RUNNERS_PACKAGE} from {RUNNERS_DIR}"


def validate_runners_package_in_env(env_name: str, pkg_name: str) -> Tuple[bool, str, str, List[str]]:
    """Validate a runners package by resolving it inside a given conda environment and listing modules.

    Returns (ok, detail, directory, modules).
    """
    ok, directory, err = _resolve_package_dir_in_conda_env(env_name, pkg_name)
    if not ok:
        return False, f"Failed to resolve in env '{env_name}': {err}", directory, []
    # List modules in that directory
    try:
        mods = [e[:-3] for e in os.listdir(directory) if e.endswith(".py") and not e.startswith("__")]
    except Exception as e:
        return False, f"Resolved to {directory} but failed to list modules: {e}", directory, []
    if not mods:
        return False, f"Resolved to {directory} in env '{env_name}' but found no .py modules", directory, []
    detail = f"Resolved in env '{env_name}' to {directory}; {len(mods)} module(s) found"
    return True, detail, directory, sorted(mods)


def _to_name_from_flag(flag: str) -> str:
    # --start-date -> start_date; -s -> s
    if flag.startswith("--"):
        return flag[2:].replace("-", "_")
    if flag.startswith("-"):
        return flag[1:]
    return flag


def parse_argparse_args_for_module(module_name: str) -> List[ArgSpec]:
    """Parse argparse add_argument calls from a module within the runners package.

    module_name should be the filename without .py (e.g., "first_model").
    """
    py_file = os.path.join(RUNNERS_DIR, f"{module_name}.py")
    try:
        with open(py_file, "r", encoding="utf-8") as f:
            src = f.read()
    except OSError:
        return []

    try:
        tree = ast.parse(src, filename=py_file)
    except SyntaxError:
        return []

    argspecs: List[ArgSpec] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr != "add_argument":
                continue
            # Collect positional/flag strings
            flags: List[str] = []
            for a in node.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    flags.append(a.value)
                elif isinstance(a, ast.Str):  # py<3.8
                    flags.append(a.s)
            # Keyword args
            kw: Dict[str, Any] = {}
            for k in node.keywords:
                key = k.arg
                val = k.value
                kw[key] = val

            # Determine name/dest
            dest_name: Optional[str] = None
            if "dest" in kw:
                v = kw["dest"]
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    dest_name = v.value
                elif isinstance(v, ast.Str):
                    dest_name = v.s

            # Positional if no leading '-' in flags
            positional = not any(f.startswith("-") for f in flags)

            # Choose canonical name
            if dest_name:
                name = dest_name
            elif flags:
                name = _to_name_from_flag(sorted(flags, key=len, reverse=True)[0])
            else:
                name = f"arg_{len(argspecs)+1}"

            # Type
            arg_type = "str"
            if "type" in kw:
                v = kw["type"]
                if isinstance(v, ast.Name):
                    if v.id in ("int", "float", "str"):
                        arg_type = v.id
                elif isinstance(v, ast.Attribute):
                    if v.attr in ("int", "float", "str"):
                        arg_type = v.attr
            # action
            action: Optional[str] = None
            if "action" in kw:
                v = kw["action"]
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    action = v.value
                elif isinstance(v, ast.Str):
                    action = v.s
                if action == "store_true":
                    arg_type = "bool"

            # default
            default: Optional[Any] = None
            if "default" in kw:
                v = kw["default"]
                if isinstance(v, ast.Constant):
                    default = v.value
                elif isinstance(v, ast.Str):
                    default = v.s

            # choices
            choices: Optional[List[Any]] = None
            if "choices" in kw:
                v = kw["choices"]
                if isinstance(v, (ast.List, ast.Tuple)):
                    vals = []
                    for elt in v.elts:
                        if isinstance(elt, ast.Constant):
                            vals.append(elt.value)
                        elif isinstance(elt, ast.Str):
                            vals.append(elt.s)
                    choices = vals

            help_text: Optional[str] = None
            if "help" in kw:
                v = kw["help"]
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    help_text = v.value
                elif isinstance(v, ast.Str):
                    help_text = v.s

            argspecs.append(
                ArgSpec(
                    name=name,
                    flags=flags,
                    positional=positional,
                    arg_type=arg_type,
                    default=default,
                    choices=choices,
                    help_text=help_text,
                    action=action,
                )
            )

    return argspecs


def list_runner_modules() -> List[str]:
    """List module names available in the runners package directory."""
    if not os.path.isdir(RUNNERS_DIR):
        return []
    modules: List[str] = []
    for entry in os.listdir(RUNNERS_DIR):
        if not entry.endswith(".py"):
            continue
        if entry.startswith("__"):
            continue
        modules.append(entry[:-3])  # strip .py
    return sorted(modules)


def _home_config_dir() -> str:
    return os.path.join(os.path.expanduser("~"), HOME_CONFIG_DIRNAME)


def get_env_config_path() -> str:
    """Return the path to the home-sourced environment config file."""
    return os.path.join(_home_config_dir(), HOME_CONFIG_FILENAME)


def ensure_default_env_config() -> None:
    """Create a default config.ini with DEV/UAT/PROD sections if missing."""
    cfg_path = get_env_config_path()
    if os.path.exists(cfg_path):
        return
    # Migrate old config from ~/.qf_dashboard/config.ini if present
    old_cfg_path = os.path.join(os.path.expanduser("~"), OLD_HOME_CONFIG_DIRNAME, HOME_CONFIG_FILENAME)
    if os.path.exists(old_cfg_path):
        os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
        try:
            shutil.copy2(old_cfg_path, cfg_path)
            return
        except Exception:
            # Fall back to generating a fresh default if copy fails
            pass
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    cp = configparser.ConfigParser()
    cp["DEV"] = {
        "API_URL": "http://localhost:8000",
        "API_KEY": "dev-key",
        "LOG_LEVEL": "INFO",
        "CONDA_ENV": CONDA_ENV_NAME,
        "CONFIG_PATH": "~/.dashboard/config",
    }
    cp["UAT"] = {
        "API_URL": "https://uat.api.example.com",
        "API_KEY": "uat-key",
        "LOG_LEVEL": "INFO",
        "CONDA_ENV": CONDA_ENV_NAME,
        "CONFIG_PATH": "~/.dashboard/config",
    }
    cp["PROD"] = {
        "API_URL": "https://api.example.com",
        "API_KEY": "prod-key",
        "LOG_LEVEL": "WARNING",
        "CONDA_ENV": CONDA_ENV_NAME,
        "CONFIG_PATH": "~/.dashboard/config",
    }
    with open(cfg_path, "w", encoding="utf-8") as f:
        cp.write(f)


def list_env_names() -> List[str]:
    """List environment names (sections) from the home config file."""
    cfg_path = get_env_config_path()
    cp = configparser.ConfigParser()
    try:
        cp.read(cfg_path)
    except Exception:
        return []
    return list(cp.sections())


def get_env_for(env_name: str) -> Dict[str, str]:
    """Load environment variables (as strings) for the given env section."""
    cfg_path = get_env_config_path()
    cp = configparser.ConfigParser()
    cp.read(cfg_path)
    if env_name not in cp:
        return {}
    section = cp[env_name]
    env_vars: Dict[str, str] = {}
    for key in section:
        env_vars[key.upper()] = str(section.get(key))
    return env_vars


def save_env_for(env_name: str, updates: Dict[str, str]):
    """Persist environment variables for a given section.

    IMPORTANT: Only existing keys in the target section are updated.
    New keys are NOT added. Returns a tuple: (updated_keys, skipped_keys).
    """
    cfg_path = get_env_config_path()
    cp = configparser.ConfigParser()
    try:
        cp.read(cfg_path)
    except Exception:
        # If reading fails, start fresh
        cp = configparser.ConfigParser()
    if env_name not in cp:
        raise ValueError(f"Environment section '{env_name}' not found in config.ini")
    section = cp[env_name]
    updated_keys = []
    skipped_keys = []
    for k, v in updates.items():
        lk = k.lower()
        if lk in section:
            section[lk] = str(v)
            updated_keys.append(k)
        else:
            skipped_keys.append(k)
    if updated_keys:
        os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
        with open(cfg_path, "w", encoding="utf-8") as f:
            cp.write(f)
    return updated_keys, skipped_keys


from typing import Tuple


def conda_env_exists(env_name: str) -> Tuple[bool, str]:
    """Check if a conda environment with the given name exists.

    Returns (exists, detail). If conda is not available or the query fails,
    returns (False, reason).
    """
    if not env_name:
        return False, "No environment name provided"
    try:
        proc = subprocess.run(
            ["conda", "env", "list", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False, "conda executable not found on PATH"
    except Exception as e:
        return False, f"Failed to query conda: {e}"

    if proc.returncode != 0:
        return False, f"conda returned {proc.returncode}: {proc.stderr.strip()}"
    try:
        data = json.loads(proc.stdout)
        env_paths = data.get("envs", [])
        for p in env_paths:
            try:
                if os.path.basename(p.rstrip(os.sep)) == env_name:
                    return True, p
            except Exception:
                continue
        return False, f"Environment '{env_name}' not found"
    except json.JSONDecodeError:
        return False, "Failed to parse conda JSON output"


def _python_executable_for_env(env_name: str) -> Optional[str]:
    """Resolve the Python executable path for a given conda environment name.

    Returns an absolute path or None if resolution fails.
    """
    ok, detail = conda_env_exists(env_name)
    if not ok or not detail:
        return None
    env_path = str(detail)
    # Prefer typical locations
    candidates = [
        os.path.join(env_path, "bin", "python"),                # Unix-like
        os.path.join(env_path, "python.exe"),                     # Windows root
        os.path.join(env_path, "Scripts", "python.exe"),         # Windows Scripts
    ]
    for p in candidates:
        try:
            if os.path.exists(p) and os.access(p, os.X_OK):
                return p
        except Exception:
            continue
    return None


def build_command(
    module_name: str,
    specs: List[ArgSpec],
    values: Dict[str, Any],
    conda_env_name: Optional[str] = None,
    backend: str = "conda",
) -> List[str]:
    """Build a command to run a module from the runners package in the desired env.

    backends:
      - "conda": use `conda run -n <env> python -m <package.module>`
      - "python": resolve the env's Python interpreter path and run `python -m <package.module>` directly
    """
    env_name = (conda_env_name or CONDA_ENV_NAME).strip()
    backend = (backend or "conda").strip().lower()
    if backend == "python":
        pyexe = _python_executable_for_env(env_name)
        if pyexe:
            cmd: List[str] = [
                pyexe,
                "-m",
                f"{RUNNERS_PACKAGE}.{module_name}",
            ]
        else:
            # Fallback to conda backend if interpreter resolution fails
            backend = "conda"
    if backend == "conda":
        cmd = [
            "conda",
            "run",
            "-n",
            env_name,
            "python",
            "-m",
            f"{RUNNERS_PACKAGE}.{module_name}",
        ]
    # Positional first in encounter order
    for spec in specs:
        val = values.get(spec.name)
        if spec.positional:
            if spec.arg_type == "bool":
                if val is not None:
                    cmd.append(str(val))
            else:
                if val is not None and str(val) != "":
                    cmd.append(str(val))
    # Options next
    for spec in specs:
        if spec.positional:
            continue
        flag = spec.preferred_flag()
        if not flag:
            continue
        val = values.get(spec.name)
        if spec.arg_type == "bool" and spec.action == "store_true":
            if bool(val):
                cmd.append(flag)
        else:
            if val is not None and str(val) != "":
                cmd.extend([flag, str(val)])
    return cmd


def run_subprocess(cmd: List[str], cwd: Optional[str] = None, extra_env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    logger = logging.getLogger("dashboard.runners")
    joined = " ".join(shlex.quote(c) for c in cmd)
    logger.info("Executing: %s (cwd=%s)", joined, cwd or os.getcwd())
    try:
        env = os.environ.copy()
        if extra_env:
            env.update({k: str(v) for k, v in extra_env.items()})
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    except Exception:
        logger.exception("Subprocess execution failed")
        raise
    logger.info("Finished with return code: %s", proc.returncode)
    if proc.stdout:
        logger.debug("Stdout:\n%s", proc.stdout[:4000])
    if proc.stderr:
        logger.debug("Stderr:\n%s", proc.stderr[:4000])
    return proc


# --- Asynchronous process management for long-running tasks ---

# Keep track of active processes by PID (lives in process memory; suitable for Streamlit session lifecycle)
ACTIVE_PROCS: Dict[int, subprocess.Popen] = {}
# Map PID to (stdout_path, stderr_path) for attaching/tailing logs later
ACTIVE_LOG_PATHS: Dict[int, Dict[str, str]] = {}
# Map PID to tailer control (thread and stop event)
ACTIVE_TAILERS: Dict[int, Dict[str, Any]] = {}


def start_subprocess(
    cmd: List[str],
    cwd: Optional[str] = None,
    extra_env: Optional[Dict[str, str]] = None,
    log_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """Start a subprocess asynchronously, redirecting output to files.

    Returns dict with keys: pid, stdout_path, stderr_path, started_at.
    """
    logger = logging.getLogger("dashboard.runners")
    env = os.environ.copy()
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})

    os.makedirs(RUN_LOGS_DIR, exist_ok=True)
    prefix = log_prefix or datetime.now().strftime("%Y%m%d-%H%M%S")
    stdout_path = os.path.join(RUN_LOGS_DIR, f"{prefix}.out.log")
    stderr_path = os.path.join(RUN_LOGS_DIR, f"{prefix}.err.log")

    # Open files and launch process; child inherits FDs, safe to close in parent after spawn
    with open(stdout_path, "w", encoding="utf-8") as out, open(stderr_path, "w", encoding="utf-8") as err:
        try:
            # Hint child process to attach logging to these files
            try:
                env["DASHBOARD_CHILD_LOG_STDOUT"] = stdout_path
                env["DASHBOARD_CHILD_LOG_STDERR"] = stderr_path
                # Prefer LOG_LEVEL from extra_env; default INFO
                level = (extra_env or {}).get("LOG_LEVEL") if extra_env else None
                env["DASHBOARD_CHILD_LOG_LEVEL"] = str(level or "INFO").upper()
            except Exception:
                pass
            p = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=out,
                stderr=err,
                text=True,
                env=env,
                start_new_session=True,  # new process group for group termination
            )
        except Exception:
            logger.exception("Failed to start subprocess")
            raise

    # After starting the process, include PID in log filenames for easier tracking.
    try:
        pid_suffix = f"_pid_{p.pid}"
        new_stdout_path = os.path.join(RUN_LOGS_DIR, f"{prefix}{pid_suffix}.out.log")
        new_stderr_path = os.path.join(RUN_LOGS_DIR, f"{prefix}{pid_suffix}.err.log")
        # Attempt to rename existing files; if it fails, keep original paths.
        try:
            os.rename(stdout_path, new_stdout_path)
            stdout_path = new_stdout_path
        except Exception:
            pass
        try:
            os.rename(stderr_path, new_stderr_path)
            stderr_path = new_stderr_path
        except Exception:
            pass
        logger.info(
            "Logs for PID %s: stdout=%s stderr=%s",
            p.pid,
            stdout_path,
            stderr_path,
        )
    except Exception:
        logger.exception("Failed to include PID in log filenames for PID %s", p.pid)

    ACTIVE_PROCS[p.pid] = p
    ACTIVE_LOG_PATHS[p.pid] = {
        "stdout": stdout_path,
        "stderr": stderr_path,
    }
    joined = " ".join(shlex.quote(c) for c in cmd)
    logger.info("Started PID %s: %s (cwd=%s)", p.pid, joined, cwd or os.getcwd())
    # Persist run metadata to central store (best-effort). Include extra_env when available.
    try:
        add_run(p.pid, joined, cwd, stdout_path, stderr_path, extra_env=extra_env)
    except Exception:
        logger.exception("Failed to record run in run_store for PID %s", p.pid)

    # Start a watcher thread to update the run store when the process exits
    def _watch_process(proc: subprocess.Popen, pid: int) -> None:
        try:
            rc = proc.wait()
            try:
                update_run_status(pid, "finished", returncode=rc)
            except Exception:
                logger.exception("Failed to update run status in run_store for PID %s", pid)
        except Exception:
            logger.exception("Process watcher for PID %s failed", pid)

    try:
        t = threading.Thread(target=_watch_process, args=(p, p.pid), daemon=True)
        t.start()
    except Exception:
        logger.exception("Failed to start watcher thread for PID %s", p.pid)
    return {
        "pid": p.pid,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }


def get_status(pid: int) -> Dict[str, Any]:
    """Get running status and return code (if finished) for a PID we started."""
    p = ACTIVE_PROCS.get(pid)
    if not p:
        return {"known": False, "running": False, "returncode": None}
    rc = p.poll()
    return {"known": True, "running": rc is None, "returncode": rc}


def terminate_process(pid: int, force_after: float = 5.0) -> bool:
    """Terminate a running subprocess by PID. Returns True if terminated."""
    logger = logging.getLogger("dashboard.runners")
    p = ACTIVE_PROCS.get(pid)
    if not p:
        return False
    # Send SIGTERM to the whole process group
    try:
        os.killpg(p.pid, signal.SIGTERM)
    except ProcessLookupError:
        ACTIVE_PROCS.pop(pid, None)
        return True
    except Exception:
        logger.exception("Failed to send SIGTERM to PID %s", pid)
        # Fallback to terminate the single process
        try:
            p.terminate()
        except Exception:
            pass

    # Wait briefly for graceful shutdown
    deadline = time.time() + max(0.1, force_after)
    while time.time() < deadline:
        if p.poll() is not None:
            ACTIVE_PROCS.pop(pid, None)
            ACTIVE_LOG_PATHS.pop(pid, None)
            # Stop tailer if running
            try:
                ctl = ACTIVE_TAILERS.pop(pid, None)
                if ctl and isinstance(ctl.get("stop"), threading.Event):
                    ctl["stop"].set()
            except Exception:
                pass
            # Update run store
            try:
                update_run_status(pid, "terminated", returncode=p.returncode)
            except Exception:
                logger.exception("Failed to update run status in run_store for PID %s", pid)
            logger.info("Process %s terminated with rc=%s", pid, p.returncode)
            return True
        time.sleep(0.1)

    # Force kill the group
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass
    ACTIVE_PROCS.pop(pid, None)
    ACTIVE_LOG_PATHS.pop(pid, None)
    try:
        ctl = ACTIVE_TAILERS.pop(pid, None)
        if ctl and isinstance(ctl.get("stop"), threading.Event):
            ctl["stop"].set()
    except Exception:
        pass
    try:
        update_run_status(pid, "killed", returncode=None)
    except Exception:
        logger.exception("Failed to update run status in run_store for PID %s", pid)
    logger.info("Process %s force-killed", pid)
    return True


def attach_log_tail_to_dashboard(pid: int, max_lines: int = 200, label: Optional[str] = None) -> bool:
    """Append the tail of a subprocess's stdout/stderr logs into the dashboard log.

    Returns True if attached successfully, False otherwise.
    """
    logger = logging.getLogger("dashboard.attach")
    paths = ACTIVE_LOG_PATHS.get(pid)
    if not paths:
        # If not tracked (e.g., after restart), try to infer from known runs folder by scanning filenames with pid in name (best-effort)
        return False
    out_path = paths.get("stdout")
    err_path = paths.get("stderr")
    try:
        combined_tail = []
        if out_path and os.path.exists(out_path):
            with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            combined_tail.append("".join(lines[-max_lines:]))
        if err_path and os.path.exists(err_path):
            with open(err_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            if lines:
                # Append raw stderr lines without inserting any header
                combined_tail.append("".join(lines[-max_lines:]))
        text = ("".join(combined_tail)).strip()
        header = f"[ATTACH] PID={pid}{(' '+str(label)) if label else ''}"
        if text:
            # Write as a single info entry; rotation will cap file size
            logger.info("%s\n%s", header, text)
        else:
            logger.info("%s (no output)", header)
        return True
    except Exception:
        logging.getLogger("dashboard.runners").exception("Failed to attach logs for PID %s", pid)
        return False


def _tail_attach_loop(pid: int, label: Optional[str], interval: float, stop_event: threading.Event) -> None:
    """Background loop to attach new stdout/stderr content to dashboard log."""
    logger = logging.getLogger("dashboard.attach")
    p = ACTIVE_PROCS.get(pid)
    paths = ACTIVE_LOG_PATHS.get(pid, {})
    out_path = paths.get("stdout")
    err_path = paths.get("stderr")
    # Track file positions to only read new content
    out_pos = 0
    err_pos = 0
    try:
        if out_path and os.path.exists(out_path):
            out_pos = os.path.getsize(out_path)
        if err_path and os.path.exists(err_path):
            err_pos = os.path.getsize(err_path)
    except Exception:
        out_pos = err_pos = 0

    while not stop_event.is_set():
        try:
            # Exit if process ended
            pcur = ACTIVE_PROCS.get(pid)
            if (pcur is None) or (pcur.poll() is not None):
                break
            chunks: List[str] = []
            if out_path and os.path.exists(out_path):
                with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(out_pos)
                    data = f.read()
                if data:
                    out_pos += len(data)
                    chunks.append(data)
            if err_path and os.path.exists(err_path):
                with open(err_path, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(err_pos)
                    data = f.read()
                if data:
                    err_pos += len(data)
                    # Append stderr output raw; do not inject any header
                    chunks.append(data)
            if chunks:
                header = f"[TAIL] PID={pid}{(' '+str(label)) if label else ''}"
                logger.info("%s\n%s", header, "".join(chunks).rstrip())
        except Exception:
            logging.getLogger("dashboard.runners").exception("Tail attach loop error for PID %s", pid)
        # Sleep briefly
        try:
            time.sleep(max(0.5, float(interval)))
        except Exception:
            time.sleep(1.0)

    # Clean up when exiting
    try:
        ACTIVE_TAILERS.pop(pid, None)
    except Exception:
        pass


def enable_auto_attach(pid: int, label: Optional[str] = None, interval: float = 2.0) -> bool:
    """Start a background tailer to auto-attach new log output to dashboard log."""
    if pid in ACTIVE_TAILERS:
        return True
    if pid not in ACTIVE_PROCS or pid not in ACTIVE_LOG_PATHS:
        return False
    stop_event = threading.Event()
    th = threading.Thread(target=_tail_attach_loop, args=(pid, label, interval, stop_event), daemon=True)
    ACTIVE_TAILERS[pid] = {"thread": th, "stop": stop_event, "interval": interval, "label": label}
    try:
        th.start()
        return True
    except Exception:
        logging.getLogger("dashboard.runners").exception("Failed to start auto attach for PID %s", pid)
        ACTIVE_TAILERS.pop(pid, None)
        return False


def disable_auto_attach(pid: int) -> bool:
    """Stop the background tailer for a PID if running."""
    ctl = ACTIVE_TAILERS.get(pid)
    if not ctl:
        return False
    try:
        stop_event = ctl.get("stop")
        if isinstance(stop_event, threading.Event):
            stop_event.set()
        return True
    except Exception:
        logging.getLogger("dashboard.runners").exception("Failed to stop auto attach for PID %s", pid)
        return False


def auto_attach_enabled(pid: int) -> bool:
    return pid in ACTIVE_TAILERS
