# LED Matrix Project

A self-managing Raspberry Pi display system for a 64x64 RGB LED matrix. Cycles through 30+ display features -- games, visualizations, info displays, and video playback. Auto-updates from GitHub, connects to WiFi, and runs unattended from boot with a web control panel.

---

## Features

### Games
| Feature | Description |
|---------|-------------|
| Tic Tac Toe | AI vs AI on a 3x3 grid |
| Snake | Autonomous AI pathfinding |
| Pong | AI vs AI with increasing difficulty |
| Billiards | Physics simulation with AI player |
| Galaga | Classic arcade-style space shooter |
| Space Invaders | Retro alien invasion game |
| Tanks | Tank battle simulation |

### Visual Effects
| Feature | Description |
|---------|-------------|
| Fire | Realistic fire simulation |
| Plasma | Color plasma waves |
| Matrix Rain | Falling green characters |
| Starfield | 3D starfield flythrough |
| Game of Life | Conway's cellular automata |
| Rainbow Waves | Flowing rainbow patterns |
| Lava Lamp | Fluid lava lamp simulation |
| Living World | Procedural village sim with day/night, weather, villagers |
| Wireframe | Rotating 3D wireframe objects |
| Maze 3D | First-person 3D maze |
| Terrain Ball | Ball rolling on procedural terrain |

### Info Displays
| Feature | Description |
|---------|-------------|
| Time Display | Digital + analog clock with rainbow colors |
| Bitcoin Price | Live BTC/USD from CoinDesk API |
| Weather | Current conditions and forecast |
| Stock Ticker | Scrolling stock prices |
| S&P 500 Heatmap | Color-coded sector performance |
| Binary Clock | Time in binary representation |
| Countdown | Timer with custom target date |
| Text Scroller | Scrolling custom messages |
| QR Code | Display QR codes for URLs |
| GitHub Stats | Repository statistics display |
| Slideshow | Cycle through custom images |
| Logo Display | Custom logo rendering |

### Video
| Feature | Description |
|---------|-------------|
| YouTube Stream | Pre-cached YouTube playlist playback at 15 FPS |

### System
| Feature | Description |
|---------|-------------|
| Boot Screen | Animated startup sequence (ring burst + loading bar) |
| Web Control Panel | Mobile-friendly dashboard for full remote control |
| Auto-Updater | Git-based updates every 30 minutes |
| Night Mode | Scheduled brightness + feature restrictions |

---

## Web Control Panel

A password-protected web interface accessible from any device on the same network at `http://<pi-ip>:5000`.

| Tab | Description |
|-----|-------------|
| Dashboard | Live status, current feature, uptime, restart/update controls |
| Features | Toggle features on/off, set per-feature duration |
| YouTube | Manage video playlist, trigger playback |
| Messages | Configure scrolling text messages |
| Stocks | Set stock symbols for ticker and heatmap |
| Timer | Configure countdown target |
| Draw | Pixel art editor (64x64) |
| 3D | Configure wireframe objects |
| World | Living World controls and event log |
| WiFi | Add/remove WiFi networks |
| **Logs** | **Live log viewer with filtering, color-coded errors, auto-refresh** |
| Settings | GitHub branch, log level, system configuration |

Default credentials: `admin` / `ledmatrix` (change via Settings or `config/web.json`)

---

## Quick Start (Raspberry Pi)

### 1. Clone and install

```bash
cd /home/pi
git clone https://github.com/RynAgain/LED_MATRIX-Project.git
cd LED_MATRIX-Project
sudo bash scripts/install.sh
```

The installer sets up:
- System packages (Python 3, pip, git, NetworkManager, ffmpeg)
- Python virtual environment + dependencies
- systemd services for display, web panel, and auto-updater
- Logs directory

### 2. Configure hardware

```bash
sudo bash scripts/configure_matrix.sh
```

