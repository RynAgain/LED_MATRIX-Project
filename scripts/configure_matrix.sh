#!/bin/bash
# LED Matrix Project - Hardware Configuration Script
# Run: sudo bash scripts/configure_matrix.sh
#
# Walks you through setting the correct hardware parameters for your
# specific LED matrix panel. Writes results to config/config.json so
# the display service picks them up on next start.
#
# Reference: https://github.com/hzeller/rpi-rgb-led-matrix

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_PATH="$PROJECT_ROOT/config/config.json"

info()  { echo -e "${CYAN}[i]${NC} $1"; }
ok()    { echo -e "${GREEN}[+]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }

# ---------------------------------------------------------------------------
# Helper: read a value from the user with a default
# Usage: ask "prompt" "default"
# ---------------------------------------------------------------------------
ask() {
    local prompt="$1"
    local default="$2"
    local reply
    read -rp "$(echo -e "${BOLD}$prompt${NC} [${GREEN}$default${NC}]: ")" reply
    echo "${reply:-$default}"
}

echo ""
echo "========================================"
echo "  LED Matrix Hardware Configuration"
echo "========================================"
echo ""
info "This script helps you set the correct hardware parameters"
info "for your specific RGB LED matrix panel(s)."
echo ""
info "If you're unsure about a value, just press Enter to keep the default."
info "You can always re-run this script later."
echo ""

# ===== Panel dimensions =====
echo -e "${CYAN}--- Panel Dimensions ---${NC}"
echo ""
info "Common panel sizes: 16x32, 32x32, 32x64, 64x64"
info "This is the size of a SINGLE panel (before chaining)."
echo ""

ROWS=$(ask "Panel rows (height of one panel)" "64")
COLS=$(ask "Panel columns (width of one panel)" "64")

echo ""

# ===== Chaining / Parallel =====
echo -e "${CYAN}--- Chaining & Parallel ---${NC}"
echo ""
info "chain_length = number of panels daisy-chained in series"
info "parallel     = number of parallel chains (1-3, depends on Pi model)"
info "  - Pi 3/4/5: up to 3 parallel chains"
info "  - Pi Zero:   1 parallel chain"
info ""
info "Total LEDs = rows x cols x chain_length x parallel"
echo ""

CHAIN_LENGTH=$(ask "Chain length (panels in series)" "1")
PARALLEL=$(ask "Parallel chains" "1")

TOTAL_W=$(( COLS * CHAIN_LENGTH ))
TOTAL_H=$(( ROWS * PARALLEL ))
echo ""
ok "Total display resolution: ${TOTAL_W}x${TOTAL_H} pixels"
echo ""

# ===== Hardware mapping =====
echo -e "${CYAN}--- Hardware Mapping (GPIO wiring) ---${NC}"
echo ""
info "This depends on how the matrix is wired to the Pi's GPIO header."
info "Options:"
echo "  1) regular        - Standard wiring (Adafruit HAT, most common)"
echo "  2) adafruit-hat   - Adafruit RGB Matrix HAT/Bonnet"
echo "  3) adafruit-hat-pwm - Adafruit HAT with hardware PWM (better quality)"
echo "  4) regular-pi1    - Original Pi 1 revision 1 wiring"
echo "  5) classic        - Classic pinout from early rpi-rgb-led-matrix"
echo "  6) classic-pi1    - Classic pinout for Pi 1 rev 1"
echo "  7) compute-module - Raspberry Pi Compute Module"
echo ""

HW_CHOICE=$(ask "Hardware mapping (1-7 or type name)" "1")
case "$HW_CHOICE" in
    1|regular)           HW_MAPPING="regular" ;;
    2|adafruit-hat)      HW_MAPPING="adafruit-hat" ;;
    3|adafruit-hat-pwm)  HW_MAPPING="adafruit-hat-pwm" ;;
    4|regular-pi1)       HW_MAPPING="regular-pi1" ;;
    5|classic)           HW_MAPPING="classic" ;;
    6|classic-pi1)       HW_MAPPING="classic-pi1" ;;
    7|compute-module)    HW_MAPPING="compute-module" ;;
    *)                   HW_MAPPING="$HW_CHOICE" ;;
esac

ok "Hardware mapping: $HW_MAPPING"
echo ""

# ===== GPIO slowdown =====
echo -e "${CYAN}--- GPIO Slowdown ---${NC}"
echo ""
info "Slows down GPIO to prevent flicker on faster Pi models."
info "Recommended values:"
echo "  Pi Zero / Pi 1:  0 or 1"
echo "  Pi 2:            1 or 2"
echo "  Pi 3:            2 or 3"
echo "  Pi 4:            3 or 4"
echo "  Pi 5:            4 or 5"
echo ""

