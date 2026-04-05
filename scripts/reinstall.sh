#!/bin/bash
# LED Matrix Project - Clean Slate Reinstall
# Nukes all generated state (venv, logs, systemd units, caches) and
# re-runs install.sh from scratch so the Pi is back to a known-good state.
#
# Usage: sudo bash scripts/reinstall.sh
#
# What this does:
#   1. Stops all LED Matrix systemd services
#   2. Removes old systemd unit files
#   3. Deletes venv/, logs/, __pycache__/, downloaded videos
#   4. Re-runs scripts/install.sh (creates venv, installs deps, registers services)
#   5. Starts services and shows status

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Must be root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root: sudo bash scripts/reinstall.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo ""
echo "=============================================="
log_warn "LED Matrix - CLEAN SLATE REINSTALL"
echo "=============================================="
echo ""
log_warn "This will destroy and recreate:"
echo "  - venv/            (Python virtual environment)"
echo "  - logs/            (log files, PID files, caches)"
echo "  - __pycache__/     (Python bytecode cache)"
echo "  - systemd services (will be re-registered)"
echo ""
echo "  Project root: $PROJECT_ROOT"
echo ""

# Prompt for confirmation (skip if --yes flag provided)
if [[ "$1" != "--yes" && "$1" != "-y" ]]; then
    read -p "Continue? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        log_info "Aborted."
        exit 0
    fi
fi

echo ""

# --- Step 1: Stop services ---
log_info "Step 1/5: Stopping LED Matrix services..."
systemctl stop led-matrix.service 2>/dev/null || true
systemctl stop led-matrix-web.service 2>/dev/null || true
systemctl stop led-matrix-updater.timer 2>/dev/null || true
systemctl stop led-matrix-updater.service 2>/dev/null || true
systemctl disable led-matrix.service 2>/dev/null || true
systemctl disable led-matrix-web.service 2>/dev/null || true
systemctl disable led-matrix-updater.timer 2>/dev/null || true
log_info "Services stopped and disabled"

# --- Step 2: Remove old systemd units ---
log_info "Step 2/5: Removing old systemd unit files..."
rm -f /etc/systemd/system/led-matrix.service
rm -f /etc/systemd/system/led-matrix-web.service
rm -f /etc/systemd/system/led-matrix-updater.service
rm -f /etc/systemd/system/led-matrix-updater.timer
systemctl daemon-reload
log_info "Systemd units removed"

# --- Step 3: Nuke generated state ---
log_info "Step 3/5: Removing generated files..."

# Virtual environment
if [ -d "$PROJECT_ROOT/venv" ]; then
    rm -rf "$PROJECT_ROOT/venv"
    log_info "  Removed venv/"
fi

# Logs directory (will be recreated by install.sh)
if [ -d "$PROJECT_ROOT/logs" ]; then
    rm -rf "$PROJECT_ROOT/logs"
    log_info "  Removed logs/"
fi

# Python bytecode caches
find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$PROJECT_ROOT" -name "*.pyc" -delete 2>/dev/null || true
log_info "  Removed __pycache__ and .pyc files"

# Downloaded videos (keep the placeholder)
find "$PROJECT_ROOT/downloaded_videos" -type f ! -name "placeholder.txt.txt" -delete 2>/dev/null || true
log_info "  Cleaned downloaded_videos/"

log_info "Clean slate ready"

# --- Step 4: Re-run installer ---
log_info "Step 4/5: Running install.sh..."
echo ""
bash "$PROJECT_ROOT/scripts/install.sh"
echo ""

# --- Step 5: Start services and verify ---
log_info "Step 5/5: Starting services..."
systemctl start led-matrix.service
systemctl start led-matrix-web.service
systemctl start led-matrix-updater.timer

# Brief pause for services to initialize
sleep 3

echo ""
echo "=============================================="
log_info "REINSTALL COMPLETE - Service Status:"
echo "=============================================="
echo ""
echo "  led-matrix.service (display):"
systemctl is-active led-matrix.service && echo "    --> RUNNING" || echo "    --> NOT RUNNING (check: journalctl -u led-matrix -e)"
echo ""
echo "  led-matrix-web.service (web panel):"
systemctl is-active led-matrix-web.service && echo "    --> RUNNING" || echo "    --> NOT RUNNING (check: journalctl -u led-matrix-web -e)"
echo ""
echo "  led-matrix-updater.timer (auto-update):"
systemctl is-active led-matrix-updater.timer && echo "    --> RUNNING" || echo "    --> NOT RUNNING"
echo ""
echo "  Troubleshoot:"
echo "    journalctl -u led-matrix.service -f"
echo "    journalctl -u led-matrix-web.service -f"
echo ""
