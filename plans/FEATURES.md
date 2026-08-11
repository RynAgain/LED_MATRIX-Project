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
  - [x] `ExecStartPre` WiFi connection check (handled in Python via ensure_wifi())

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

## Display Features (36 modes)

### Games (10)
- [x] Tic Tac Toe (AI vs AI)
- [x] Snake (autonomous AI)
- [x] Pong (AI vs AI)
- [x] Breakout (autonomous AI)
- [x] Billiards (physics simulation)
- [x] Galaga (classic arcade shooter)
- [x] Space Invaders (classic arcade shooter)
- [x] Tanks (artillery combat)
- [x] Tetris (AI-driven falling blocks)
- [x] Pinball (Lost World-style scrolling table, 128x500 playfield)
- [x] Missile Command (six cities, MIRV warheads, crosshair interceptors, chain explosions, wave bonuses, demo AI leads its targets)

### Original Displays (1 video + 2 utility)
- [x] Time Display (clock)
- [x] Bitcoin Price Display (live API via requests)
- [x] YouTube Stream (yt-dlp + OpenCV)

### Visual Effects (11)
- [x] Fire (procedural flame simulation)
- [x] Plasma (sine-based color cycling)
- [x] Matrix Rain (falling green characters)
- [x] Starfield (3D star parallax)
- [x] Game of Life (Conway's cellular automaton)
- [x] Rainbow Waves (animated color gradients)
- [x] Lava Lamp (metaball / blob effect)
- [x] Living World (persistent village simulation)
- [x] Wireframe (rotating 3D polygon shapes)
- [x] Maze 3D (first-person maze walker)
- [x] Terrain Ball (rolling ball on procedural terrain)

### Utilities (13)
- [x] Weather (live weather display)
- [x] Text Scroller (scrolling message display)
- [x] Stock Ticker (live stock prices)
- [x] S&P 500 Heatmap (sector-based market heatmap)
- [x] Binary Clock (binary-encoded time display)
- [x] Base 6 Clock (senary time display -- Project Hail Mary / Eridian inspired)
- [x] Hail Mary Clock (book-accurate Eridian symbols, 40-hour day, astrophage aesthetic)
- [x] Countdown (configurable countdown timer)
- [x] QR Code (display WiFi password, custom URLs)
- [x] Slideshow (cycle uploaded images)
- [x] GitHub Stats (contribution heatmap)
- [x] System Stats (CPU, RAM, disk usage)
- [x] Logo Wholefoods (branded logo display)

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
- [x] HTTPS/TLS support
- [x] Password hashing (SHA-256)
- [x] Rate limiting on login attempts
- [x] WebSocket for real-time status updates (with polling fallback)

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

- [x] Documentation sync
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
- [x] Instant feature switching (interrupt current feature mid-display via web command)
- [x] Brightness control from web panel
- [x] Per-feature duration settings (different duration for each feature)
- [x] Countdown timer (configurable from web panel)
- [x] Image slideshow (upload images via web panel)
- [x] Live matrix preview in dashboard (screenshot of current display)
- [x] Pixel art editor (draw on matrix from phone in real-time)
- [x] Feature scheduling (time-based: games during day, ambient at night)

### New Display Modes
- [x] Lava lamp / metaball effect
- [x] QR code display (show WiFi password, custom URLs)

### Security
- [x] Password hashing (replace plaintext passwords in web.json)
- [x] Login rate limiting (prevent brute force)
- [x] HTTPS/TLS support for web panel

### Web Panel Polish
- [x] Drag-and-drop feature reordering
- [x] Weather location configurable from web settings
- [x] Night mode (auto-dim/off schedule)
- [x] WebSocket for real-time status (replace polling)

### Code Quality
- [x] Update test suite for all 19+ display modules
- [x] Clean up stray files ($null in project root)

---

## Next Up (Actionable)

### Security Hardening
- [x] Auto-generate `secret_key` on first boot (currently ships as `CHANGE_ME_TO_RANDOM_STRING` in `config/web.json`)
- [x] Auto-migrate plaintext password to hashed on first boot (default `"admin": "ledmatrix"` ships unprotected)
- [x] Set HTTPS to `enabled: false` in shipped `config/web.json` (currently committed as `true`, will fail on fresh installs without certs)
- [x] Add CSRF protection tokens to all web forms

### Slideshow / Image Management
- [x] Direct image upload endpoint (multipart file upload form in web panel, not just pixel editor save)
- [x] Image delete/manage UI (view, delete uploaded images from web panel)
- [x] Resize uploaded images to matrix dimensions (64x64) server-side

### Display Feature Gaps
- [x] Add all 33 display modules to FEATURES.md (only 20 were listed; added galaga, space_invaders, tanks, wireframe, maze_3d, terrain_ball, system_stats, living_world, logo_wholefoods, github_stats, countdown, lava_lamp, qr_code, slideshow)
- [ ] Boot screen configuration from web panel (intentionally skipped -- hardcoded by design)
- [x] GitHub stats config from web panel (PAT token, username)
- [x] Messages config from web panel (text_scroller messages management)

### Web Panel Enhancements
- [x] Config backup/restore (download/upload `config/` as zip from web panel)
- [x] Git version rollback from web panel (list recent commits, revert to selected)
- [x] Health check endpoint (`/api/health` for external monitoring tools)
- [x] REST API documentation page (auto-generated or static list of all endpoints)
- [x] Logs page improvements (filter by level, auto-scroll, clear logs)
- [x] Error notification system (flash persistent alerts when features fail to load)

### Reliability
- [x] Graceful degradation when internet is unavailable (skip API-dependent features, don't crash)
- [x] Config file backup before auto-update overwrites (save `config/*.json.bak` before `git pull`)
- [x] Watchdog timer for stuck display modules (kill and move to next if a feature hangs > 2x duration)
- [x] Disk space check before video downloads (prevent filling SD card)

### Developer Experience
- [x] Add execution tests for all 33 display modules (currently only ~16 have `_runs_briefly` tests)
- [ ] CI pipeline configuration -- removed, not needed per user
- [x] Code coverage reporting (pytest-cov integration)
- [ ] Type hints across all Python modules -- deferred (large scope, low urgency)
- [x] Pre-commit hooks (linting, formatting)

---

## Code Review Action Items

> Findings from the full-project code review, organized by severity.
> Each item is actionable with specific file references.

### TIER 1: CRITICAL / SECURITY

- [x] **[CRITICAL] WiFi credentials committed to git** -- `config/wifi.json` contains real SSIDs and passwords in version control. Add `config/wifi.json` to `.gitignore`, ship `config/wifi.json.example` with placeholders, and clean up the 20 duplicate TestNetwork entries.
- [x] **[CRITICAL] WiFi password exposed on command line** -- `src/wifi/manager.py:155` passes WiFi passwords as CLI arguments visible in `ps aux`. Use `nmcli` connection profiles or pass credentials via stdin.
- [x] **[CRITICAL] TOCTOU race in command file handling** -- `src/main.py:166-178` and the `_command_watcher` thread compete for the same command file without synchronization. Use `_pending_lock` to gate all command file I/O.
- [x] **[CRITICAL] `NameError` in time_display binary clock** -- `src/display/time_display.py:462` references `ImageFont` which is never imported. Add `from PIL import ImageFont` to module imports.
- [x] **[CRITICAL] Broken HSV colors in binary clock** -- `src/display/time_display.py:460,480` divides hue by 360 before passing to `_hsv_to_rgb()` which already expects 0-360 range. Remove the `/ 360.0` division.
- [x] **[CRITICAL] Module-level network thread on import** -- `src/display/sp500_heatmap.py:298` starts a background HTTP thread at import time. Move the thread start inside `run()`.
- [x] **[CRITICAL] Unauthenticated WebSocket endpoint** -- `src/web/app.py:866` `/ws/status` has no session validation. Add `if "user" not in session: ws.close(); return` at handler start.
- [x] **[CRITICAL] `_update_villagers()` is 1370 lines** -- `src/display/living_world/villager_ai.py:494-1367` is unmaintainable. Refactor into per-state handler functions with a dispatcher.

### TIER 2: HIGH

- [x] **[HIGH] Pin yt-dlp to a specific release** -- `requirements.txt:22` pulls master HEAD. Pin to a specific release tag.
- [x] **[HIGH] Fix git stash pop after failed pull** -- `src/updater/auto_update.py:202-226` pops stash even when pull fails, risking merge conflicts. Only pop stash on successful pull.
- [x] **[HIGH] Weak SHA-256 password hashing** -- `src/web/app.py:30` uses SHA-256 without key stretching. Replace with `hashlib.pbkdf2_hmac` with >=600k iterations or bcrypt.
- [x] **[HIGH] Hardcoded default credentials** -- `src/web/app.py:117` falls back to `admin/ledmatrix`. Force password change on first boot or generate random password.
- [x] **[HIGH] XSS via onclick handlers in templates** -- `src/web/templates/youtube.html:24,69` and `wifi.html:25` inject server data into JS onclick attributes. Use `data-*` attributes with `|tojson` filter instead.
- [x] **[HIGH] Silent `write_status()` failure** -- `src/main.py:88-91` bare `except: pass` swallows all errors. Log at debug level.
- [x] **[HIGH] SSID parsing breaks on colons** -- `src/wifi/manager.py:109,129,94` splits on `:` which is valid in SSIDs. Use `nmcli -t --escape yes` mode.
- [x] **[HIGH] Simulator DrawText renders blocks instead of text** -- `src/simulator/graphics.py:55-77` renders solid rectangles for all characters. Parse BDF fonts or use the bitmap font from `boot_screen.py`.
- [x] **[HIGH] Simulator Font.LoadFont ignores font file** -- `src/simulator/graphics.py:31-36` stores path but never reads it. At minimum infer metrics from filename.
- [x] **[HIGH] Simulator brightness is a no-op** -- `src/simulator/matrix.py:293-294` ignores brightness setting, making night-mode untestable. Apply as multiplier in render.
- [x] **[HIGH] Simulator singleton never cleaned up** -- `src/simulator/matrix.py:86-91` `_SimulatorWindow._instance` persists forever. Add `shutdown()` classmethod with `atexit` registration.
- [x] **[HIGH] Dev.py logs default password** -- `dev.py:63` logs `"Login: admin / ledmatrix"` to file. Remove password from log.
- [x] **[HIGH] Missing `should_stop()` in game sleep loops** -- Add `should_stop()` checks to blocking sleeps in: `billiards.py:387`, `breakout.py:360-377`, `snake.py:252-270`, `pong.py:319,336`, `tic_tac_toe.py:228-274`, `tanks.py:288`, `maze_3d.py:456`, `stock_ticker.py:129`. Create shared `_interruptible_sleep()` helper in `_shared.py`.
- [x] **[HIGH] Socket leak in system_stats** -- `src/display/system_stats.py:189-196` socket not wrapped in `try/finally` or `with`. Use context manager.
- [x] **[HIGH] Race condition on `_bg_fetching` flag** -- `src/display/sp500_heatmap.py:257-289` reads/writes without lock. Protect with `_bg_lock`.
- [x] **[HIGH] Atomic file writes for living world** -- `src/display/living_world/persistence.py:97` and `world_api.py:83` write directly to file. Use temp file + `os.replace()`.
- [x] **[HIGH] Valley cols cache never invalidated** -- `src/display/living_world/terrain.py:171-194` cache is useless because `_invalidate_valley_cols_cache()` is never called and cache_gen never passed. Fix caching or remove it.
- [x] **[HIGH] Dead `_reset_requested` handler** -- `src/display/living_world/simulation.py:157` sets attribute never checked. Implement the reset handler or remove the command.
- [x] **[HIGH] Villager gets lumber from dead tree** -- `src/display/living_world/villager_ai.py:676-690` awards lumber even when target tree was already chopped by another villager. Check `target_tree.alive` before awarding.
- [x] **[HIGH] Hunting movement bypasses terrain checks** -- `src/display/living_world/villager_ai.py:870-874` allows walking through water/cliffs during chase. Apply same terrain checks as normal walking.
- [x] **[HIGH] `.coveragerc` excludes `living_world` and `simulator`** -- Remove these from the omit list since they have dedicated tests.
- [x] **[HIGH] Test smoke tests have zero output assertions** -- `tests/test_display_modules.py:77-254` and `tests/test_simulator.py` only verify "no crash." Add pixel-change assertions.
- [x] **[HIGH] Test global state leaks** -- Rate limiter, event log, `sys.modules`, real config files leak between tests. Use `tmp_path` and fixture-based isolation.

### TIER 3: MEDIUM

- [x] **[MEDIUM] `VALID_FEATURE_NAMES` duplicated** -- `src/config_validator.py:17-27` duplicates list from `main.py`. Define canonical list in one shared location.
- [x] **[MEDIUM] No validation of `matrix_hardware` config block** -- `src/config_validator.py` does not validate hardware settings. Add `validate_hardware_config()`.
- [x] **[MEDIUM] No validation of `schedule.json`** -- Add `validate_schedule_config()` to `config_validator.py`.
- [x] **[MEDIUM] Replace `_stop_flag` bool+Lock with `threading.Event`** -- `src/display/_shared.py:4` would allow `wait(timeout)` for near-instant command response.
- [x] **[MEDIUM] Internet check uses unreliable `httpbin.org`** -- `src/main.py:27-34`. Use a configurable, more reliable endpoint.
- [x] **[MEDIUM] Thread-unsafe globals in main.py** -- `src/main.py:61-64` `_shutdown`, `_current_feature` accessed by multiple threads without locks. Use `threading.Event` for shutdown.
- [x] **[MEDIUM] CSRF bypass for JSON API endpoints** -- `src/web/app.py:619` skips CSRF for `request.is_json`. Validate custom header like `X-Requested-With`.
- [x] **[MEDIUM] Unchecked `int()` on form input** -- `src/web/app.py` multiple routes (737,753,787-789,795,800-803,829,930,1028,1061-1063). Add `try/except ValueError`.
- [x] **[MEDIUM] Config restore can overwrite `web.json`** -- `src/web/app.py:1598-1606`. Exclude `web.json` from restore or add backslash path traversal check.
- [x] **[MEDIUM] XSS via `insertAdjacentHTML`** -- Multiple templates (`youtube.html:89`, `countdown.html:52`, `settings.html:399`, `living_world.html:191`, `slideshow.html:94`, `pixel_editor.html:102`). Use `textContent` instead of `innerHTML`.
- [x] **[MEDIUM] External CDN script without SRI hash** -- `src/web/templates/features.html:88` loads SortableJS without integrity check. Add SRI hash or vendor locally.
- [x] **[MEDIUM] `random.seed()` reseeds global state** -- `src/display/galaga.py:100` and `tanks.py:244`. Use local `random.Random(42)` instance.
- [x] **[MEDIUM] Repeated import inside render loops** -- `countdown.py:90`, `galaga.py:166`, `space_invaders.py:171`, `tanks.py:341`, `wireframe.py:348`, `sp500_heatmap.py:317`. Move imports to module level.
- [x] **[MEDIUM] Performance: lava_lamp pure Python metaballs** -- `src/display/lava_lamp.py:84-109` O(W*H*N) per frame. Consider numpy or lookup tables.
- [x] **[MEDIUM] Performance: plasma sin() calls** -- `src/display/plasma.py:38-48` 16K+ trig calls per frame. Use precomputed sine tables.
- [x] **[MEDIUM] Dead code: `_render_heatmap()`** -- `src/display/sp500_heatmap.py:146-197` never called. Remove or consolidate.
- [x] **[MEDIUM] `ip_addr` computed but never displayed** -- `src/display/system_stats.py:332,365,376`. Either display it or stop computing it.
- [x] **[MEDIUM] YouTube private attribute access** -- `src/display/youtube_stream.py:489` accesses `downloader._ready_queue`. Add public `has_pending()` method.
- [x] **[MEDIUM] Entity head/body color names swapped** -- `src/display/living_world/entities.py:63-64` `head_color` from clothes palette, `body_color` from skin. Rename to `top_color`/`bottom_color`.
- [x] **[MEDIUM] Event log thread safety** -- `src/display/living_world/event_log.py:22` module-level deque without lock. Add `threading.Lock`.
- [x] **[MEDIUM] Lighting performance on RPi** -- `src/display/living_world/lighting.py:12-84` O(structures * mask_size) per frame. Pre-filter visible structures.
- [x] **[MEDIUM] Non-atomic snapshot writes** -- `src/display/living_world/world_api.py:83`. Use temp + `os.replace()`.
- [x] **[MEDIUM] Command file checked every frame** -- `src/display/living_world/simulation.py:82-95`. Throttle to every ~30 ticks.
- [x] **[MEDIUM] Snow flake list unbounded** -- `src/display/living_world/world_updates.py:519-544`. Cap at `max_snow = 200`.
- [x] **[MEDIUM] Merge terrain + water render passes** -- `src/display/living_world/rendering.py:127-182` two full 4096-pixel passes. Merge into single pass.
- [x] **[MEDIUM] Separate test deps from production** -- `requirements.txt:41-42` has pytest in main requirements. Move to `requirements-dev.txt`.
- [x] **[MEDIUM] pygame platform marker misses Linux** -- `requirements.txt:29`. Add `sys_platform == "linux"`.
- [x] **[MEDIUM] Conditional assertions in living world tests** -- `tests/test_living_world.py:3449,3871,4013-4015` silently pass. Force deterministic behavior.
- [x] **[MEDIUM] Weak test assertions in web tests** -- `tests/test_web.py:101-156` use `or` that always passes. Assert specific flash messages.
- [x] **[MEDIUM] Add `--cov` to pytest defaults** -- `pytest.ini` doesn't invoke coverage automatically.

### TIER 4: LOW

- [x] **[LOW] Add docstrings to package `__init__.py` files** -- `src/__init__.py`, `src/display/__init__.py`.
- [x] **[LOW] Move `FONT_5X7` to shared `fonts.py`** -- `src/display/boot_screen.py:46-90`. Reusable by other modules.
- [x] **[LOW] Extract duplicated bitmap font/color utilities** -- `pong.py`, `breakout.py`, `snake.py`, `tic_tac_toe.py` share `DIGITS`, `_draw_digit`, `_lerp_color`, `_hsv_to_rgb`. Create `src/display/_utils.py`.
- [x] **[LOW] Remove dead `main()` from bitcoin_price** -- `src/display/bitcoin_price.py:61-67`. Unused function.
- [x] **[LOW] Remove unused `canvas` parameter** -- `src/display/bitcoin_price.py:12`. Never used.
- [x] **[LOW] Move DIGITS constant to module level** -- `src/display/countdown.py:45-57`. Recreated every function call.
- [x] **[LOW] Redundant `min()` in qr_code** -- `src/display/qr_code.py:48` both operands identical.
- [x] **[LOW] Hardcoded `arial.ttf` font** -- `src/display/bitcoin_price.py:20`. Remove truetype attempt.
- [x] **[LOW] Color clamping in simulator** -- `src/simulator/graphics.py:14` `Color` doesn't clamp to 0-255.
- [x] **[LOW] Deprecated `PILImage.NEAREST`** -- `src/simulator/matrix.py:346`. Use `Resampling.NEAREST`.
- [x] **[LOW] Deprecated `datetime.utcnow()`** -- `src/web/app.py:526`. Use `datetime.now(timezone.utc)`.
- [x] **[LOW] Logout via GET** -- `src/web/app.py:668`. Change to POST with CSRF.
- [x] **[LOW] Add CSP headers** -- `src/web/app.py`. Add `Content-Security-Policy` via `@app.after_request`.
- [x] **[LOW] Broken `toggle-slider` CSS class** -- `src/web/templates/wireframe.html:18`. Change to `toggle-switch`.
- [x] **[LOW] Add pytest markers for slow/integration** -- `pytest.ini`. Define and apply markers.
- [x] **[LOW] Add pytest-timeout** -- Prevent hanging tests. Set `timeout = 30`.
- [x] **[LOW] Slideshow loads all images into memory** -- `src/display/slideshow.py:17-34`. Load lazily one at a time.
- [x] **[LOW] `_apply_campfire_light` missing lower clamp** -- `src/display/living_world/lighting.py:25-27`. Add `max(0, ...)`.
- [x] **[LOW] Dead `_compute_season()` function** -- `src/display/living_world/day_night.py:87-91`. Remove.
- [x] **[LOW] Dead villager AI branch** -- `src/display/living_world/villager_ai.py:956-960`. Remove acknowledged dead code.
- [x] **[LOW] Bow search range is identical** -- `src/display/living_world/villager_ai.py:1229` `20 if v.has_bow else 20`. Fix to differentiate.
- [x] **[LOW] Lumber deducted before building completes** -- `src/display/living_world/villager_ai.py:924-926`. Defer deduction or refund on interruption.

## Stability Hardening (2026-07-28 review)

- [x] Fix `barricade.py` syntax error (stray `j` before module docstring broke import)
- [x] Log rotation: `RotatingFileHandler` (1MB x 3) for `display.log` and `updater.log` -- prevents SD-card fill
- [x] Zombie feature-thread handling: abandoned watchdog threads are tracked; if one is still alive when the next feature starts, exit(1) for a clean systemd restart instead of racing on the shared matrix / cleared stop flag
- [x] Frame-heartbeat hang detection: `_SafeMatrixProxy` timestamps `SetImage`/`SwapOnVSync`; watchdog force-stops any feature with no frame for 60s (previously a deadlocked game went undetected for 48h)
- [x] Simulator matrix wrapped in `_SafeMatrixProxy` so heartbeat works in dev too
- [x] Slideshow re-pushes held frames every 0.5s so long holds don't trip the heartbeat
- [x] Auto-update restart gated on IDLE: updater defers pull/restart while user is in menu or game
- [x] Removed stale web-panel remnants from `logs/` (`command.json`, `status.json`, `display.pid`)

## Pinball Overhaul (2026-07-29)

Gameplay fixes (commit 42a6c37):
- [x] Drain detection covers outlanes (soft-lock fix)
- [x] Per-substep wall/flipper collision (no tunneling at high speed)
- [x] TILT mechanic: 3 nudges per ball kills flippers for 3s
- [x] Orbit shot implemented (entry/exit markers, 2000 pts, purple FX)
- [x] Rollover lane groups reset + 3000-pt completion bonus
- [x] Demo stall guard (random impulse after 2s near-zero speed)

Look & feel + physics polish:
- [x] Momentum-preserving flipper hits: ball velocity reflected off the moving surface, real omega x r surface velocity added; tip hits harder than base; cradling on a raised flipper works
- [x] Constant-angular-speed flipper stroke (omega stays strong through full travel)
- [x] Wall bounces split into normal restitution (0.62) + damped tangential roll
- [x] Bumper kick scales with incoming speed + slight random deflection
- [x] Slingshots fire only on approach, with cooldown (no double-triggers)
- [x] Camera look-ahead biases view toward ball travel direction
- [x] Depth-gradient playfield background (fades darker toward drain)
- [x] Expanding shockwave ring on bumper hits + specular cap highlights
- [x] Slingshots drawn as filled kicker triangles
- [x] Flippers rendered as tapered wedges with pivot posts
- [x] Ball speed halo, pulsing lit rollover lamps, HUD score underline

Performance + collision quality (playtest feedback):
- [x] Static playfield (gradient/walls/rails/drain) pre-rendered once to a 128x500 image; draw() crops the viewport -- ~90 -> ~15 draw calls/frame
- [x] Wall collision resolves only the deepest-penetrating segment (no corner fighting/jitter)
- [x] Rolling contact mode: grazing hits cancel normal velocity instead of micro-bouncing
- [x] Boundary clamps use shared WALL_RESTITUTION, only bounce when moving inward

Clipping elimination (2026-08-01, playtest feedback):
- [x] Removed plunger-lane clamp that teleported every launched ball through the lane wall (the main clipping source -- it was accidentally acting as the launch mechanism)
- [x] Lane geometry made actually traversable: launch arch diagonal extended to the rail, 5px dead corridor wall removed, 2px dead channel merged into lane wall
- [x] PLUNGER_MAX raised to 11.5 (lane climb needs ~9.8); speed cap exempted in lane; weak launches fall back and re-dock on the plunger
- [x] Swept line-crossing test per substep catches true wall crossings the distance check misses
- [x] Wall resolution iterates up to 3 passes (acute wedges can't leave residual penetration)
- [x] Sling kicks: front-face-only via robust cross-product side test; deterministic push-out along kick normal
- [x] Verified: 120,000-frame sim across 10 seeds, zero wall-overlap frames, full gameplay (launches, slings, drains, complete games)

Feature batch: multiball, kickback, bonus, haptics (2026-08-01):
- [x] Multiball: game refactored to a balls list (balls[0] = primary/plunger ball); all collision paths take a ball param; per-ball swept-collision anchors; camera follows the field ball nearest the drain; nudge affects every field ball
- [x] Lock saucer at (26,162): capture two balls (re-dock + 1000 pts + bonus units), third entry releases 3-ball MULTIBALL; 1s debounce; pulsing pink ring with locked-ball pips
- [x] 2x scoring during multiball (score_mult = bonus_mult x 2); drained multiball balls are removed without consuming balls_left; "MULTIBALL OVER" banner on the last
- [x] Left-outlane kickback: armed at game start, fires the ball back up the lane once, re-armed by completing the bottom rollover group; pulsing yellow lane indicator
- [x] End-of-ball bonus: units accrue per ball (+1 rollover, +2 target, +5 orbit/lock), paid out as units x 100 x bonus_mult on a real drain; multiplier resets each ball
- [x] Controller rumble driven by per-frame impact strength (bumpers, slings, flipper hits, lock, multiball, kickback, tilt, drains)
- [x] Generic fading event banner (LOCK / MULTIBALL / BONUS / KICKBACK ARMED / TILT)
- [x] Flipper exit-speed cap (1.5x game speed cap): per-substep contact was re-adding surface velocity, pumping balls to 30-45 px/frame teleports (found by the new test suite)
- [x] Headless test suite `tests/test_pinball_sim.py`: 16 tests -- seeded no-clipping/OOB/speed sims, gameplay-alive, flipper impulse + passive no-energy-gain, swept wall test, kickback, lock/multiball lifecycle, bonus tally, ball save, tilt, haptics
- [x] Verified: 60,000-frame soak across 10 seeds -- zero overlaps, zero out-of-bounds, zero speed violations, 171 launches, 21 games, high score 248,950
