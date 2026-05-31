#!/bin/bash
# Double-click this file to launch LumSat on macOS.
# It sets up a local Python environment the first time, then runs the app.
set -e

# Always work from the folder this script lives in, no matter where it's launched from.
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Python 3 was not found. Install it from https://www.python.org/downloads/ and try again."
    echo "Press Return to close."
    read -r _
    exit 1
fi

# Create the virtual environment on first run.
if [ ! -d ".venv" ]; then
    echo "First run: creating a local Python environment (this happens once)…"
    "$PYTHON" -m venv .venv
fi

# Use the venv's interpreter directly — no need to 'activate'.
VENV_PY=".venv/bin/python"

# Install/update dependencies. pip is quick when everything is already present.
echo "Checking dependencies…"
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -r requirements.txt

echo "Launching LumSat…"
exec "$VENV_PY" main.py
