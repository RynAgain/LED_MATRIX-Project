# LED_MATRIX-Project -- Feature Tracker

> Tracks all features and improvements for the LED Matrix Project revamp.
> All items start unchecked. Check off as implementation is completed and verified.

---

## Core Infrastructure

- [x] WiFi configuration system
  - [x] `config/wifi.json` with SSID, password, priority, hidden flag
  - [x] Connect to open/public WiFi networks (no password)
  - [x] Captive portal detection and handling
  - [x] Multiple network support with priority ordering
  - [x] Connection retry logic with fixed delay
  - [x] Connectivity check before starting display features

- [x] Auto-update from GitHub
  - [x] Detect remote changes via `git fetch` + `git rev-parse`
  - [x] Pull changes cleanly (`git stash` local, `git pull`)
  - [x] Reinstall dependencies after pull (`pip install -r requirements.txt`)
  - [x] Restart the display service after successful update
  - [x] Configurable check interval in `config/config.json`
  - [x] Log all update activity to centralized log

- [x] Systemd service for startup
  - [x] `led-matrix.service` unit file for display process
  - [x] `led-matrix-updater.service` or timer unit for auto-updater
  - [x] Auto-start on boot (`After=network-online.target`)
  - [x] Auto-restart on crash (`Restart=always`, `RestartSec=10`)
  - [x] Network dependency enforcement (`Wants=network-online.target`)
  - [ ] `ExecStartPre` WiFi connection check (handled in Python instead of systemd)

- [x] Logging system
  - [x] Centralized log directory (`logs/`)
  - [x] Structured log format with timestamps
  - [x] Log rotation (size-based or time-based)
  - [x] Separate logs for display and updater subsystems

- [x] Config validation
  - [x] Validate `config/config.json` schema on startup
  - [x] Validate `config/wifi.json` schema on startup
  - [x] Graceful error messages for malformed config
  - [x] Default/fallback values for missing optional fields

---

## Display Features (19 modes)

### Games
- [x] Tic Tac Toe (AI vs AI)
- [x] Snake (autonomous AI)
- [x] Pong (AI vs AI)
- [x] Billiards (physics simulation)

### Original Displays
- [x] Time Display (clock)
- [x] Bitcoin Price Display (live API via requests)
- [x] YouTube Stream (yt-dlp + OpenCV)

