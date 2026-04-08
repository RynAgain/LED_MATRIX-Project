#!/bin/bash
# LED Matrix Project - Installation Script
# Run this once on a fresh Raspberry Pi to set up everything.
# Usage: sudo bash scripts/install.sh
#
# What this does:
#   1. Installs system packages (python3, build tools, ffmpeg, etc.)
#   2. Creates a Python virtual environment
#   3. Installs Python pip dependencies
#   4. Clones & compiles rpi-rgb-led-matrix C library + Python bindings
#   5. Disables onboard audio (GPIO 18 conflict with LED matrix)
#   6. Creates logs directory
#   7. Installs systemd services
#   8. Prompts for WiFi configuration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
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
ACTUAL_HOME=$(eval echo "~$ACTUAL_USER")

# Detect platform (skip hardware steps on non-Pi systems)
IS_PI=false
if [ -f /proc/device-tree/model ] && grep -qi "raspberry" /proc/device-tree/model 2>/dev/null; then
    IS_PI=true
fi

TOTAL_STEPS=8
if [ "$IS_PI" = false ]; then
    TOTAL_STEPS=6
fi

log_info "LED Matrix Project Installer"
log_info "Project root: $PROJECT_ROOT"
log_info "Installing for user: $ACTUAL_USER"
if [ "$IS_PI" = true ]; then
    PI_MODEL=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo "Unknown")
    log_info "Detected: $PI_MODEL"
else
    log_warn "Not running on a Raspberry Pi -- skipping hardware steps"
fi
echo ""

STEP=0

# ---------------------------------------------------------------------------
# Step 1: System packages
# ---------------------------------------------------------------------------
STEP=$((STEP + 1))
log_info "Step $STEP/$TOTAL_STEPS: Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    network-manager \
    ffmpeg \
    > /dev/null 2>&1

# Build tools needed to compile rpi-rgb-led-matrix
if [ "$IS_PI" = true ]; then
    apt-get install -y -qq \
        build-essential \
        gcc \
        g++ \
        make \
        cython3 \
        > /dev/null 2>&1
    log_info "System packages installed (including build tools for rpi-rgb-led-matrix)"
else
    log_info "System packages installed (build tools skipped -- not on Pi)"
fi

# ---------------------------------------------------------------------------
# Step 2: Create virtual environment
# ---------------------------------------------------------------------------
STEP=$((STEP + 1))
log_info "Step $STEP/$TOTAL_STEPS: Setting up Python virtual environment..."
VENV_PATH="$PROJECT_ROOT/venv"
if [ ! -d "$VENV_PATH" ]; then
    python3 -m venv "$VENV_PATH"
    log_info "Virtual environment created at $VENV_PATH"
else
    log_info "Virtual environment already exists"
fi

# ---------------------------------------------------------------------------
# Step 3: Install Python dependencies
# ---------------------------------------------------------------------------
STEP=$((STEP + 1))
log_info "Step $STEP/$TOTAL_STEPS: Installing Python dependencies..."
"$VENV_PATH/bin/pip" install --quiet --upgrade pip
"$VENV_PATH/bin/pip" install --quiet -r "$PROJECT_ROOT/requirements.txt"
# Install yt-dlp from GitHub source (latest fixes, ahead of PyPI)
"$VENV_PATH/bin/pip" install --quiet --upgrade "yt-dlp @ https://github.com/yt-dlp/yt-dlp/archive/master.tar.gz" 2>/dev/null || true
log_info "Python dependencies installed"

