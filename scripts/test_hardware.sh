#!/bin/bash
# LED Matrix Project - Hardware Diagnostics for Sengreat / Generic HATs
# Run: sudo bash scripts/test_hardware.sh
#
# Tests GPIO access, audio conflicts, hardware mapping, and runs a
# quick pixel test so you can visually confirm the panel is working.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python3"
CONFIG_PATH="$PROJECT_ROOT/config/config.json"

pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "  ${CYAN}[INFO]${NC} $1"; }

# Must be root for GPIO tests
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[ERROR]${NC} Please run as root: sudo bash scripts/test_hardware.sh"
    exit 1
fi

echo ""
echo "========================================"
echo "  LED Matrix Hardware Diagnostics"
echo "  (Sengreat / Generic HAT focused)"
echo "========================================"
echo ""

# ----------------------------------------------------------------
# 1. Root & GPIO check
# ----------------------------------------------------------------
echo -e "${CYAN}1. Root & GPIO Access${NC}"

pass "Running as root (required for rpi-rgb-led-matrix)"

if [ -d /sys/class/gpio ]; then
    pass "GPIO sysfs interface available"
else
    warn "GPIO sysfs not found (might be fine on newer kernels using libgpiod)"
fi

# Check if /dev/mem or /dev/gpiomem is accessible
if [ -r /dev/mem ]; then
    pass "/dev/mem is readable (needed for hardware PWM)"
else
    fail "/dev/mem not readable -- hardware pulsing won't work"
    echo "       Try: sudo chmod a+rw /dev/mem  (or just run as root)"
fi

echo ""

# ----------------------------------------------------------------
# 2. Audio conflict check (critical for Sengreat HAT)
# ----------------------------------------------------------------
echo -e "${CYAN}2. Onboard Audio Conflict${NC}"
echo ""
info "The Pi's onboard audio uses GPIO 18 (PWM0), which conflicts with"
info "the LED matrix. If audio is enabled, the display will flicker or"
info "show garbage. This is the #1 issue with Sengreat/generic HATs."
echo ""

AUDIO_ENABLED=false

# Check /boot/config.txt or /boot/firmware/config.txt
for BOOT_CONFIG in /boot/firmware/config.txt /boot/config.txt; do
    if [ -f "$BOOT_CONFIG" ]; then
        # Check if dtparam=audio=on is active (uncommented)
        if grep -q "^dtparam=audio=on" "$BOOT_CONFIG" 2>/dev/null; then
            AUDIO_ENABLED=true
            fail "Onboard audio is ENABLED in $BOOT_CONFIG"
            echo "       This conflicts with the LED matrix GPIO pins!"
            echo ""
            echo "       Fix: Edit $BOOT_CONFIG and change:"
            echo "         dtparam=audio=on"
            echo "       to:"
            echo "         dtparam=audio=off"
            echo "       Then reboot."
            echo ""
        elif grep -q "^#dtparam=audio=on" "$BOOT_CONFIG" 2>/dev/null || \
             grep -q "^dtparam=audio=off" "$BOOT_CONFIG" 2>/dev/null; then
            pass "Onboard audio is disabled in $BOOT_CONFIG"
        else
            warn "No audio setting found in $BOOT_CONFIG -- audio may still be active"
            echo "       Add 'dtparam=audio=off' to $BOOT_CONFIG and reboot."
        fi
        break
    fi
done

# Also check if snd_bcm2835 module is loaded
if lsmod 2>/dev/null | grep -q snd_bcm2835; then
    AUDIO_ENABLED=true
    fail "snd_bcm2835 kernel module is loaded (Pi onboard audio is active)"
    echo "       Blacklist it: echo 'blacklist snd_bcm2835' | sudo tee /etc/modprobe.d/blacklist-audio.conf"
    echo "       Then reboot."
else
    pass "snd_bcm2835 module is NOT loaded"
fi

echo ""

# ----------------------------------------------------------------
# 3. Check for I2S / SPI conflicts
# ----------------------------------------------------------------
echo -e "${CYAN}3. GPIO Pin Conflicts${NC}"

# Check if I2S is enabled (uses GPIO 18, 19, 20, 21 -- conflicts with matrix)
for BOOT_CONFIG in /boot/firmware/config.txt /boot/config.txt; do
    if [ -f "$BOOT_CONFIG" ]; then
        if grep -q "^dtoverlay=hifiberry" "$BOOT_CONFIG" 2>/dev/null || \
           grep -q "^dtoverlay=i2s" "$BOOT_CONFIG" 2>/dev/null; then
            fail "I2S audio overlay detected in $BOOT_CONFIG -- conflicts with matrix"
            echo "       Comment out the I2S/HiFiBerry overlay and reboot."
        else
            pass "No I2S overlays detected"
        fi
        break
    fi
