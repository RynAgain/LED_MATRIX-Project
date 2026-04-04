#!/bin/bash
# LED Matrix - YouTube Download Diagnostic
# Run on the Pi: bash scripts/test_youtube.sh
# Tests yt-dlp, ffmpeg, and video download capabilities.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python3"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "  ${CYAN}[INFO]${NC} $1"; }

echo ""
echo "========================================"
echo "  YouTube Download Diagnostic"
echo "========================================"
echo ""

# Use venv python if available
if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
    warn "No venv found, using system Python"
fi

# 1. Check Python
echo -e "${CYAN}1. Python${NC}"
PY_VER=$($VENV_PYTHON --version 2>&1)
if [ $? -eq 0 ]; then
    pass "$PY_VER"
else
    fail "Python not found"
    exit 1
fi
echo ""

# 2. Check yt-dlp
echo -e "${CYAN}2. yt-dlp${NC}"
YT_VER=$($VENV_PYTHON -c "import yt_dlp; print(yt_dlp.version.__version__)" 2>&1)
if [ $? -eq 0 ]; then
    pass "yt-dlp version: $YT_VER"
else
    fail "yt-dlp not installed: $YT_VER"
    echo "       Fix: $VENV_PYTHON -m pip install yt-dlp"
fi
echo ""

# 3. Check OpenCV
echo -e "${CYAN}3. OpenCV${NC}"
CV_VER=$($VENV_PYTHON -c "import cv2; print(cv2.__version__)" 2>&1)
if [ $? -eq 0 ]; then
    pass "OpenCV version: $CV_VER"
else
    fail "OpenCV not installed: $CV_VER"
    echo "       Fix: $VENV_PYTHON -m pip install opencv-python-headless"
fi
echo ""

# 4. Check ffmpeg
echo -e "${CYAN}4. ffmpeg (needed for format merging)${NC}"
FFMPEG_VER=$(ffmpeg -version 2>&1 | head -1)
if command -v ffmpeg &>/dev/null; then
    pass "ffmpeg: $FFMPEG_VER"
else
    fail "ffmpeg NOT installed"
    echo "       Fix: sudo apt-get install -y ffmpeg"
    echo "       This is needed when yt-dlp has to merge separate audio/video streams"
fi
echo ""

# 5. Check internet
echo -e "${CYAN}5. Internet connectivity${NC}"
if ping -c 1 -W 3 youtube.com &>/dev/null; then
    pass "youtube.com reachable"
else
    fail "Cannot reach youtube.com"
    echo "       Check WiFi/network connection"
fi
echo ""

# 6. Test URL extraction
echo -e "${CYAN}6. URL Extraction Test${NC}"
TEST_URL="https://www.youtube.com/watch?v=Gx5--eK2k6Y"
info "Testing with: $TEST_URL"
echo ""

$VENV_PYTHON -c "
import yt_dlp
import sys

url = '$TEST_URL'
print('  Attempting URL extraction...')

# First try: simple format
ydl_opts = {
    'format': 'worst',
    'quiet': False,
    'no_warnings': False,
    'socket_timeout': 15,
}

try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        print(f'  Title: {info.get(\"title\", \"?\")!r}')
        print(f'  Duration: {info.get(\"duration\", \"?\")}s')
        print(f'  Format: {info.get(\"format\", \"?\")}')
        print(f'  Height: {info.get(\"height\", \"?\")}')
        print(f'  URL present: {bool(info.get(\"url\"))}')
        print(f'  Requested formats: {len(info.get(\"requested_formats\", []))}')

        # List available formats
        formats = info.get('formats', [])
        print(f'  Available formats: {len(formats)}')
        for f in formats[:5]:
            h = f.get('height', '?')
            ext = f.get('ext', '?')
            vcodec = f.get('vcodec', 'none')
            acodec = f.get('acodec', 'none')
            fs = f.get('filesize', 0) or 0
            print(f'    - {ext} {h}p v={vcodec} a={acodec} size={fs/1024/1024:.1f}MB')