Interactive wizard for your specific LED panel. Configures:
- Panel dimensions (16x32, 32x32, 64x64, etc.)
- GPIO wiring (`regular`, `adafruit-hat`, `adafruit-hat-pwm`, etc.)
- Chaining, parallel chains, multiplexing
- GPIO slowdown (Pi model dependent)
- Brightness, PWM, scan mode

Settings are saved to `config/config.json` under `matrix_hardware`.

### 3. Configure WiFi

Edit `config/wifi.json`:

```json
{
  "networks": [
    {"ssid": "YourWiFiName", "password": "your_password", "priority": 1, "hidden": false}
  ],
  "connection_timeout": 30,
  "retry_attempts": 3,
  "retry_delay": 10
}
```

### 4. Reboot

```bash
sudo reboot
```

On boot, the system will:
1. Show an animated boot screen on the matrix (~4 seconds)
2. Connect to WiFi
3. Pre-cache YouTube videos (if youtube_stream is enabled)
4. Begin cycling through enabled features
5. Start the web control panel on port 5000
6. Check for GitHub updates every 30 minutes

---

## Boot Sequence

```
Power on
  --> Linux boot (~15-20s)
  --> systemd starts led-matrix.service (2s delay)
  --> Boot screen animation (ring burst + "LED MATRIX" + loading bar)
  --> WiFi connectivity check
  --> YouTube video pre-caching (with loading ring, if enabled)
  --> Feature display loop begins
```

YouTube videos are downloaded once to `downloaded_videos/` and cached permanently. Subsequent boots play instantly from disk. No internet required for cached content.

---

## Architecture

```
LED_MATRIX-Project/
  config/                  # All configuration files
    config.json            # Feature sequence, hardware settings, display options
    web.json               # Web panel credentials and settings
    wifi.json              # WiFi network credentials
    youtube_urls.csv       # YouTube playlist
    schedule.json          # Night mode / scheduling
    stocks.json            # Stock ticker symbols
    messages.json          # Text scroller messages
    countdown.json         # Countdown target
    weather.json           # Weather API settings
    qr.json                # QR code content
    wireframe.json         # 3D wireframe settings
    github_stats.json      # GitHub stats configuration
    images/                # Custom images for slideshow
  scripts/                 # Operational scripts
    install.sh             # One-time Raspberry Pi setup
    update.sh              # Called by systemd timer for auto-updates
    configure_matrix.sh    # Interactive hardware configuration wizard
    troubleshoot.sh        # System diagnostic tool
    test_youtube.sh        # YouTube download diagnostic
  services/                # systemd unit files
    led-matrix.service     # Main display service (runs as root for GPIO)
    led-matrix-web.service # Web control panel
    led-matrix-updater.*   # Auto-update service + timer
  src/                     # Application code
    main.py                # Entry point: boot screen, config, feature loop
    config_validator.py    # JSON schema validation
    display/               # 30+ display feature modules
      boot_screen.py       # Boot animation + loading ring + pixel font
      _shared.py           # Shared stop signaling for features
      living_world/        # Procedural village simulation (multi-file)
    simulator/             # Pygame LED matrix emulator (dev only)
    wifi/                  # WiFi connection manager (nmcli)
    updater/               # Git-based auto-updater
    web/                   # Flask web control panel
      app.py               # Routes, auth, API endpoints
      templates/           # Jinja2 HTML templates (13 pages + base)
      static/              # CSS styles
  downloaded_videos/       # YouTube video cache (persists across reboots)
  rgbmatrix/               # RGB LED matrix Cython library stubs
  tests/                   # Test suite (526 tests, runs without Pi hardware)
  logs/                    # Runtime logs (display.log, updater.log, status.json)
```

---

## Hardware

### Requirements
- Raspberry Pi (3, 4, or 5 recommended)
- 64x64 RGB LED Matrix panel (HUB75 interface)
- GPIO HAT/Bonnet (Adafruit HAT recommended; generic HATs work with `regular` mapping)
- 5V power supply (6A+ for 64x64 panel + Pi)

