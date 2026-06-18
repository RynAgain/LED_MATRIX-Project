#!/bin/bash
# LED Matrix Project - Update Script
# Called by led-matrix-updater.timer OR manually.
# Strategy: git fetch + reset --hard (always works regardless of local state).
# Then: check if requirements changed, reinstall service files, restart.

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

# ──────────────────────────────────────────────────────────────────────────────
# Pre-flight: Remove stale git lock if older than 5 minutes
# ──────────────────────────────────────────────────────────────────────────────
LOCK_FILE="$PROJECT_ROOT/.git/index.lock"
if [ -f "$LOCK_FILE" ]; then
    LOCK_AGE=$(( $(date +%s) - $(stat -c %Y "$LOCK_FILE" 2>/dev/null || echo 0) ))
    if [ "$LOCK_AGE" -gt 300 ]; then
        rm -f "$LOCK_FILE"
        log "Removed stale git lock (age: ${LOCK_AGE}s)"
    else
        log "WARNING: git lock exists (age: ${LOCK_AGE}s), waiting..."
        sleep 30
        # If still there after waiting, remove it
        if [ -f "$LOCK_FILE" ]; then
            rm -f "$LOCK_FILE"
            log "Removed git lock after waiting 30s"
        fi
    fi
fi

# ──────────────────────────────────────────────────────────────────────────────
# Pre-flight: Check network connectivity
# ──────────────────────────────────────────────────────────────────────────────
log "Checking network connectivity..."
if ! timeout 10 git ls-remote --exit-code origin HEAD >/dev/null 2>&1; then
    log "ERROR: Cannot reach git remote. Network down or remote unavailable."
    exit 1
fi

log "Starting update..."

# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Save current HEAD so we can detect what changed
# ──────────────────────────────────────────────────────────────────────────────
OLD_HEAD=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
log "Current HEAD: ${OLD_HEAD:0:8}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 1.5: Backup tracked config files BEFORE reset overwrites them
# ──────────────────────────────────────────────────────────────────────────────
# config/config.json, controller.json, etc. are tracked by git.
# git reset --hard will overwrite them with upstream versions.
# We back them up so we can restore user customizations after reset.
CONFIG_BACKUP_DIR=$(mktemp -d "/tmp/led-matrix-config-XXXXXX")
log "Backing up config files to $CONFIG_BACKUP_DIR..."
BACKED_UP=0
for CFG_FILE in "$PROJECT_ROOT"/config/*.json; do
    if [ -f "$CFG_FILE" ]; then
        cp "$CFG_FILE" "$CONFIG_BACKUP_DIR/" 2>/dev/null && BACKED_UP=$((BACKED_UP + 1))
    fi
done
log "Backed up $BACKED_UP config files"

# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Fetch + hard reset (guaranteed to work regardless of local state)
# ──────────────────────────────────────────────────────────────────────────────
log "Running git fetch origin main..."
if ! timeout 60 git fetch origin main 2>&1 | tee -a "$LOG_FILE"; then
    log "ERROR: git fetch failed. Network issue or remote unreachable."
    rm -rf "$CONFIG_BACKUP_DIR"
    exit 1
fi

# Check if we're already up to date
NEW_HEAD=$(git rev-parse origin/main 2>/dev/null || echo "unknown")
if [ "$OLD_HEAD" = "$NEW_HEAD" ]; then
    log "Already up to date (${OLD_HEAD:0:8}). Nothing to do."
    rm -rf "$CONFIG_BACKUP_DIR"
    exit 0
fi

log "Running git reset --hard origin/main..."
if ! timeout 30 git reset --hard origin/main 2>&1 | tee -a "$LOG_FILE"; then
    log "ERROR: git reset --hard failed. Attempting recovery..."
    # Nuclear recovery: remove index and retry
    rm -f "$PROJECT_ROOT/.git/index.lock"
    rm -f "$PROJECT_ROOT/.git/index"
    git read-tree HEAD 2>/dev/null || true
    if ! timeout 30 git reset --hard origin/main 2>&1 | tee -a "$LOG_FILE"; then
        log "ERROR: Reset recovery failed. Manual intervention required."
        # Restore configs even on failure so user isn't left broken
        cp "$CONFIG_BACKUP_DIR"/*.json "$PROJECT_ROOT/config/" 2>/dev/null || true
        rm -rf "$CONFIG_BACKUP_DIR"
        exit 1
    fi
fi

log "Code updated: ${OLD_HEAD:0:8} -> ${NEW_HEAD:0:8}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 2.5: Restore user config files from backup
# ──────────────────────────────────────────────────────────────────────────────
# Restore backed-up config files (user's carousel toggles, API keys, etc.)
# This overwrites whatever the upstream reset brought in for config/*.json
RESTORED=0
for CFG_FILE in "$CONFIG_BACKUP_DIR"/*.json; do
    if [ -f "$CFG_FILE" ]; then
        BASENAME=$(basename "$CFG_FILE")
        cp "$CFG_FILE" "$PROJECT_ROOT/config/$BASENAME" 2>/dev/null && RESTORED=$((RESTORED + 1))
    fi
done
rm -rf "$CONFIG_BACKUP_DIR"
log "Restored $RESTORED config files from pre-update backup"

# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Clean untracked files that may conflict with new tracked files
# ──────────────────────────────────────────────────────────────────────────────
# Exclude config/ and logs/ from cleaning (user data)
git clean -fd --exclude=config/ --exclude=logs/ --exclude=venv/ --exclude=downloaded_videos/ 2>&1 | tee -a "$LOG_FILE"

# ──────────────────────────────────────────────────────────────────────────────
# Step 4: Install/update dependencies if requirements.txt changed
# ──────────────────────────────────────────────────────────────────────────────
if [ "$OLD_HEAD" != "unknown" ]; then
    # Compare old HEAD to new HEAD for requirements changes (works across multi-commit jumps)
    if git diff "$OLD_HEAD" "$NEW_HEAD" --name-only 2>/dev/null | grep -q "requirements.txt"; then
        log "requirements.txt changed between $OLD_HEAD and $NEW_HEAD, upgrading dependencies..."
        timeout 300 $VENV_PYTHON -m pip install --upgrade -r requirements.txt --quiet 2>&1 | tee -a "$LOG_FILE"
        PIP_EXIT=$?
        if [ $PIP_EXIT -ne 0 ]; then
            log "WARNING: pip upgrade failed (exit $PIP_EXIT). Trying install without --upgrade..."
            timeout 300 $VENV_PYTHON -m pip install -r requirements.txt --quiet 2>&1 | tee -a "$LOG_FILE"
        fi
    fi
else
    # Can't detect changes (fresh clone or corrupted state) — always install
    log "Could not determine old HEAD, installing all dependencies..."
    timeout 300 $VENV_PYTHON -m pip install --upgrade -r requirements.txt --quiet 2>&1 | tee -a "$LOG_FILE"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Step 5: Re-install service files if they changed (self-update capability)
# ──────────────────────────────────────────────────────────────────────────────
SERVICES_CHANGED=false
if [ "$OLD_HEAD" != "unknown" ]; then
    if git diff "$OLD_HEAD" "$NEW_HEAD" --name-only 2>/dev/null | grep -q "^services/"; then
        SERVICES_CHANGED=true
    fi
    if git diff "$OLD_HEAD" "$NEW_HEAD" --name-only 2>/dev/null | grep -q "^scripts/"; then
        SERVICES_CHANGED=true
    fi
fi

if [ "$SERVICES_CHANGED" = true ]; then
    log "Service/script files changed, re-installing..."
    ACTUAL_USER="${SUDO_USER:-$(whoami)}"
    ACTUAL_HOME=$(eval echo "~$ACTUAL_USER")

    for SVC_FILE in led-matrix.service led-matrix-updater.service led-matrix-updater.timer; do
        SRC="$PROJECT_ROOT/services/$SVC_FILE"
        DST="/etc/systemd/system/$SVC_FILE"
        if [ -f "$SRC" ]; then
            sudo cp "$SRC" "$DST"
            sudo sed -i "s|/home/ryn/LED_MATRIX-Project|$PROJECT_ROOT|g" "$DST"
            sudo sed -i "s|User=ryn|User=$ACTUAL_USER|g" "$DST"
            sudo sed -i "s|Group=ryn|Group=$ACTUAL_USER|g" "$DST"
            sudo sed -i "s|HOME=/home/ryn|HOME=$ACTUAL_HOME|g" "$DST"
            log "Updated $SVC_FILE"
        fi
    done

    sudo systemctl daemon-reload
    log "Systemd daemon reloaded"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Step 6: Restart the display service
# ──────────────────────────────────────────────────────────────────────────────
log "Restarting led-matrix.service..."
sudo systemctl restart led-matrix.service
RESTART_EXIT=$?

if [ $RESTART_EXIT -eq 0 ]; then
    log "Service restarted successfully"
else
    log "WARNING: Service restart failed (exit $RESTART_EXIT). Attempting start..."
    sudo systemctl start led-matrix.service
fi

# ──────────────────────────────────────────────────────────────────────────────
# Cleanup: Rotate log if too large (> 2MB)
# ──────────────────────────────────────────────────────────────────────────────
if [ -f "$LOG_FILE" ]; then
    LOG_SIZE=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$LOG_SIZE" -gt 2097152 ]; then
        mv "$LOG_FILE" "$LOG_FILE.old"
        log "Log rotated (was ${LOG_SIZE} bytes)"
    fi
fi

log "Update complete (${OLD_HEAD:0:8} -> ${NEW_HEAD:0:8})"
exit 0
