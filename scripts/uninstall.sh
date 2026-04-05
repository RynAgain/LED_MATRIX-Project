#!/bin/bash
# LED Matrix Project - Full Uninstall Script
# Completely removes all LED Matrix services, files, and configuration from the Pi.
#
# Usage: sudo bash scripts/uninstall.sh
#
# What this removes:
#   - All systemd services and timers (stopped, disabled, deleted)
#   - Virtual environment (venv/)
#   - Logs directory (logs/)
#   - Python bytecode caches (__pycache__/, .pyc)
#   - Downloaded videos
#   - Optionally: the entire project directory
#
# What this does NOT touch:
#   - System packages (python3, ffmpeg, etc.)
#   - /boot/config.txt changes (audio disable, etc.)
#   - NetworkManager WiFi profiles

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${CYAN}[STEP]${NC} $1"; }

# Must be root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root: sudo bash scripts/uninstall.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo ""
echo "=============================================="
echo -e "  ${RED}LED Matrix Project - FULL UNINSTALL${NC}"
echo "=============================================="
echo ""
echo "  Project root: $PROJECT_ROOT"
echo ""
echo "  This will:"
echo "    [x] Stop and remove all systemd services"
echo "    [x] Delete venv/ (Python virtual environment)"
echo "    [x] Delete logs/ (log files, PID files, caches)"
echo "    [x] Delete __pycache__/ and .pyc files"
echo "    [x] Delete downloaded videos"
echo "    [ ] Optionally delete the ENTIRE project directory"
echo ""

# Prompt for confirmation (skip if --yes flag provided)
if [[ "$1" != "--yes" && "$1" != "-y" ]]; then
    read -p "Are you sure you want to uninstall? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        log_info "Aborted."
        exit 0
    fi
fi

echo ""

# --- Step 1: Stop all services ---
log_step "Step 1/5: Stopping all LED Matrix services..."

systemctl stop led-matrix.service 2>/dev/null || true
systemctl stop led-matrix-web.service 2>/dev/null || true
systemctl stop led-matrix-updater.timer 2>/dev/null || true
systemctl stop led-matrix-updater.service 2>/dev/null || true

log_info "All services stopped"

# --- Step 2: Disable and remove systemd units ---
log_step "Step 2/5: Removing systemd service files..."

systemctl disable led-matrix.service 2>/dev/null || true
systemctl disable led-matrix-web.service 2>/dev/null || true
systemctl disable led-matrix-updater.timer 2>/dev/null || true
systemctl disable led-matrix-updater.service 2>/dev/null || true

rm -f /etc/systemd/system/led-matrix.service
rm -f /etc/systemd/system/led-matrix-web.service
rm -f /etc/systemd/system/led-matrix-updater.service
rm -f /etc/systemd/system/led-matrix-updater.timer

systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true

log_info "Systemd units removed and daemon reloaded"

# --- Step 3: Remove generated files ---
log_step "Step 3/5: Removing generated files..."

# Virtual environment
if [ -d "$PROJECT_ROOT/venv" ]; then
    rm -rf "$PROJECT_ROOT/venv"
    log_info "  Removed venv/"
else
    log_info "  venv/ not found (already clean)"
fi

# Logs directory
if [ -d "$PROJECT_ROOT/logs" ]; then
    rm -rf "$PROJECT_ROOT/logs"
    log_info "  Removed logs/"
else
    log_info "  logs/ not found (already clean)"
fi

# Python bytecode caches
PYCACHE_COUNT=$(find "$PROJECT_ROOT" -type d -name "__pycache__" 2>/dev/null | wc -l)
find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$PROJECT_ROOT" -name "*.pyc" -delete 2>/dev/null || true
log_info "  Removed $PYCACHE_COUNT __pycache__ directories"

# Downloaded videos (keep placeholder)
if [ -d "$PROJECT_ROOT/downloaded_videos" ]; then
    find "$PROJECT_ROOT/downloaded_videos" -type f ! -name "placeholder.txt.txt" -delete 2>/dev/null || true
    log_info "  Cleaned downloaded_videos/"
fi

# .pytest_cache
if [ -d "$PROJECT_ROOT/.pytest_cache" ]; then
    rm -rf "$PROJECT_ROOT/.pytest_cache"
    log_info "  Removed .pytest_cache/"
fi

# --- Step 4: Verify cleanup ---
log_step "Step 4/5: Verifying cleanup..."

ALL_CLEAN=true

if systemctl list-unit-files 2>/dev/null | grep -q "led-matrix"; then
    log_warn "Some led-matrix units still registered (may need reboot)"
    ALL_CLEAN=false
else
    log_info "No led-matrix systemd units found"
fi

if [ -d "$PROJECT_ROOT/venv" ]; then
    log_warn "venv/ still exists"
    ALL_CLEAN=false
fi

if [ -d "$PROJECT_ROOT/logs" ]; then
    log_warn "logs/ still exists"
    ALL_CLEAN=false
fi

if $ALL_CLEAN; then
    log_info "All generated files removed successfully"
fi

# --- Step 5: Optionally remove entire project ---
log_step "Step 5/5: Remove project directory?"
echo ""
echo "  The project source code is still at: $PROJECT_ROOT"
echo "  You can re-clone it later with:"
echo "    git clone https://github.com/RynAgain/LED_MATRIX-Project.git"
echo ""

if [[ "$1" == "--all" ]]; then
    DELETE_ALL="y"
else
    read -p "  Delete the ENTIRE project directory? [y/N] " DELETE_ALL
fi

if [[ "$DELETE_ALL" =~ ^[Yy]$ ]]; then
    log_warn "Deleting entire project directory: $PROJECT_ROOT"
    # We need to cd out of the project before deleting it
    cd /tmp
    rm -rf "$PROJECT_ROOT"
    log_info "Project directory deleted"
else
    log_info "Project directory kept at: $PROJECT_ROOT"
fi

# --- Done ---
echo ""
echo "=============================================="
log_info "UNINSTALL COMPLETE"
echo "=============================================="
echo ""
echo "  What was removed:"
echo "    - Systemd services (led-matrix, led-matrix-web, led-matrix-updater)"
echo "    - Virtual environment (venv/)"
echo "    - Log files (logs/)"
echo "    - Python caches (__pycache__/)"
echo "    - Downloaded videos"
echo ""
echo "  What was NOT removed (manual cleanup if needed):"
echo "    - System packages: python3, ffmpeg, network-manager"
echo "      Remove with: sudo apt-get remove ffmpeg network-manager"
echo "    - /boot/config.txt changes (dtparam=audio=off)"
echo "      Revert with: sudo sed -i 's/^dtparam=audio=off/dtparam=audio=on/' /boot/config.txt"
echo "    - NetworkManager WiFi profiles"
echo "      List with: nmcli connection show"
echo ""
echo "  To reinstall later:"
echo "    git clone https://github.com/RynAgain/LED_MATRIX-Project.git"
echo "    cd LED_MATRIX-Project"
echo "    sudo bash scripts/install.sh"
echo ""