GPIO_SLOWDOWN=$(ask "GPIO slowdown" "4")
echo ""

# ===== Pixel mapper =====
echo -e "${CYAN}--- Pixel Mapper (panel arrangement) ---${NC}"
echo ""
info "If you have multiple panels, this controls how they're arranged."
info "Options:"
echo "  (empty)        - Single panel or simple left-to-right chain"
echo "  U-mapper       - Panels form a U-shape (serpentine / zig-zag)"
echo "  Rotate:90      - Rotate output 90 degrees"
echo "  Rotate:180     - Rotate output 180 degrees"
echo "  Rotate:270     - Rotate output 270 degrees"
echo "  Mirror:H       - Mirror horizontally"
echo "  Mirror:V       - Mirror vertically"
echo ""
info "You can combine them with semicolons: U-mapper;Rotate:180"
echo ""

PIXEL_MAPPER=$(ask "Pixel mapper (leave empty for none)" "")
echo ""

# ===== Multiplexing =====
echo -e "${CYAN}--- Row Multiplexing ---${NC}"
echo ""
info "Most panels use direct multiplexing (0). Some cheap panels"
info "use stripe or checker multiplexing. Try 0 first."
info "Options:"
echo "  0 = Direct (default, most panels)"
echo "  1 = Stripe"
echo "  2 = Checker (both halves)"
echo "  3 = Spiral"
echo "  4 = Z-Stripe (uncommon)"
echo "  5 = ZnMirrorZStripe"
echo "  6 = coreman"
echo "  7 = Kaler2Scan"
echo "  8 = P10-128x4-Z"
echo "  9 = QiangLiQ8"
echo "  10 = InversedZStripe"
echo "  11 = P10Outdoor1R1G1B1"
echo "  12 = P10Outdoor1R1G1B2"
echo "  13 = P10Outdoor1R1G1B3"
echo "  14 = P10CoremanMapper"
echo "  15 = P8Outdoor1R1G1B"
echo "  16 = FlippedStripe"
echo "  17 = P10Outdoor32x16HalfScan"
echo ""

MUX=$(ask "Row multiplexing (0-17)" "0")
echo ""

# ===== Row address type =====
echo -e "${CYAN}--- Row Address Type ---${NC}"
echo ""
info "How rows are addressed on the panel's shift registers."
echo "  0 = Direct (default, most panels)"
echo "  1 = AB-addressed (some older panels)"
echo "  2 = Direct row select"
echo "  3 = ABC-addressed (some 1/8 or 1/16 scan)"
echo "  4 = ABC shift + DE direct"
echo ""

ROW_ADDR=$(ask "Row address type (0-4)" "0")
echo ""

# ===== Brightness =====
echo -e "${CYAN}--- Brightness ---${NC}"
echo ""
info "Display brightness (1-100%). Higher = brighter but more power draw."
echo ""

BRIGHTNESS=$(ask "Brightness (1-100)" "80")
echo ""

# ===== PWM settings =====
echo -e "${CYAN}--- PWM Settings ---${NC}"
echo ""
info "PWM bits control color depth. Higher = more colors but may flicker."
info "  Default: 11 (2048 levels per channel)"
info "  Range: 1-11"
echo ""

PWM_BITS=$(ask "PWM bits (1-11)" "11")

info "PWM LSB nanoseconds - lower = faster refresh but may cause issues."
info "  Default: 130"
echo ""

PWM_LSB_NS=$(ask "PWM LSB nanoseconds" "130")

info "PWM dither bits - adds temporal dithering for smoother gradients."
info "  Default: 0 (disabled). Try 1-2 if you see color banding."
echo ""

PWM_DITHER=$(ask "PWM dither bits (0-2)" "0")
echo ""

# ===== Scan mode =====
echo -e "${CYAN}--- Scan Mode ---${NC}"
echo ""
info "How the panel scans its rows."
echo "  0 = Progressive (default)"
echo "  1 = Interlaced"
echo ""

SCAN_MODE=$(ask "Scan mode (0 or 1)" "0")
echo ""

# ===== Disable hardware pulsing =====
echo -e "${CYAN}--- Hardware Pulsing ---${NC}"
echo ""
info "Hardware pulsing gives the best quality but requires running as root."
info "Disable only if you see permission errors and cannot run as root."
echo ""

DISABLE_HW_PULSE_INPUT=$(ask "Disable hardware pulsing? (y/n)" "n")
if [ "$DISABLE_HW_PULSE_INPUT" = "y" ] || [ "$DISABLE_HW_PULSE_INPUT" = "Y" ]; then
    DISABLE_HW_PULSE=True
