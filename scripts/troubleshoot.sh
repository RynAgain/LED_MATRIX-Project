#!/bin/bash
# LED Matrix Project - Troubleshooting Script
# Run: bash scripts/troubleshoot.sh
# Checks service status, logs, permissions, and common issues.

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "  ${CYAN}[INFO]${NC} $1"; }

echo ""
echo "========================================"
echo "  LED Matrix Troubleshooting Report"
echo "========================================"
echo ""

# --- 1. Check if services are installed ---
echo -e "${CYAN}1. Service Installation${NC}"

if [ -f /etc/systemd/system/led-matrix.service ]; then
    pass "led-matrix.service is installed"
else
    fail "led-matrix.service is NOT installed"
    echo "       Run: sudo bash scripts/install.sh"
fi

if [ -f /etc/systemd/system/led-matrix-web.service ]; then
    pass "led-matrix-web.service is installed"
else
    warn "led-matrix-web.service is NOT installed (optional)"
fi

echo ""

# --- 2. Check if services are enabled ---
echo -e "${CYAN}2. Service Enable Status${NC}"

if systemctl is-enabled led-matrix.service &>/dev/null; then
    pass "led-matrix.service is enabled (will start on boot)"
else
    fail "led-matrix.service is NOT enabled"
    echo "       Run: sudo systemctl enable led-matrix.service"
fi

if systemctl is-enabled led-matrix-web.service &>/dev/null; then
    pass "led-matrix-web.service is enabled"
else
    warn "led-matrix-web.service is NOT enabled"
    echo "       Run: sudo systemctl enable led-matrix-web.service"
fi

echo ""

# --- 3. Check if services are running ---
echo -e "${CYAN}3. Service Runtime Status${NC}"

DISPLAY_STATUS=$(systemctl is-active led-matrix.service 2>/dev/null)
if [ "$DISPLAY_STATUS" = "active" ]; then
    pass "led-matrix.service is running"
else
    fail "led-matrix.service is $DISPLAY_STATUS"
    echo "       Start it: sudo systemctl start led-matrix.service"
fi

WEB_STATUS=$(systemctl is-active led-matrix-web.service 2>/dev/null)
if [ "$WEB_STATUS" = "active" ]; then
    pass "led-matrix-web.service is running"
else
    warn "led-matrix-web.service is $WEB_STATUS"
fi

echo ""

# --- 4. Check service user ---
echo -e "${CYAN}4. Service Configuration${NC}"

if [ -f /etc/systemd/system/led-matrix.service ]; then
    SVC_USER=$(grep "^User=" /etc/systemd/system/led-matrix.service | cut -d= -f2)
    if [ "$SVC_USER" = "root" ]; then
        pass "Display service runs as root (required for GPIO)"
    else
        fail "Display service runs as '$SVC_USER' -- must be root for GPIO access"
        echo "       The rpi-rgb-led-matrix library requires root to access GPIO pins."
        echo "       Fix: Re-run sudo bash scripts/install.sh or edit the service file."
    fi

    if grep -q "ProtectHome=" /etc/systemd/system/led-matrix.service; then
        PROTECT=$(grep "ProtectHome=" /etc/systemd/system/led-matrix.service | cut -d= -f2)
        if [ "$PROTECT" = "no" ] || [ "$PROTECT" = "false" ]; then
            pass "ProtectHome is disabled"
        else
            fail "ProtectHome=$PROTECT blocks writes to /home"
            echo "       Remove or set ProtectHome=no in the service file."
        fi
    else
        pass "No ProtectHome restriction"
    fi
fi

echo ""

# --- 5. Check Python venv ---
echo -e "${CYAN}5. Python Virtual Environment${NC}"

VENV_PATH="$PROJECT_ROOT/venv"
if [ -d "$VENV_PATH" ]; then
    pass "Virtual environment exists at $VENV_PATH"
else
    fail "Virtual environment NOT found at $VENV_PATH"
    echo "       Run: sudo bash scripts/install.sh"
fi

if [ -f "$VENV_PATH/bin/python3" ]; then
    PYTHON_VER=$("$VENV_PATH/bin/python3" --version 2>&1)
    pass "Python: $PYTHON_VER"
else
    fail "Python3 not found in venv"
fi

echo ""

# --- 6. Check config ---
echo -e "${CYAN}6. Configuration${NC}"

CONFIG_PATH="$PROJECT_ROOT/config/config.json"
if [ -f "$CONFIG_PATH" ]; then
    pass "config.json exists"
    
    # Check for enabled features
    ENABLED_COUNT=$(python3 -c "
import json
with open('$CONFIG_PATH') as f:
    c = json.load(f)
print(sum(1 for s in c.get('sequence',[]) if s.get('enabled')))
" 2>/dev/null)
    
    if [ -n "$ENABLED_COUNT" ] && [ "$ENABLED_COUNT" -gt 0 ]; then
        pass "$ENABLED_COUNT feature(s) enabled"
    else
        fail "No features are enabled in config.json"
        echo "       The service will exit immediately if no features are enabled."
        echo "       Enable at least one feature in config/config.json"
    fi
else
    fail "config.json not found"
fi

echo ""

# --- 7. Check logs directory ---
echo -e "${CYAN}7. Logs Directory${NC}"

LOGS_DIR="$PROJECT_ROOT/logs"
if [ -d "$LOGS_DIR" ]; then
    pass "logs/ directory exists"
    
    if [ -f "$LOGS_DIR/display.log" ]; then
        LOG_SIZE=$(stat -c%s "$LOGS_DIR/display.log" 2>/dev/null || echo "0")
        info "display.log size: $LOG_SIZE bytes"
    else
        warn "No display.log yet (service may not have run)"
    fi
else
    fail "logs/ directory does not exist"
    echo "       Run: mkdir -p $LOGS_DIR"
fi

echo ""

# --- 8. Check permissions ---
echo -e "${CYAN}8. File Permissions${NC}"

if [ -w "$PROJECT_ROOT/logs" ] 2>/dev/null || [ "$(id -u)" = "0" ]; then
    pass "logs/ directory is writable"
else
    warn "logs/ directory may not be writable by current user"
fi

if [ -r "$PROJECT_ROOT/config/config.json" ]; then
    pass "config.json is readable"
else
    fail "config.json is NOT readable"
fi

echo ""

# --- 9. Recent journal logs ---
echo -e "${CYAN}9. Recent Service Logs (last 20 lines)${NC}"
echo ""

if command -v journalctl &>/dev/null; then
    journalctl -u led-matrix.service --no-pager -n 20 2>/dev/null || \
        warn "Could not read journal (try with sudo)"
else
    warn "journalctl not available"
fi

echo ""

# --- 10. Quick fix suggestions ---
echo "========================================"
echo -e "${CYAN}  Quick Fix Commands${NC}"
echo "========================================"
echo ""
echo "  Re-install services:"
echo "    sudo bash $PROJECT_ROOT/scripts/install.sh"
echo ""
echo "  Start display now:"
echo "    sudo systemctl start led-matrix.service"
echo ""
echo "  Watch live logs:"
echo "    journalctl -u led-matrix.service -f"
echo ""
echo "  Restart after config change:"
echo "    sudo systemctl restart led-matrix.service"
echo ""
echo "  Check display log file:"
echo "    tail -50 $PROJECT_ROOT/logs/display.log"
echo ""