### Visual Effects
- [x] Fire (procedural flame simulation)
- [x] Plasma (sine-based color cycling)
- [x] Matrix Rain (falling green characters)
- [x] Starfield (3D star parallax)
- [x] Game of Life (Conway's cellular automaton)
- [x] Rainbow Waves (animated color gradients)

### Utilities
- [x] Weather (live weather display)
- [x] Text Scroller (scrolling message display)
- [x] Stock Ticker (live stock prices)
- [x] S&P 500 Heatmap (sector-based market heatmap)
- [x] Binary Clock (binary-encoded time display)

---

### Web Control Panel
- [x] Flask-based web server with mobile-responsive UI
- [x] Password-protected authentication with session management
- [x] Dashboard with live status display (auto-refreshing)
- [x] Feature toggle page with iOS-style switches
- [x] WiFi network management (add/remove networks)
- [x] Settings page (GitHub branch, log level)
- [x] REST API endpoints (status, restart, update)
- [x] Systemd service for web panel
- [x] Status file IPC between display and web services
- [x] PID-based SIGHUP for config reload
- [x] Dark theme, mobile-first CSS
- [x] Web endpoint tests (15 tests)
- [ ] HTTPS/TLS support
- [ ] Password hashing (currently plaintext in config)
- [ ] Rate limiting on login attempts
- [ ] WebSocket for real-time status updates (currently polling)

---

## Project Quality

- [x] Clean project structure
  - [x] Move Python source files into `src/` directory
  - [x] Create `src/display/` package for all display feature modules
  - [x] Create `src/wifi/` package for WiFi manager
  - [x] Create `src/updater/` package for auto-update logic
  - [x] Move config files into `config/` directory
  - [x] Move shell scripts into `scripts/` directory
  - [x] Move systemd unit files into `services/` directory
  - [x] Create `src/main.py` as the single entry point

- [x] Updated dependencies
  - [x] Remove pinned `opencv-python==3.4.11.12` (use compatible modern version)
  - [x] Pin all dependencies to tested versions in `requirements.txt`
  - [x] Verify all deps install cleanly on Raspberry Pi OS

- [x] Virtual environment support
  - [x] `scripts/install.sh` creates and activates a venv
  - [x] Systemd service runs Python from the venv
  - [x] Document venv setup in README

- [x] Remove legacy/dead code
  - [x] Remove `fix_python_path.bat` (Windows-only, not relevant to Pi)
  - [x] Remove VLC references from `install_and_update.sh` (`sudo apt-get install -y ... vlc`)
  - [x] Audit and remove any other unused code paths

- [x] Comprehensive README update
  - [x] Project overview and purpose
  - [x] Hardware requirements (Raspberry Pi model, LED matrix specs)
  - [x] Software prerequisites
  - [x] Installation instructions (one-command setup)
  - [x] Configuration guide (`config.json`, `wifi.json`)
  - [x] Adding/removing display features
  - [x] Troubleshooting section

- [ ] Documentation sync
  - [x] Reconcile `PROJECT_OVERVIEW.md`, `QUICKSTART.md`, `STARTUP_GUIDE.md` with actual project state (removed; README is single source of truth)
  - [x] Remove or consolidate `FIXES_SUMMARY.md` into changelog (removed)
  - [x] Ensure `config.json` docs match actual schema
  - [x] Single source of truth for setup instructions across all documentation

---

## Development Experience

- [x] Pygame-based LED matrix simulator for Windows/macOS development
- [x] Simulator auto-registers as rgbmatrix module for transparent dev experience
- [x] Mock graphics module (Color, Font, DrawText, DrawCircle, DrawLine)
- [x] Add unit tests for display modules
- [x] Add integration test that runs full feature cycle in simulator

### Cython Bindings Improvements

- [x] Added NULL guard in RGBMatrix.__dealloc__ to prevent segfault
- [x] Added language_level=3str directive for Python 3 consistency
- [x] Migrated deprecated property syntax to @property decorators
- [x] Fixed integer type mismatches in RGBMatrixOptions setters
- [x] Replaced bare Exception with specific error types
- [x] Added Color.__repr__ for debuggability
- [x] Updated Makefile for modern Cython
- [x] Release GIL in SetPixelsPillow() tight loop
- [x] Replace Pillow unsafe_ptrs with tobytes() for forward compatibility
- [x] Expose DrawText with background_color parameter
- [x] Expose VerticalDrawText

---

## Planned Improvements

### High Impact Features
- [ ] Instant feature switching (interrupt current feature mid-display via web command)
- [ ] Brightness control from web panel
- [ ] Per-feature duration settings (different duration for each feature)
- [ ] Countdown timer (configurable from web panel)
- [ ] Image slideshow (upload images via web panel)
- [ ] Live matrix preview in dashboard (screenshot of current display)
- [ ] Pixel art editor (draw on matrix from phone in real-time)
- [ ] Feature scheduling (time-based: games during day, ambient at night)

### New Display Modes
- [ ] Lava lamp / metaball effect
- [ ] QR code display (show WiFi password, custom URLs)

### Security
- [ ] Password hashing (replace plaintext passwords in web.json)
- [ ] Login rate limiting (prevent brute force)
- [ ] HTTPS/TLS support for web panel

### Web Panel Polish
- [ ] Drag-and-drop feature reordering
- [ ] Weather location configurable from web settings
- [ ] Night mode (auto-dim/off schedule)
- [ ] WebSocket for real-time status (replace polling)

### Code Quality
- [ ] Update test suite for all 19+ display modules
- [ ] Clean up stray files ($null in project root)
