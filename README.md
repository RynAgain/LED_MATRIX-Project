# LED Matrix Project

A self-managing Raspberry Pi display system for a 64x64 RGB LED matrix. Cycles through 36 display features -- games, visualizations, info displays, and video playback. Auto-updates from GitHub, connects to WiFi, and runs unattended from boot. Control is via a USB gamepad and an on-matrix menu.

---

## Features

### Games
| Feature | Description |
|---------|-------------|
| Tic Tac Toe | AI vs AI on a 3x3 grid |
| Snake | Autonomous AI pathfinding |
| Pong | AI vs AI with increasing difficulty |
| Breakout | Autonomous brick-breaking with AI paddle |
| Billiards | Physics simulation with AI player |
| Galaga | Classic arcade-style space shooter |
| Space Invaders | Retro alien invasion game |
| Tanks | Tank battle simulation |
| Tetris | AI-driven falling blocks with line clears |

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
| Base 6 Clock | Senary time display (Project Hail Mary inspired) |
| Hail Mary Clock | Book-accurate Eridian symbols, 40-hour day, astrophage glow |
| Countdown | Timer with custom target date |
| Text Scroller | Scrolling custom messages |
| QR Code | Display QR codes for URLs |
| GitHub Stats | Repository statistics display |
| Slideshow | Cycle through custom images |
| Logo Display | Custom logo rendering |
| System Stats | Live CPU, RAM, temperature bars with hostname/IP |

### Video
| Feature | Description |
|---------|-------------|
| Video Player | Pre-cached video playlist playback at 15 FPS (direct MP4 URLs) |

### System
| Feature | Description |
|---------|-------------|
| Boot Screen | Animated startup sequence (ring burst + loading bar) |
| System Stats | CPU/RAM/temp bar graphs + hostname/IP on the matrix |
| Gamepad Control | On-matrix menu, playable games, and settings via a USB gamepad |
| Auto-Updater | Git-based updates every 30 min with auto-repair for corrupt repos |
| Night Mode | Scheduled brightness + feature restrictions |

---

## Controls

The matrix is controlled with a generic USB gamepad (GameCube-style). There is
**no web UI** -- the former Flask control panel has been removed entirely.

| Input | Action |
|-------|--------|
| **Start** | Open the on-matrix menu (from the idle demo carousel) |
| **D-pad / analog stick** | Navigate menus; move in games |
| **A** | Select / confirm (and primary game action) |
| **B** | Back / cancel (and secondary game action) |
| **Start + Select** (or hold **Start** ~1.5s) | Quit the current game/menu back to the idle demo |

### Behavior by mode

The app runs as a small state machine with three top-level modes:

- **IDLE** -- the default demo carousel cycles through the enabled features
  exactly as before. Pressing **Start** breaks out of the demo and opens the
  menu.
- **MENU** -- the on-matrix menu. **D-pad** moves the highlight, **A** selects,
  **B** backs out one level (and resumes the demo at the root). From here you
  can open the **Games** submenu to launch a playable game, open **Settings**
  (live brightness + demo duration), or **Resume** the idle demo carousel.
- **IN_GAME** -- a playable game (Snake, Tetris, Pong) runs interactively with
  the controller forwarded to it. On game-over, or when you press the quit
  gesture (**Start + Select**, or hold **Start**), control returns to the menu.

Closing the simulator window (or a controller window-close event) cleanly shuts
the whole application down.

### Calibrating the gamepad

Because unbranded pads expose different raw button/axis indices, run the
calibration utility once (with the pad plugged in) to write
`config/controller.json`:

```bash
python -m src.input.controller calibrate
```

`config/controller.json` is the saved button/axis mapping produced by
calibration: it records which physical gamepad button or analog-axis index maps
to each logical action (A, B, Start, Select, the four D-pad directions). If the
file is missing, the input layer falls back to a **sensible default mapping**
for common no-brand USB pads, so the system still boots and is usable without
calibration -- calibration just guarantees the buttons line up with *your*
specific pad.

### Simulator (keyboard fallback)

On a dev machine with no gamepad, the simulator window accepts a keyboard
fallback so you can test the full menu/game flow without any hardware:
arrow keys / WASD move, `Z` = A, `X` = B, `Enter` = Start, `Tab` = Select.
The same Start + Select quit gesture works from the keyboard.

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
- systemd services for the display and auto-updater
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
3. Pre-cache videos (if video_player is enabled)
4. Begin cycling through enabled features (press **Start** on the gamepad to open the menu)
5. Check for GitHub updates every 30 minutes

---

## Boot Sequence

```
Power on
  --> Linux boot (~15-20s)
  --> systemd starts led-matrix.service (2s delay)
  --> Boot screen animation (ring burst + "LED MATRIX" + loading bar)
  --> WiFi connectivity check
  --> Video pre-caching (with loading ring, if enabled)
  --> Feature display loop begins
```

Videos are downloaded once to `downloaded_videos/` and cached permanently. Subsequent boots play instantly from disk. No internet required for cached content.

---

## Architecture

