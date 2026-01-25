#!/usr/bin/env bash
set -euo pipefail

# run_dashboard.sh
# Prompt for a conda environment, check for required packages (streamlit),
# offer to install from requirements.txt if missing, then run the Streamlit dashboard.

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_ENV="qf"

echo "Run Streamlit dashboard from: $BASE_DIR/dashboard"
read -r -p "Conda environment name to use [${DEFAULT_ENV}]: " CONDA_ENV
CONDA_ENV="${CONDA_ENV:-$DEFAULT_ENV}"

if ! command -v conda >/dev/null 2>&1; then
  echo "Error: 'conda' not found on PATH. Please install Anaconda/Miniconda or add conda to PATH." >&2
  exit 1
fi

#!/usr/bin/env bash
set -euo pipefail

# run_dashboard.sh
# Interactive helper to manage conda envs and run the Streamlit dashboard.

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_ENV="qf"
REQS1="${BASE_DIR}/requirements.txt"
REQS2="${BASE_DIR}/dashboard/requirements.txt"
ENV_YML="${BASE_DIR}/environment.yml"

if ! command -v conda >/dev/null 2>&1; then
  echo "Error: 'conda' not found on PATH. Please install Anaconda/Miniconda or add conda to PATH." >&2
  exit 1
fi

_choose_env() {
  read -r -p "Conda environment name to use [${DEFAULT_ENV}]: " CONDA_ENV
  CONDA_ENV="${CONDA_ENV:-$DEFAULT_ENV}"
}

_install_requirements() {
  local env="$1"
  local reqs="$2"
  if [ ! -f "$reqs" ]; then
    echo "Requirements file not found: $reqs" >&2
    return 1
  fi
  echo "Installing requirements from $reqs into env '$env'..."
  conda run -n "$env" pip install -r "$reqs"
}

_install_packages() {
  local env="$1"
  shift
  local pkgs=("$@")
  if [ ${#pkgs[@]} -eq 0 ]; then
    read -r -p "Enter package(s) to install (space-separated, pip-style): " line
    read -r -a pkgs <<< "$line"
  fi
  if [ ${#pkgs[@]} -eq 0 ]; then
    echo "No packages provided, aborting."
    return 1
  fi
  echo "Installing packages into '$env': ${pkgs[*]}"
  conda run -n "$env" pip install "${pkgs[@]}"
}

_create_env_from_yml() {
  local env="$1"
  if [ ! -f "$ENV_YML" ]; then
    echo "No environment.yml found at $ENV_YML" >&2
    return 1
  fi
  echo "Creating conda env '$env' from $ENV_YML..."
  conda env create -f "$ENV_YML" -n "$env"
}

_run_dashboard() {
  local env="$1"
  echo "Launching Streamlit in env '$env' (press Ctrl-C to stop)..."
  cd "$BASE_DIR/dashboard"
  exec conda run -n "$env" streamlit run dashboard.py --server.fileWatcherType=watchdog --server.runOnSave=true
}

print_menu() {
  cat <<MENU
Select an action:
  1) Check conda environments (list)
  2) Check a conda env for missing packages (streamlit or requirements.txt)
  3) Install requirements.txt into a conda env
  4) Install specific Python packages into a conda env
  5) Create conda env from environment.yml
  6) Run the dashboard in a conda env
  7) Quit
MENU
}

while true; do
  print_menu
  read -r -p "Choice [1-7]: " choice
  case "$choice" in
    1)
      echo "Available conda environments:"
      conda env list
      ;;
    2)
      _choose_env
      echo "Checking for missing packages in '$CONDA_ENV'..."
      if [ -f "$REQS1" ]; then
        mods=$(awk '{print $1}' "$REQS1" | grep -v '^#' | tr '\n' ' ')
      elif [ -f "$REQS2" ]; then
        mods=$(awk '{print $1}' "$REQS2" | grep -v '^#' | tr '\n' ' ')
      else
        mods="streamlit"
      fi
      echo "Probing for: $mods"
      missing=$(conda run -n "$CONDA_ENV" python - <<PY
import importlib.util, json, sys
mods = sys.argv[1:]
missing = []
for m in mods:
    if importlib.util.find_spec(m) is None:
        missing.append(m)
print(json.dumps(missing))
PY
"$mods" 2>/dev/null || echo "[]")
      echo "Missing: $missing"
      ;;
    3)
      _choose_env
      if [ -f "$REQS1" ]; then
        read -r -p "Install from $REQS1 into '$CONDA_ENV'? [Y/n]: " ans
        ans="${ans:-Y}"
        if [[ "$ans" =~ ^([yY]|$) ]]; then
          _install_requirements "$CONDA_ENV" "$REQS1"
        fi
      elif [ -f "$REQS2" ]; then
        read -r -p "Install from $REQS2 into '$CONDA_ENV'? [Y/n]: " ans
        ans="${ans:-Y}"
        if [[ "$ans" =~ ^([yY]|$) ]]; then
          _install_requirements "$CONDA_ENV" "$REQS2"
        fi
      else
        echo "No requirements.txt found in $REQS1 or $REQS2"
      fi
      ;;
    4)
      _choose_env
      read -r -p "Enter package(s) to install (space-separated): " pkgs
      if [ -n "$pkgs" ]; then
        _install_packages "$CONDA_ENV" $pkgs
      fi
      ;;
    5)
      _choose_env
      read -r -p "Create env '$CONDA_ENV' from environment.yml? [Y/n]: " ans
      ans="${ans:-Y}"
      if [[ "$ans" =~ ^([yY]|$) ]]; then
        _create_env_from_yml "$CONDA_ENV"
      fi
      ;;
    6)
      _choose_env
      _run_dashboard "$CONDA_ENV"
      ;;
    7)
      echo "Bye"
      exit 0
      ;;
    *)
      echo "Invalid choice"
      ;;
  esac
done
