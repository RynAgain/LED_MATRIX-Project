#!/bin/bash
# LED Matrix Project - Service Startup Wrapper
# Called by led-matrix.service.
# Ensures the virtual environment and dependencies exist before launching.
#
# Usage:  sudo bash scripts/start.sh

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
# Quick check: try importing Pillow (a key always-present dependency). If it
# fails, install everything from requirements.txt.
if ! "$VENV_PYTHON" -c "import PIL" 2>/dev/null; then
    log "Dependencies missing -- installing from requirements.txt..."
    "$VENV_PYTHON" -m pip install --quiet --upgrade pip
    "$VENV_PYTHON" -m pip install --quiet -r "$PROJECT_ROOT/requirements.txt"
    log "Dependencies installed"
else
    log "Dependencies OK"
fi

# --- Git safe.directory (service runs as root, repo is user-owned) ---
# git >= 2.35.2 refuses to touch a repo owned by another user ("dubious
# ownership"), which broke the menu's UPDATE fetch and git-describe
# versioning. Register the project in the SYSTEM config (the only scope
# git trusts for safe.directory). Idempotent: only adds if missing.
if command -v git >/dev/null 2>&1; then
    if ! git config --system --get-all safe.directory 2>/dev/null | grep -qxF "$PROJECT_ROOT"; then
        git config --system --add safe.directory "$PROJECT_ROOT" 2>/dev/null \
            && log "Registered $PROJECT_ROOT as a git safe.directory" \
            || log "WARNING: could not register git safe.directory"
    fi
fi

# --- Launch the display service ---
log "Starting LED matrix display service..."
exec "$VENV_PYTHON" "$PROJECT_ROOT/src/main.py"