```
LED_MATRIX-Project/
  config/                  # All configuration files
    config.json            # Feature sequence, hardware settings, display options
    controller.json        # USB gamepad button/axis mapping (from calibration)
    wifi.json              # WiFi network credentials
    video_urls.csv         # Video playlist (direct MP4 URLs)
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
  services/                # systemd unit files
    led-matrix.service     # Main display service (runs as root for GPIO)
    led-matrix-updater.*   # Auto-update service + timer
  src/                     # Application code
    main.py                # Entry point: boot screen, config, state machine
    config_validator.py    # JSON schema validation
    app_state.py           # Top-level state machine (IDLE/MENU/IN_GAME)
    input/                 # USB gamepad controller + keyboard fallback
    menu/                  # On-matrix menu + settings screen
    display/               # 36 display feature modules
      boot_screen.py       # Boot animation + loading ring + pixel font
      _shared.py           # Shared stop signaling for features
      living_world/        # Procedural village simulation (multi-file)
    simulator/             # Pygame LED matrix emulator (dev only)
    wifi/                  # WiFi connection manager (nmcli)
    updater/               # Git-based auto-updater
  downloaded_videos/       # Video cache (persists across reboots)
  rgbmatrix/               # RGB LED matrix Cython bindings (optimized SetImage pipeline)
  tests/                   # Test suite (runs without Pi hardware)
  logs/                    # Runtime logs (display.log, updater.log)
```

### Application modes

`src/main.py` boots the matrix, shows the boot screen, loads config, then hands
off to the top-level state machine in [`src/app_state.py`](src/app_state.py),
which drives three modes:

```
IDLE  --(press Start)-->  MENU  --(select a game)-->  IN_GAME
  ^                         |                            |
  +------(Resume / B)-------+<-----(game over / quit)----+
```

- **IDLE** runs the demo carousel (the classic feature-cycling loop).
- **MENU** is the data-driven on-matrix menu in [`src/menu/`](src/menu/menu_system.py)
  (Games submenu, inline Settings, Resume).
- **IN_GAME** runs a playable game with the controller forwarded to it.

Input comes from a USB gamepad via [`src/input/`](src/input/controller.py)
(with a simulator keyboard fallback). There is **no web server** -- control is
entirely on-device through the gamepad and the on-matrix menu.

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

The vendored [`rgbmatrix/`](rgbmatrix/) Cython bindings include a custom-optimized [`SetImage()`](rgbmatrix/core.pyx:12) pipeline in [`core.pyx`](rgbmatrix/core.pyx) with three rendering tiers:

1. **Fast path** -- Direct Pillow `unsafe_ptrs` access via [`SetPixelsPillow()`](rgbmatrix/core.pyx:61). Zero-copy pointer access to the image's raw 32-bit RGBA pixel buffer. Decorated with `@boundscheck(False)` and `@wraparound(False)` to eliminate all array bounds checks at the C level. The entire pixel-setting loop runs inside a `with nogil:` block, fully releasing the Python GIL so background threads (command watcher, YouTube downloads) continue unblocked. Pixel data is unpacked directly from `uint32_t **image_ptr` -- no intermediate copies, no Python object creation per pixel.

2. **Medium path** -- `image.tobytes()` with a `nogil` typed C loop. The raw bytes pointer (`const unsigned char*`) is cast and iterated in pure C, again with the GIL released. This path is used when the Pillow version does not expose `unsafe_ptrs` (pre-10.x).

3. **Slow fallback** -- Pure Python per-pixel access with explicit bounds checking. Used only when neither of the above paths are available. Guarantees correctness but at the cost of Python overhead per pixel.

The [`graphics.pyx`](rgbmatrix/graphics.pyx) module provides:
- [`DrawText()`](rgbmatrix/graphics.pyx:61) with optional background color fill and kerning offset
- [`VerticalDrawText()`](rgbmatrix/graphics.pyx:86) for column-oriented text rendering
- [`DrawCircle()`](rgbmatrix/graphics.pyx:106) and [`DrawLine()`](rgbmatrix/graphics.pyx:109) primitives

These changes together yield significantly higher frame rates compared to the upstream Python bindings, especially on Pi 3/4 where the GIL release allows the display refresh thread and application logic to overlap.

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

# Force an update check
sudo systemctl start led-matrix-updater.service
```

### Viewing Logs

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

# Hardware configuration
sudo bash scripts/configure_matrix.sh
```

### Video Playlist Management

Videos listed in `config/video_urls.csv` are downloaded at boot via direct HTTP and cached in `downloaded_videos/`. Format:

```csv
url,title,duration
https://archive.org/download/example/video.mp4,Video Title,1
```

- `url`: any direct HTTP/HTTPS link to a video file (archive.org, S3, GitHub Releases, self-hosted, etc.)
- `duration`: playback time in minutes (`x` = full video)
- Videos are downloaded once and cached permanently
- No internet needed after initial download

> **Note:** YouTube URL support was removed. YouTube's increasingly aggressive anti-bot measures
> (PO tokens, cookie expiration, rate limiting) made yt-dlp-based downloads unreliable on headless
> devices like the Pi. Direct MP4 URLs from stable hosts like archive.org are far more reliable
> and require no authentication or special tooling.

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

Tests cover the simulator API, config validation, display modules, the input/controller layer, the menu and app state machine, the playable games, integration, and the living world simulation.

---

## How Auto-Update Works

1. A systemd timer fires every 30 minutes (and 2 minutes after boot)
2. Ensures WiFi connectivity
3. Runs `git fetch` + `git pull --ff-only` from the configured branch
5. Detects and auto-repairs corrupt Git objects (`prune`, `gc`, `fsck`)
6. Installs any new Python dependencies
7. Restarts the display service
8. All activity logged to `logs/updater.log`

Code-only changes (new features, bug fixes) are picked up automatically. Changes to systemd service files require re-running `sudo bash scripts/install.sh`.

### Git Auto-Repair

If `git fetch` fails due to corrupt loose objects (common on Pi after power loss), the updater automatically:
1. Runs `git prune` to remove unreachable objects
2. Runs `git gc` to repack the object database
3. Runs `git fsck` to verify integrity
4. Retries the fetch/pull cycle

A manual emergency repair script is also available:
```bash
sudo bash scripts/repair.sh
```

---

## License

See repository for license information.
