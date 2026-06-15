#!/bin/bash
# LED Matrix Project - Update Script
# Called by led-matrix-updater.timer OR manually.
# Simply: git pull, install deps if requirements changed, restart service.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python3"
LOG_FILE="$PROJECT_ROOT/logs/updater.log"

mkdir -p "$PROJECT_ROOT/logs"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [UPDATE] $1" | tee -a "$LOG_FILE"
}

# Use venv python if available, fallback to system python
if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
fi

cd "$PROJECT_ROOT" || { log "ERROR: Cannot cd to $PROJECT_ROOT"; exit 1; }

# Remove stale git lock if older than 5 minutes
LOCK_FILE="$PROJECT_ROOT/.git/index.lock"
if [ -f "$LOCK_FILE" ]; then
    LOCK_AGE=$(( $(date +%s) - $(stat -c %Y "$LOCK_FILE" 2>/dev/null || echo 0) ))
    if [ "$LOCK_AGE" -gt 300 ]; then
        rm -f "$LOCK_FILE"
        log "Removed stale git lock (age: ${LOCK_AGE}s)"
    fi
fi

log "Starting update..."

# Step 1: git pull (simple, clean)
log "Running git pull..."
PULL_OUTPUT=$(git pull 2>&1)
PULL_EXIT=$?

if [ $PULL_EXIT -eq 0 ]; then
    log "git pull OK: $PULL_OUTPUT"
else
    log "git pull failed (exit $PULL_EXIT): $PULL_OUTPUT"
    log "Trying git fetch + reset --hard..."
    git fetch origin main 2>&1 | tee -a "$LOG_FILE"
    git reset --hard origin/main 2>&1 | tee -a "$LOG_FILE"
    if [ $? -ne 0 ]; then
        log "ERROR: Both pull and reset failed. Manual intervention needed."
        exit 1
    fi
    log "Hard reset succeeded"
fi

# Step 2: Install/update dependencies if requirements.txt changed
if git diff HEAD~1 --name-only 2>/dev/null | grep -q "requirements.txt"; then
    log "requirements.txt changed, updating dependencies..."
    $VENV_PYTHON -m pip install -r requirements.txt --quiet 2>&1 | tee -a "$LOG_FILE"
fi

# Step 3: Restart the display service
log "Restarting led-matrix.service..."
sudo systemctl restart led-matrix.service
RESTART_EXIT=$?

if [ $RESTART_EXIT -eq 0 ]; then
    log "Service restarted successfully"
else
    log "WARNING: Service restart failed (exit $RESTART_EXIT)"
fi

# Rotate log if too large (> 2MB)
if [ -f "$LOG_FILE" ]; then
    LOG_SIZE=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$LOG_SIZE" -gt 2097152 ]; then
        mv "$LOG_FILE" "$LOG_FILE.old"
        log "Log rotated"
    fi
fi

log "Update complete"
exit 0
