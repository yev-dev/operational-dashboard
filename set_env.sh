#!/usr/bin/env bash
# set_env.sh
# Usage (recommended): source set_env.sh [ENV] [CONFIG_PATH]
# If sourced, this will export variables into your current shell. Default ENV=PROD
# Example: source set_env.sh DEV /home/user/.operational_dashboard/config.ini

CONFIG_PATH_DEFAULT="$HOME/.dashboard/config.ini"

target_env="$1"
config_path="$2"

if [ -z "$config_path" ]; then
  config_path="$CONFIG_PATH_DEFAULT"
fi

# Detect if the script is being sourced
# In bash/zsh, when sourced, $BASH_SOURCE[0] != $0 (bash) or $ZSH_NAME present for zsh
sourced=0
# bash/zsh compatibility
if [ -n "${BASH_SOURCE[0]:-}" ]; then
  if [ "${BASH_SOURCE[0]}" != "$0" ]; then
    sourced=1
  fi
elif [ -n "$ZSH_NAME" ]; then
  # zsh: $0 will hold the shell name when sourced
  case $0 in
    -zsh|zsh) sourced=1 ;;
    *) sourced=0 ;;
  esac
fi

# Prompt for environment if not provided
if [ -z "$target_env" ]; then
  read -e -p "Environment [PROD]: " env_input
  target_env="${env_input:-PROD}"
fi

if [ ! -f "$config_path" ]; then
  echo "Config file not found: $config_path" >&2
  if [ "$sourced" -eq 1 ]; then
    return 1 2>/dev/null || true
  else
    exit 1
  fi
fi

# Extract lines belonging to the requested section (simple INI parsing)
# We ignore blank lines and comment lines starting with # or ;
mapfile -t kv_lines < <(awk -v sec="[$target_env]" '
  BEGIN{found=0}
  /^\s*\[/ {gsub(/^[ \t]+|[ \t]+$/,"",$0); found = ($0==sec)}
  found && $0 !~ /^\s*\[/ { if ($0 ~ /=/) print $0 }
' "$config_path")

if [ ${#kv_lines[@]} -eq 0 ]; then
  echo "No keys found under section [$target_env] in $config_path" >&2
  if [ "$sourced" -eq 1 ]; then
    return 2 2>/dev/null || true
  else
    exit 2
  fi
fi

# Function to trim whitespace
_trim() { echo "$1" | sed -e 's/^[ \t]*//' -e 's/[ \t]*$//' ; }

exported_list=()
for line in "${kv_lines[@]}"; do
  # strip comments after value
  line="$(echo "$line" | sed -e 's/[;#].*$//')"
  # trim
  line="$( _trim "$line" )"
  [ -z "$line" ] && continue
  # split on first '='
  key="${line%%=*}"
  val="${line#*=}"
  key="$( _trim "$key" )"
  val="$( _trim "$val" )"
  # remove surrounding quotes from val
  val="${val%\"}"
  val="${val#\"}"
  val="${val%\'}"
  val="${val#\'}"
  # Normalize key to uppercase and safe characters
  key_up="$(echo "$key" | tr '[:lower:]' '[:upper:]' | sed 's/[^A-Z0-9_]/_/g')"

  # Export into current shell (works only if sourced)
  export "$key_up=$val"
  exported_list+=("$key_up")
done

# Print summary
echo "Set environment variables for [$target_env] from $config_path:"
for k in "${exported_list[@]}"; do
  # Use printf to show empty values clearly
  printf "  %s=%s\n" "$k" "${!k}"
done

if [ "$sourced" -eq 0 ]; then
  echo "Note: To export variables into your current shell, source this script instead of executing it:"
  echo "  source $0 $target_env $config_path"
fi

# If sourced, return success
if [ "$sourced" -eq 1 ]; then
  return 0 2>/dev/null || true
fi
exit 0
