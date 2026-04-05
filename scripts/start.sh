#!/bin/bash
# LED Matrix Project - Service Startup Wrapper
# Called by led-matrix.service (and optionally led-matrix-web.service).
# Ensures the virtual environment and dependencies exist before launching.
#
# Usage (display):  sudo bash scripts/start.sh display
# Usage (web):      bash scripts/start.sh web

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PATH="$PROJECT_ROOT/venv"
VENV_PYTHON="$VENV_PATH/bin/python3"
LOG_DIR="$PROJECT_ROOT/logs"

# Ensure logs directory exists (gitignored, may be missing after fresh clone)
mkdir -p "$LOG_DIR"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [START] $1"
}

# --- Check / create virtual environment ---
if [ ! -f "$VENV_PYTHON" ]; then
    log "Virtual environment not found at $VENV_PATH -- creating..."
    python3 -m venv "$VENV_PATH"
    log "Virtual environment created"
fi

# --- Check / install dependencies ---
# Quick check: try importing flask (a key dependency). If it fails, install.
if ! "$VENV_PYTHON" -c "import flask" 2>/dev/null; then
    log "Dependencies missing -- installing from requirements.txt..."
    "$VENV_PYTHON" -m pip install --quiet --upgrade pip
    "$VENV_PYTHON" -m pip install --quiet -r "$PROJECT_ROOT/requirements.txt"
    log "Dependencies installed"
else
    log "Dependencies OK"
fi

# --- Launch the requested service ---
MODE="${1:-display}"

case "$MODE" in
    display)
        log "Starting LED matrix display service..."
        exec "$VENV_PYTHON" "$PROJECT_ROOT/src/main.py"
        ;;
    web)
        log "Starting LED matrix web panel..."
        exec "$VENV_PYTHON" -m src.web.app
        ;;
    *)
        log "Unknown mode: $MODE (expected 'display' or 'web')"
        exit 1
        ;;
esac
