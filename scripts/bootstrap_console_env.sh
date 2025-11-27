#!/usr/bin/env bash
set -euo pipefail

# Bootstrap a local environment for the Enigmatic console and CLI.
# This script should be sourced to preserve environment variables:
#   source scripts/bootstrap_console_env.sh

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to create a virtual environment." >&2
  return 1 2>/dev/null || exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment at .venv …"
  python3 -m venv .venv
else
  echo "Reusing existing virtual environment at .venv"
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

rpc_user_default=${DGB_RPC_USER:-rpcuser}
rpc_pass_default=${DGB_RPC_PASSWORD:-rpcpass}

read -rp "DGB RPC user [${rpc_user_default}]: " rpc_user_input
read -srp "DGB RPC password [${rpc_pass_default}]: " rpc_pass_input
printf "\n"

rpc_user=${rpc_user_input:-$rpc_user_default}
rpc_pass=${rpc_pass_input:-$rpc_pass_default}

export DGB_RPC_USER="$rpc_user"
export DGB_RPC_PASSWORD="$rpc_pass"

if command -v enigmatic-dgb >/dev/null 2>&1; then
  enigmatic-dgb --help >/dev/null
fi

echo "Environment prepared."
echo "- Virtual environment: $(python -c 'import sys; print(sys.prefix)')"
echo "- DGB_RPC_USER exported as: $DGB_RPC_USER"
echo "- DGB_RPC_PASSWORD exported."
echo
cat <<'NEXT_STEPS'
Next steps:
  1. Ensure the virtualenv is active: source .venv/bin/activate
  2. Launch the console when ready: enigmatic-dgb console
  3. Use the CLI directly: enigmatic-dgb --help
NEXT_STEPS