else
    DISABLE_HW_PULSE=False
fi
echo ""

# ===== Show on-screen panel =====
echo -e "${CYAN}--- LED Panel Type Detection ---${NC}"
echo ""
info "Common panel types and their typical settings:"
echo ""
echo "  Panel           | rows | cols | mux | row_addr | scan"
echo "  ----------------+------+------+-----+----------+-----"
echo "  P2 64x64        |  64  |  64  |  0  |    0     |  0"
echo "  P2.5 64x64      |  64  |  64  |  0  |    0     |  0"
echo "  P3 32x32        |  32  |  32  |  0  |    0     |  0"
echo "  P3 64x32        |  32  |  64  |  0  |    0     |  0"
echo "  P4 32x32        |  32  |  32  |  0  |    0     |  0"
echo "  P5 32x16        |  16  |  32  |  0  |    0     |  0"
echo "  P10 32x16       |  16  |  32  |  1  |    0     |  0"
echo "  P10 outdoor     |  16  |  32  |  8  |    0     |  0"
echo ""

# ===== Summary =====
echo "========================================"
echo -e "  ${CYAN}Configuration Summary${NC}"
echo "========================================"
echo ""
echo "  Panel size:           ${ROWS}x${COLS}"
echo "  Chain length:         $CHAIN_LENGTH"
echo "  Parallel:             $PARALLEL"
echo "  Total resolution:     ${TOTAL_W}x${TOTAL_H}"
echo "  Hardware mapping:     $HW_MAPPING"
echo "  GPIO slowdown:        $GPIO_SLOWDOWN"
echo "  Pixel mapper:         ${PIXEL_MAPPER:-(none)}"
echo "  Multiplexing:         $MUX"
echo "  Row address type:     $ROW_ADDR"
echo "  Brightness:           $BRIGHTNESS%"
echo "  PWM bits:             $PWM_BITS"
echo "  PWM LSB ns:           $PWM_LSB_NS"
echo "  PWM dither bits:      $PWM_DITHER"
echo "  Scan mode:            $SCAN_MODE"
echo "  Disable HW pulsing:   $DISABLE_HW_PULSE"
echo ""

CONFIRM=$(ask "Save this configuration? (y/n)" "y")
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    warn "Configuration NOT saved. Re-run to try again."
    exit 0
fi

# ===== Write to config.json =====
info "Writing hardware config to $CONFIG_PATH ..."

# Use Python to safely merge into the existing config.json
python3 - "$CONFIG_PATH" <<PYEOF
import json, sys

config_path = sys.argv[1]

# Read existing config
try:
    with open(config_path, "r") as f:
        config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    config = {}

# Set hardware block
config["matrix_hardware"] = {
    "rows": int("$ROWS"),
    "cols": int("$COLS"),
    "chain_length": int("$CHAIN_LENGTH"),
    "parallel": int("$PARALLEL"),
    "hardware_mapping": "$HW_MAPPING",
    "gpio_slowdown": int("$GPIO_SLOWDOWN"),
    "pixel_mapper": "$PIXEL_MAPPER",
    "multiplexing": int("$MUX"),
    "row_address_type": int("$ROW_ADDR"),
    "brightness": int("$BRIGHTNESS"),
    "pwm_bits": int("$PWM_BITS"),
    "pwm_lsb_nanoseconds": int("$PWM_LSB_NS"),
    "pwm_dither_bits": int("$PWM_DITHER"),
    "scan_mode": int("$SCAN_MODE"),
    "disable_hardware_pulsing": $DISABLE_HW_PULSE,
    "drop_privileges": False
}

with open(config_path, "w") as f:
    json.dump(config, f, indent=2)

print("  Configuration saved successfully.")
PYEOF

echo ""
ok "Hardware configuration saved to config/config.json"
echo ""
echo "  To apply changes:"
echo "    sudo systemctl restart led-matrix.service"
echo ""
echo "  If the display looks wrong, re-run this script with different settings:"
echo "    sudo bash $PROJECT_ROOT/scripts/configure_matrix.sh"
echo ""
echo "  Common fixes for display issues:"
echo "    - Garbled image:     Try different multiplexing values (0-17)"
echo "    - Flickering:        Increase gpio_slowdown"
echo "    - Wrong orientation: Add Rotate:90/180/270 to pixel_mapper"
echo "    - Colors wrong:      Check hardware_mapping matches your HAT/bonnet"
echo "    - Dim display:       Increase brightness (up to 100)"
echo ""
