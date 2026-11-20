#!/usr/bin/env bash
set -euo pipefail

# Resolve paths relative to this script, not the caller's directory.
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

VENV_DIR="$ROOT_DIR/ICT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

trap 'printf "\nERROR: Launcher failed at line %s. Review the messages above.\n" "$LINENO" >&2' ERR

printf '%s\n' \
    "============================================================" \
    "Dynamic Moisture-Triggered Seed Release System" \
    "============================================================"
printf '\n'

if [[ ! -f "$ROOT_DIR/requirements.txt" ]]; then
    printf 'ERROR: requirements.txt was not found beside this launcher.\n' >&2
    exit 1
fi

if [[ ! -f "$ROOT_DIR/final_dashboard.py" ]]; then
    printf 'ERROR: final_dashboard.py was not found beside this launcher.\n' >&2
    exit 1
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
    # Do not overwrite an existing environment from another platform
    # or an environment that needs manual repair.
    if [[ -e "$VENV_DIR" ]]; then
        printf '%s\n' \
            "ERROR: ICT/.venv exists but has no usable bin/python." \
            "It may be incomplete or belong to another operating system." \
            "Rename that environment, then run this launcher again." >&2
        exit 1
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        printf 'ERROR: Python 3 is required. Install it and retry.\n' >&2
        exit 1
    fi

    printf 'Creating the Python virtual environment in ICT/.venv...\n'
    mkdir -p "$ROOT_DIR/ICT"
    python3 -m venv "$VENV_DIR"
fi

printf 'Using Python: '
"$VENV_PYTHON" --version

printf '\nChecking and installing application dependencies...\n'
"$VENV_PYTHON" -m pip install -r "$ROOT_DIR/requirements.txt"

printf '\nStarting the dashboard...\n'
printf 'Keep this terminal open while using the application.\n'
printf 'Press Ctrl+C to stop the dashboard.\n\n'

exec "$VENV_PYTHON" -m streamlit run "$ROOT_DIR/final_dashboard.py"