except Exception as e:
    print(f'  EXTRACTION FAILED: {e}')
    sys.exit(1)
" 2>&1

if [ $? -eq 0 ]; then
    echo ""
    pass "URL extraction works"
else
    echo ""
    fail "URL extraction failed"
fi
echo ""

# 7. Test actual download
echo -e "${CYAN}7. Download Test${NC}"
TEST_FILE="/tmp/yt_test_download.mp4"
rm -f "$TEST_FILE" 2>/dev/null

info "Downloading a short video to $TEST_FILE..."
echo ""

$VENV_PYTHON -c "
import yt_dlp
import os

url = '$TEST_URL'
output = '$TEST_FILE'

# Try different format strategies
strategies = [
    'worst[height<=240][ext=mp4]',
    'worst[ext=mp4]',
    'worst',
    'best[height<=480]',
    'best',
]

for i, fmt in enumerate(strategies):
    print(f'  Strategy {i+1}: format={fmt}')
    ydl_opts = {
        'format': fmt,
        'outtmpl': output,
        'quiet': False,
        'no_warnings': False,
        'socket_timeout': 30,
        'retries': 2,
        'merge_output_format': 'mp4',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Check if file exists (might have different extension)
        if os.path.exists(output):
            size = os.path.getsize(output)
            print(f'  SUCCESS: {output} ({size} bytes)')
            break
        else:
            # Check for other extensions
            base = os.path.splitext(output)[0]
            for ext in ['.mp4', '.webm', '.mkv', '.mp4.part']:
                candidate = base + ext
                if os.path.exists(candidate):
                    size = os.path.getsize(candidate)
                    print(f'  SUCCESS (alt ext): {candidate} ({size} bytes)')
                    break
            else:
                print(f'  File not found at expected path')
                import glob
                matches = glob.glob(base + '*')
                if matches:
                    print(f'  Found: {matches}')
                continue

    except Exception as e:
        print(f'  Strategy {i+1} failed: {e}')
        continue
" 2>&1

echo ""
if [ -f "$TEST_FILE" ]; then
    SIZE=$(stat -c%s "$TEST_FILE" 2>/dev/null || stat -f%z "$TEST_FILE" 2>/dev/null)
    pass "Download successful: $SIZE bytes"
    rm -f "$TEST_FILE"
else
    # Check for alternate extension
    if ls /tmp/yt_test_download.* &>/dev/null 2>&1; then
        warn "Downloaded with different extension:"
        ls -la /tmp/yt_test_download.*
        rm -f /tmp/yt_test_download.*
    else
        fail "Download failed -- no file created"
    fi
fi
echo ""

# 8. Check cache directory
echo -e "${CYAN}8. Cache Directory${NC}"
CACHE_DIR="$PROJECT_ROOT/downloaded_videos"
if [ -d "$CACHE_DIR" ]; then
    COUNT=$(find "$CACHE_DIR" -name "*.mp4" -type f | wc -l)
    pass "Cache dir exists: $CACHE_DIR"
    info "$COUNT cached .mp4 files"
    if [ "$COUNT" -gt 0 ]; then
        ls -lh "$CACHE_DIR"/*.mp4 2>/dev/null
    fi
else
    warn "Cache directory does not exist"
fi
echo ""

# 9. Check display.log for errors
echo -e "${CYAN}9. Recent YouTube Errors in Log${NC}"
LOG_FILE="$PROJECT_ROOT/logs/display.log"
if [ -f "$LOG_FILE" ]; then
    ERRORS=$(grep -i -E "youtube|download|yt.dlp|cache|video" "$LOG_FILE" | tail -20)
    if [ -n "$ERRORS" ]; then
        echo "$ERRORS"
    else
        info "No YouTube-related entries in log"
    fi
else
    warn "No display.log found"
fi
echo ""