done

echo ""

# ----------------------------------------------------------------
# 4. Current hardware config
# ----------------------------------------------------------------
echo -e "${CYAN}4. Current Hardware Configuration${NC}"

if [ -f "$CONFIG_PATH" ]; then
    # Extract and display current hardware settings using Python
    "$VENV_PYTHON" - "$CONFIG_PATH" <<'PYEOF' 2>/dev/null || python3 - "$CONFIG_PATH" <<'PYEOF' 2>/dev/null
import json, sys

with open(sys.argv[1]) as f:
    config = json.load(f)

hw = config.get("matrix_hardware", {})
if not hw:
    print("  [WARN] No matrix_hardware section in config.json")
    print("         Run: sudo bash scripts/configure_matrix.sh")
    sys.exit(0)

print(f"  Rows:                  {hw.get('rows', '?')}")
print(f"  Cols:                  {hw.get('cols', '?')}")
print(f"  Chain length:          {hw.get('chain_length', '?')}")
print(f"  Parallel:              {hw.get('parallel', '?')}")
print(f"  Hardware mapping:      {hw.get('hardware_mapping', '?')}")
print(f"  GPIO slowdown:         {hw.get('gpio_slowdown', '?')}")
print(f"  Brightness:            {hw.get('brightness', '?')}%")
print(f"  Multiplexing:          {hw.get('multiplexing', '?')}")
print(f"  Row address type:      {hw.get('row_address_type', '?')}")
print(f"  PWM bits:              {hw.get('pwm_bits', '?')}")
print(f"  Disable HW pulsing:    {hw.get('disable_hardware_pulsing', '?')}")
print(f"  Drop privileges:       {hw.get('drop_privileges', '?')}")

mapping = hw.get("hardware_mapping", "regular")
if mapping == "regular":
    print("")
    print("  [i] hardware_mapping='regular' is the correct default for Sengreat HAT.")
    print("      If display is garbled, also try 'adafruit-hat'.")
elif mapping == "adafruit-hat":
    print("")
    print("  [i] hardware_mapping='adafruit-hat' -- some Sengreat clones use this.")
    print("      If display is garbled, try switching to 'regular'.")
PYEOF

else
    fail "config.json not found at $CONFIG_PATH"
fi

echo ""

# ----------------------------------------------------------------
# 5. Pi model detection
# ----------------------------------------------------------------
echo -e "${CYAN}5. Raspberry Pi Model${NC}"

if [ -f /proc/device-tree/model ]; then
    PI_MODEL=$(tr -d '\0' < /proc/device-tree/model)
    info "Detected: $PI_MODEL"

    # Recommend gpio_slowdown based on model
    if echo "$PI_MODEL" | grep -qi "Pi 5"; then
        info "Recommended gpio_slowdown: 4-5"
    elif echo "$PI_MODEL" | grep -qi "Pi 4"; then
        info "Recommended gpio_slowdown: 4"
    elif echo "$PI_MODEL" | grep -qi "Pi 3"; then
        info "Recommended gpio_slowdown: 2-3"
    elif echo "$PI_MODEL" | grep -qi "Pi 2"; then
        info "Recommended gpio_slowdown: 1-2"
    elif echo "$PI_MODEL" | grep -qi "Pi Zero\|Pi 1"; then
        info "Recommended gpio_slowdown: 0-1"
    fi
else
    warn "Could not detect Pi model"
fi

echo ""

# ----------------------------------------------------------------
# 6. Quick pixel test
# ----------------------------------------------------------------
echo -e "${CYAN}6. Quick Pixel Test${NC}"
echo ""
info "This will display solid red, green, blue, then white on the matrix"
info "for 2 seconds each. Watch the panel to verify it's working."
echo ""

read -p "Run pixel test now? [y/N] " RUN_TEST

if [[ "$RUN_TEST" =~ ^[Yy]$ ]]; then
    echo ""
    info "Running pixel test..."
    echo ""

    # Use venv python if available, else system
    PYTHON="$VENV_PYTHON"
    if [ ! -f "$PYTHON" ]; then
        PYTHON="python3"
    fi

    "$PYTHON" - "$CONFIG_PATH" <<'PYEOF'
import json
import sys
import time
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[1])))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

config_path = sys.argv[1]

# Load hardware config
try:
    with open(config_path) as f:
        config = json.load(f)
    hw = config.get("matrix_hardware", {})
