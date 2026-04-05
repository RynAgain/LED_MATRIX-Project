#!/bin/bash
# LED Matrix Project - Update Script
# Called by led-matrix-updater.timer via led-matrix-updater.service
# Checks GitHub for changes and applies updates.

set -e

# Determine project root (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python3"
LOG_FILE="$PROJECT_ROOT/logs/updater.log"

# Ensure logs directory exists
mkdir -p "$PROJECT_ROOT/logs"

log() {
    local msg="$(date '+%Y-%m-%d %H:%M:%S') [UPDATE] $1"
    echo "$msg" | tee -a "$LOG_FILE"
}

# Use venv python if available, fallback to system python
if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
    log "Virtual environment not found, using system Python"
fi

log "Starting update check..."

# Ensure WiFi connectivity first
log "Checking WiFi connectivity..."
"$VENV_PYTHON" -m src.wifi.manager connect 2>&1 | tee -a "$LOG_FILE" || {
    log "WARNING: WiFi connection check failed, attempting update anyway"
}

# Keep yt-dlp updated from GitHub source (gets fixes hours before PyPI release)
log "Updating yt-dlp from GitHub..."
"$VENV_PYTHON" -m pip install --upgrade --quiet "yt-dlp @ https://github.com/yt-dlp/yt-dlp/archive/master.tar.gz" 2>&1 | tee -a "$LOG_FILE" || {
    # Fallback to PyPI if GitHub source fails
    log "GitHub install failed, trying PyPI..."
    "$VENV_PYTHON" -m pip install --upgrade --quiet yt-dlp 2>&1 | tee -a "$LOG_FILE" || {
        log "WARNING: yt-dlp update failed (non-fatal)"
    }
}

# Run the auto-updater
cd "$PROJECT_ROOT"
"$VENV_PYTHON" -m src.updater.auto_update update 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

if [ $EXIT_CODE -eq 0 ]; then
    log "Update applied successfully"
else
    log "No update needed or update failed (exit code: $EXIT_CODE)"
fi

# Rotate log if it's too large (> 5MB)
if [ -f "$LOG_FILE" ] && [ $(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE" 2>/dev/null || echo 0) -gt 5242880 ]; then
    mv "$LOG_FILE" "$LOG_FILE.old"
    log "Log rotated"
fi

exit 0