### Hardware Mapping

| HAT Type | `hardware_mapping` value |
|----------|-------------------------|
| Generic HUB75 / Sengreat | `regular` |
| Adafruit RGB Matrix HAT | `adafruit-hat` |
| Adafruit HAT with HW PWM | `adafruit-hat-pwm` |
| Raspberry Pi Compute Module | `compute-module` |

### Cython Driver Improvements

The vendored `rgbmatrix/` Cython bindings include an optimized `SetImage()` pipeline in `core.pyx` with three rendering tiers:

1. **Fast path** -- Direct Pillow `unsafe_ptrs` access via `SetPixelsPillow()`. Zero-copy pointer access to the image's raw 32-bit pixel buffer with `@boundscheck(False)`, `@wraparound(False)`, and `nogil` C loop. This is the fastest possible Python-to-C pixel transfer.

2. **Medium path** -- `image.tobytes()` with a `nogil` typed C loop. Releases the Python GIL during the pixel-setting loop, allowing other threads (command watcher, background downloads) to run concurrently.

3. **Slow fallback** -- Pure Python per-pixel access with bounds checking. Used only when the above paths fail (e.g., incompatible Pillow version).

The `graphics.pyx` module provides `DrawText()` with background color and kerning support, `VerticalDrawText()`, plus `DrawCircle()` and `DrawLine()` primitives.

### GPIO Slowdown by Pi Model

| Pi Model | Recommended `gpio_slowdown` |
|----------|-----------------------------|
| Pi Zero / Pi 1 | 0-1 |
| Pi 2 | 1-2 |
| Pi 3 | 2-3 |
| Pi 4 | 3-4 |
| Pi 5 | 4-5 |

---

## Managing the System

### Service Commands

```bash
# Display service
sudo systemctl status led-matrix.service
sudo systemctl restart led-matrix.service

# Web panel
sudo systemctl status led-matrix-web.service

# Force an update check
sudo systemctl start led-matrix-updater.service
```

### Viewing Logs

**From the web panel**: navigate to the Logs tab for a live, filterable log viewer.

**From the command line**:
```bash
# Live display logs
journalctl -u led-matrix.service -f

# Log files
tail -f logs/display.log
tail -f logs/updater.log
```

### Troubleshooting

```bash
# Full system diagnostic
sudo bash scripts/troubleshoot.sh

# YouTube download diagnostic
bash scripts/test_youtube.sh

# Hardware configuration
sudo bash scripts/configure_matrix.sh
```

### YouTube Video Management

Videos listed in `config/youtube_urls.csv` are downloaded at boot and cached in `downloaded_videos/`. Format:

```csv
url,title,duration
https://www.youtube.com/watch?v=...,Video Title,1
```

- `duration`: playback time in minutes (`x` = full video)
- Videos are downloaded once and cached permanently
- No internet needed after initial download
- yt-dlp is auto-updated before each download session

---

## Development (Windows/macOS)

The project includes a pygame-based LED matrix simulator:

```bash
pip install -r requirements.txt
python src/main.py
```

A window opens showing a virtual 64x64 LED matrix with per-pixel rendering.

### Testing

```bash
pytest
```

526 tests across 6 files covering simulator API, config validation, display modules, integration, web endpoints, and the living world simulation.

---

## How Auto-Update Works

1. A systemd timer fires every 30 minutes (and 2 minutes after boot)
2. Ensures WiFi connectivity
3. Runs `git fetch` + `git pull --ff-only` from the configured branch
4. Installs any new Python dependencies
5. Restarts the display service
6. All activity logged to `logs/updater.log`

Code-only changes (new features, bug fixes) are picked up automatically. Changes to systemd service files require re-running `sudo bash scripts/install.sh`.

---

## License

See repository for license information.