except Exception:
    hw = {}

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    options = RGBMatrixOptions()
    options.rows = hw.get("rows", 64)
    options.cols = hw.get("cols", 64)
    options.chain_length = hw.get("chain_length", 1)
    options.parallel = hw.get("parallel", 1)
    options.hardware_mapping = hw.get("hardware_mapping", "regular")
    options.gpio_slowdown = hw.get("gpio_slowdown", 4)
    options.brightness = hw.get("brightness", 80)
    options.drop_privileges = hw.get("drop_privileges", False)
    options.pwm_bits = hw.get("pwm_bits", 11)
    options.pwm_lsb_nanoseconds = hw.get("pwm_lsb_nanoseconds", 130)
    options.disable_hardware_pulsing = hw.get("disable_hardware_pulsing", False)

    matrix = RGBMatrix(options=options)
    canvas = matrix.CreateFrameCanvas()

    w = options.cols * options.chain_length
    h = options.rows * options.parallel

    colors = [
        ("RED",   (255, 0, 0)),
        ("GREEN", (0, 255, 0)),
        ("BLUE",  (0, 0, 255)),
        ("WHITE", (255, 255, 255)),
    ]

    for name, (r, g, b) in colors:
        print(f"  Showing {name}...")
        for y in range(h):
            for x in range(w):
                canvas.SetPixel(x, y, r, g, b)
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(2)

    # Clear
    print("  Clearing display...")
    canvas.Clear()
    matrix.SwapOnVSync(canvas)

    print("")
    print("  [PASS] Pixel test complete!")
    print("  If you saw red, green, blue, then white -- the HAT is working.")
    print("")
    print("  If the display was:")
    print("    - Completely blank:    Check power supply (5V 4A+ recommended)")
    print("    - Flickering:          Increase gpio_slowdown or disable onboard audio")
    print("    - Wrong colors:        Try hardware_mapping='adafruit-hat'")
    print("    - Garbled/shifted:     Try different multiplexing values (0-17)")
    print("    - Only half lit:       Check ribbon cable and chain_length/parallel")
    print("    - Dim:                 Check brightness setting and power supply amps")

except ImportError:
    print("  [FAIL] rgbmatrix library not installed!")
    print("         This test only works on a Raspberry Pi with rpi-rgb-led-matrix.")
    print("         Install: cd ~/rpi-rgb-led-matrix && make build-python PYTHON=$(which python3)")
    sys.exit(1)
except Exception as e:
    print(f"  [FAIL] Matrix initialization failed: {e}")
    print("")
    print("  Common causes:")
    print("    - Not running as root (sudo)")
    print("    - Wrong hardware_mapping for your HAT")
    print("    - GPIO pins in use by another process")
    print("    - Kernel module conflict (audio, SPI, I2C)")
    sys.exit(1)
PYEOF

else
    info "Skipped pixel test"
fi

echo ""

# ----------------------------------------------------------------
# 7. Sengreat-specific tips
# ----------------------------------------------------------------
echo "========================================"
echo -e "${CYAN}  Sengreat HAT - Known Issues & Tips${NC}"
echo "========================================"
echo ""
echo "  1. AUDIO CONFLICT (most common issue)"
echo "     The Pi's onboard audio uses GPIO 18 which the matrix needs."
echo "     Fix: dtparam=audio=off in /boot/config.txt, then reboot."
echo ""
echo "  2. HARDWARE MAPPING"
echo "     Sengreat HATs typically use 'regular' mapping."
echo "     If that doesn't work, try 'adafruit-hat'."
echo "     Run: sudo bash scripts/configure_matrix.sh"
echo ""
echo "  3. POWER SUPPLY"
echo "     A 64x64 panel at full white draws ~4A at 5V."
echo "     Use a dedicated 5V 4A+ power supply to the HAT's screw terminals."
echo "     Do NOT try to power the panel from the Pi's USB port."
echo ""
echo "  4. RIBBON CABLE"
echo "     The flat ribbon cable from HAT to panel is directional."
echo "     The arrow/dot on the cable should match the arrow on the panel's"
echo "     INPUT connector (not OUTPUT)."
echo ""
echo "  5. FLICKERING / GHOSTING"
echo "     Increase gpio_slowdown (try 4 or 5 on Pi 4/5)."
echo "     Lower pwm_bits from 11 to 7-8 if flicker persists."
echo "     Set pwm_dither_bits=1 for smoother gradients."
echo ""
echo "  6. DROP_PRIVILEGES MUST BE FALSE"
echo "     The Sengreat HAT needs root GPIO access. Make sure"
echo "     drop_privileges is false in config/config.json."
echo ""
echo "  7. PI 5 COMPATIBILITY"
echo "     rpi-rgb-led-matrix does NOT yet support Pi 5 natively."
echo "     If using Pi 5, check https://github.com/hzeller/rpi-rgb-led-matrix"
echo "     for the latest compatibility status."
echo ""
echo "  Quick reconfigure:"
echo "    sudo bash scripts/configure_matrix.sh"
echo ""
echo "  Full troubleshoot:"
echo "    sudo bash scripts/troubleshoot.sh"
echo ""
