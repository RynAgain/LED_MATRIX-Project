#!/usr/bin/env bash
# fix_pi.sh -- Restore the LED Matrix Pi to a known-good state.
#
# Run this on the Pi when the display is stuck looping on a single feature
# due to a corrupted or misconfigured config/config.json.
#
# Usage:
#   bash ~/LED_MATRIX-Project/scripts/fix_pi.sh
#
# What it does:
#   1. Stops the led-matrix service
#   2. Backs up the current (bad) config
#   3. Writes a fresh, sane config with a good default feature set
#   4. Restarts the service

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$PROJECT_DIR/config/config.json"
BACKUP="$PROJECT_DIR/config/config.json.bak.$(date +%Y%m%d_%H%M%S)"

echo "=== LED Matrix Pi Fix Script ==="
echo "Project dir: $PROJECT_DIR"

# ── 1. Stop the service ──────────────────────────────────────────────────────
echo ""
echo "[1/4] Stopping led-matrix service..."
if sudo systemctl is-active --quiet led-matrix.service 2>/dev/null; then
    sudo systemctl stop led-matrix.service
    echo "      Service stopped."
else
    echo "      Service was not running."
fi

# ── 2. Back up the bad config ────────────────────────────────────────────────
echo ""
echo "[2/4] Backing up current config to: $BACKUP"
cp "$CONFIG" "$BACKUP" 2>/dev/null && echo "      Backup saved." || echo "      (No existing config to back up.)"

# ── 3. Write a fresh sane config ────────────────────────────────────────────
echo ""
echo "[3/4] Writing fresh config..."

cat > "$CONFIG" << 'JSONEOF'
{
  "github_branch": "main",
  "display_duration": 30,
  "log_level": "INFO",
  "matrix_hardware": {
    "rows": 64,
    "cols": 64,
    "chain_length": 1,
    "parallel": 1,
    "hardware_mapping": "regular",
    "gpio_slowdown": 4,
    "brightness": 80,
    "pwm_bits": 11,
    "pwm_lsb_nanoseconds": 130,
    "pwm_dither_bits": 0,
    "scan_mode": 0,
    "multiplexing": 0,
    "row_address_type": 0,
    "pixel_mapper": "",
    "disable_hardware_pulsing": false,
    "drop_privileges": false
  },
  "sequence": [
    {"name": "snake",           "type": "game",    "enabled": false},
    {"name": "pong",            "type": "game",    "enabled": false},
    {"name": "fire",            "type": "effect",  "enabled": true},
    {"name": "tic_tac_toe",     "type": "game",    "enabled": false},
    {"name": "breakout",        "type": "game",    "enabled": false},
    {"name": "billiards",       "type": "game",    "enabled": false},
    {"name": "time_display",    "type": "utility", "enabled": true},
    {"name": "bitcoin_price",   "type": "utility", "enabled": false},
    {"name": "youtube_stream",  "type": "video",   "enabled": false},
    {"name": "plasma",          "type": "effect",  "enabled": true},
    {"name": "matrix_rain",     "type": "effect",  "enabled": true},
    {"name": "starfield",       "type": "effect",  "enabled": true},
    {"name": "game_of_life",    "type": "effect",  "enabled": true},
    {"name": "rainbow_waves",   "type": "effect",  "enabled": true},
    {"name": "weather",         "type": "utility", "enabled": false},
    {"name": "text_scroller",   "type": "utility", "enabled": false},
    {"name": "stock_ticker",    "type": "utility", "enabled": false},
    {"name": "sp500_heatmap",   "type": "utility", "enabled": false},
    {"name": "binary_clock",    "type": "utility", "enabled": false},
    {"name": "countdown",       "type": "utility", "enabled": false},
    {"name": "lava_lamp",       "type": "effect",  "enabled": true},
    {"name": "living_world",    "type": "effect",  "enabled": false},
    {"name": "qr_code",         "type": "utility", "enabled": false},
    {"name": "slideshow",       "type": "utility", "enabled": false},
    {"name": "galaga",          "type": "game",    "enabled": false},
    {"name": "space_invaders",  "type": "game",    "enabled": false},
    {"name": "logo_wholefoods", "type": "utility", "enabled": false},
    {"name": "github_stats",    "type": "utility", "enabled": false},
    {"name": "tanks",           "type": "game",    "enabled": false},
    {"name": "wireframe",       "type": "effect",  "enabled": true},
    {"name": "maze_3d",         "type": "effect",  "enabled": false},
    {"name": "terrain_ball",    "type": "effect",  "enabled": true},
    {"name": "system_stats",    "type": "utility", "enabled": true},
    {"name": "base6_clock",     "type": "utility", "enabled": false},
    {"name": "tetris",          "type": "game",    "enabled": false},
    {"name": "hail_mary_clock", "type": "utility", "enabled": false}
  ]
}
JSONEOF

echo "      Config written."
echo "      Enabled: fire, time_display, plasma, matrix_rain, starfield,"
echo "               game_of_life, rainbow_waves, lava_lamp, wireframe,"
echo "               terrain_ball, system_stats"

# Verify it's valid JSON
python3 -c "import json; json.load(open('$CONFIG')); print('      JSON validation: OK')"

# ── 4. Restart the service ───────────────────────────────────────────────────
echo ""
echo "[4/4] Starting led-matrix service..."
sudo systemctl start led-matrix.service
sleep 2
if sudo systemctl is-active --quiet led-matrix.service; then
    echo "      Service is running. ✓"
    echo ""
    echo "=== Done! Matrix should now be cycling through features. ==="
else
    echo "      WARNING: Service failed to start. Check logs:"
    sudo journalctl -u led-matrix.service -n 20 --no-pager
fi

echo ""
echo "Bad config backed up to: $BACKUP"
