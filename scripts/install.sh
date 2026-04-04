#!/bin/bash
# LED Matrix Project - Installation Script
# Run this once on a fresh Raspberry Pi to set up everything.
# Usage: sudo bash scripts/install.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check for root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root: sudo bash scripts/install.sh"
    exit 1
fi

# Determine project root (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ACTUAL_USER="${SUDO_USER:-pi}"

log_info "LED Matrix Project Installer"
log_info "Project root: $PROJECT_ROOT"
log_info "Installing for user: $ACTUAL_USER"
echo ""

# --- Step 1: System packages ---
log_info "Step 1/6: Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    git \
    network-manager \
    ffmpeg \
    > /dev/null 2>&1
log_info "System packages installed (including ffmpeg for video processing)"

# --- Step 2: Create virtual environment ---
log_info "Step 2/6: Setting up Python virtual environment..."
VENV_PATH="$PROJECT_ROOT/venv"
if [ ! -d "$VENV_PATH" ]; then
    python3 -m venv "$VENV_PATH"
    log_info "Virtual environment created at $VENV_PATH"
else
    log_info "Virtual environment already exists"
fi

# --- Step 3: Install Python dependencies ---
log_info "Step 3/6: Installing Python dependencies..."
"$VENV_PATH/bin/pip" install --quiet --upgrade pip
"$VENV_PATH/bin/pip" install --quiet -r "$PROJECT_ROOT/requirements.txt"
log_info "Python dependencies installed"

# --- Step 4: Create logs directory ---
log_info "Step 4/6: Creating logs directory..."
mkdir -p "$PROJECT_ROOT/logs"
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$PROJECT_ROOT/logs"
log_info "Logs directory ready"

# --- Step 5: Install systemd services ---
log_info "Step 5/6: Installing systemd services..."

# Display service (runs as root for GPIO/hardware access)
cp "$PROJECT_ROOT/services/led-matrix.service" /etc/systemd/system/led-matrix.service
sed -i "s|/home/pi/LED_MATRIX-Project|$PROJECT_ROOT|g" /etc/systemd/system/led-matrix.service
# NOTE: Display service intentionally runs as root (required by rpi-rgb-led-matrix for GPIO)

# Updater service
cp "$PROJECT_ROOT/services/led-matrix-updater.service" /etc/systemd/system/led-matrix-updater.service
sed -i "s|/home/pi/LED_MATRIX-Project|$PROJECT_ROOT|g" /etc/systemd/system/led-matrix-updater.service
sed -i "s|User=pi|User=$ACTUAL_USER|g" /etc/systemd/system/led-matrix-updater.service
sed -i "s|Group=pi|Group=$ACTUAL_USER|g" /etc/systemd/system/led-matrix-updater.service

# Updater timer
cp "$PROJECT_ROOT/services/led-matrix-updater.timer" /etc/systemd/system/led-matrix-updater.timer

# Web control panel service
cp "$PROJECT_ROOT/services/led-matrix-web.service" /etc/systemd/system/led-matrix-web.service
sed -i "s|/home/pi/LED_MATRIX-Project|$PROJECT_ROOT|g" /etc/systemd/system/led-matrix-web.service
sed -i "s|User=pi|User=$ACTUAL_USER|g" /etc/systemd/system/led-matrix-web.service
sed -i "s|Group=pi|Group=$ACTUAL_USER|g" /etc/systemd/system/led-matrix-web.service

# Reload and enable
systemctl daemon-reload
systemctl enable led-matrix.service
systemctl enable led-matrix-updater.timer
systemctl enable led-matrix-web.service

log_info "Systemd services installed and enabled"

# --- Step 6: Configure WiFi (optional prompt) ---
log_info "Step 6/6: WiFi configuration..."
WIFI_CONFIG="$PROJECT_ROOT/config/wifi.json"

if grep -q "YOUR_WIFI_SSID" "$WIFI_CONFIG" 2>/dev/null; then
    echo ""
    log_warn "WiFi is not configured yet."
    echo "  Edit $WIFI_CONFIG to add your WiFi network(s)."
    echo "  For open/public WiFi, leave password as empty string."
    echo ""
fi

# --- Done ---
echo ""
echo "=============================================="
log_info "Installation complete!"
echo "=============================================="
echo ""
echo "  Next steps:"
echo "    1. Edit config/wifi.json with your WiFi network details"
echo "    2. Edit config/config.json to enable/disable features"
echo "    3. Reboot to start: sudo reboot"
echo ""
echo "  Or start manually:"
echo "    sudo systemctl start led-matrix.service"
echo "    sudo systemctl start led-matrix-updater.timer"
echo ""
echo "  View logs:"
echo "    journalctl -u led-matrix.service -f"
echo "    journalctl -u led-matrix-updater.service -f"
echo ""