# ---------------------------------------------------------------------------
# Step 4: Build rpi-rgb-led-matrix C library + Python bindings (Pi only)
# ---------------------------------------------------------------------------
if [ "$IS_PI" = true ]; then
    STEP=$((STEP + 1))
    log_info "Step $STEP/$TOTAL_STEPS: Building rpi-rgb-led-matrix library..."

    RGB_MATRIX_DIR="$ACTUAL_HOME/rpi-rgb-led-matrix"

    if [ -d "$RGB_MATRIX_DIR" ]; then
        log_info "rpi-rgb-led-matrix already cloned at $RGB_MATRIX_DIR -- pulling latest..."
        cd "$RGB_MATRIX_DIR"
        git pull --quiet 2>/dev/null || true
    else
        log_info "Cloning rpi-rgb-led-matrix from GitHub..."
        git clone https://github.com/hzeller/rpi-rgb-led-matrix.git "$RGB_MATRIX_DIR"
        cd "$RGB_MATRIX_DIR"
    fi

    # Build the C library
    log_info "Compiling C library (this may take a few minutes on a Pi)..."
    make -C "$RGB_MATRIX_DIR" clean 2>/dev/null || true
    if ! make -C "$RGB_MATRIX_DIR" -j"$(nproc)"; then
        log_error "C library compilation failed! See errors above."
        log_error "Common fixes:"
        log_error "  - Install build tools: sudo apt-get install build-essential gcc g++ make"
        log_error "  - Check disk space: df -h"
        log_error "  - Try manually: cd $RGB_MATRIX_DIR && make"
        # Don't exit -- continue with rest of install, matrix just won't have hardware support
    else
        log_info "C library compiled successfully"

        # Build and install the Python bindings into our venv
        log_info "Building Python bindings (this may also take a few minutes)..."
        VENV_PYTHON="$VENV_PATH/bin/python3"

        # Install Cython into the venv (needed for building the .pyx files)
        "$VENV_PATH/bin/pip" install --quiet cython

        cd "$RGB_MATRIX_DIR/bindings/python"

        # The Makefile in the bindings directory builds and installs into the
        # Python pointed to by PYTHON variable.
        # Show output so build errors are visible.
        make clean 2>/dev/null || true
        if ! make build-python PYTHON="$VENV_PYTHON"; then
            log_error "Python bindings build failed! See errors above."
            log_error "Manual fix: cd $RGB_MATRIX_DIR/bindings/python && make build-python PYTHON=$VENV_PYTHON"
        elif ! make install-python PYTHON="$VENV_PYTHON"; then
            log_error "Python bindings install failed! See errors above."
            log_error "Manual fix: cd $RGB_MATRIX_DIR/bindings/python && make install-python PYTHON=$VENV_PYTHON"
        else
            # Verify the bindings actually import correctly
            if "$VENV_PYTHON" -c "from rgbmatrix import RGBMatrix; print('rgbmatrix OK')" 2>/dev/null; then
                log_info "rpi-rgb-led-matrix Python bindings installed successfully"
            else
                log_error "Python bindings installed but import test failed!"
                log_error "Try manually: $VENV_PYTHON -c 'from rgbmatrix import RGBMatrix'"
            fi
        fi
    fi

    # Fix ownership (we cloned as root due to sudo)
    chown -R "$ACTUAL_USER:$ACTUAL_USER" "$RGB_MATRIX_DIR"

    cd "$PROJECT_ROOT"
fi

# ---------------------------------------------------------------------------
# Step 5: Disable onboard audio -- GPIO conflict fix (Pi only)
# ---------------------------------------------------------------------------
if [ "$IS_PI" = true ]; then
    STEP=$((STEP + 1))
    log_info "Step $STEP/$TOTAL_STEPS: Checking for GPIO conflicts..."

    AUDIO_FIXED=false

    # Fix /boot/config.txt or /boot/firmware/config.txt (Bookworm uses firmware/)
    for BOOT_CONFIG in /boot/firmware/config.txt /boot/config.txt; do
        if [ -f "$BOOT_CONFIG" ]; then
            if grep -q "^dtparam=audio=on" "$BOOT_CONFIG" 2>/dev/null; then
                sed -i 's/^dtparam=audio=on/dtparam=audio=off/' "$BOOT_CONFIG"
                log_info "Disabled onboard audio in $BOOT_CONFIG (was conflicting with GPIO 18)"
                AUDIO_FIXED=true
            elif grep -q "^dtparam=audio=off" "$BOOT_CONFIG" 2>/dev/null; then
                log_info "Onboard audio already disabled in $BOOT_CONFIG"
            else
                # No audio line found -- add one to be safe
                echo "dtparam=audio=off" >> "$BOOT_CONFIG"
                log_info "Added dtparam=audio=off to $BOOT_CONFIG"
                AUDIO_FIXED=true
            fi
            break
        fi
    done

    # Blacklist the snd_bcm2835 kernel module
    BLACKLIST_FILE="/etc/modprobe.d/blacklist-rgb-matrix.conf"
    if [ ! -f "$BLACKLIST_FILE" ] || ! grep -q "snd_bcm2835" "$BLACKLIST_FILE" 2>/dev/null; then
        echo "blacklist snd_bcm2835" > "$BLACKLIST_FILE"
        log_info "Blacklisted snd_bcm2835 kernel module (prevents audio/GPIO conflict)"
        AUDIO_FIXED=true
    else
        log_info "snd_bcm2835 already blacklisted"
    fi

    if [ "$AUDIO_FIXED" = true ]; then
        log_warn "Audio config changed -- a reboot is required for changes to take effect"
    fi
fi

# ---------------------------------------------------------------------------
# Step N+1: Create logs directory
# ---------------------------------------------------------------------------
STEP=$((STEP + 1))
log_info "Step $STEP/$TOTAL_STEPS: Creating logs directory..."
mkdir -p "$PROJECT_ROOT/logs"
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$PROJECT_ROOT/logs"
log_info "Logs directory ready"

# ---------------------------------------------------------------------------
# Step N+2: Install systemd services
# ---------------------------------------------------------------------------
STEP=$((STEP + 1))
log_info "Step $STEP/$TOTAL_STEPS: Installing systemd services..."

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

# ---------------------------------------------------------------------------
# Step N+3: Configure WiFi (optional prompt)
# ---------------------------------------------------------------------------
STEP=$((STEP + 1))
log_info "Step $STEP/$TOTAL_STEPS: WiFi configuration..."
WIFI_CONFIG="$PROJECT_ROOT/config/wifi.json"

if grep -q "YOUR_WIFI_SSID" "$WIFI_CONFIG" 2>/dev/null; then
    echo ""
    log_warn "WiFi is not configured yet."
    echo "  Edit $WIFI_CONFIG to add your WiFi network(s)."
    echo "  For open/public WiFi, leave password as empty string."
    echo ""
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "=============================================="
log_info "Installation complete!"
echo "=============================================="
echo ""

if [ "$IS_PI" = true ]; then
    echo "  Hardware setup:"
    echo "    [+] rpi-rgb-led-matrix C library compiled"
    echo "    [+] Python bindings installed into venv"
    echo "    [+] Onboard audio disabled (GPIO 18 conflict)"
    echo "    [+] snd_bcm2835 kernel module blacklisted"
    echo ""
fi

echo "  Next steps:"
echo "    1. Edit config/wifi.json with your WiFi network details"
echo "    2. Edit config/config.json to enable/disable features"
if [ "$IS_PI" = true ]; then
    echo "    3. Reboot to apply audio/GPIO changes: sudo reboot"
else
    echo "    3. Reboot to start: sudo reboot"
fi
echo ""
echo "  Or start manually (after reboot if audio was changed):"
echo "    sudo systemctl start led-matrix.service"
echo "    sudo systemctl start led-matrix-web.service"
echo "    sudo systemctl start led-matrix-updater.timer"
echo ""
echo "  View logs:"
echo "    journalctl -u led-matrix.service -f"
echo "    journalctl -u led-matrix-web.service -f"
echo ""
if [ "$IS_PI" = true ]; then
    echo "  Hardware diagnostics:"
    echo "    sudo bash scripts/test_hardware.sh"
    echo ""
    echo "  Reconfigure matrix settings:"
    echo "    sudo bash scripts/configure_matrix.sh"
    echo ""
fi
