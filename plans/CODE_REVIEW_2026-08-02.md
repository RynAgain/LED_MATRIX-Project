# Whole-System Code Review — 2026-08-02

Method: 5 parallel deep reviews (core runtime / info features / big games / small
games+toys / living_world+ops) + cross-cutting static sweeps. All P0/P1 claims
spot-verified against source before inclusion. ~35k lines reviewed.

Overall: hygiene is strong (every network call and subprocess has a timeout, no
bare excepts, atomic living_world saves, monotonic heartbeat). The real work is:
one security hole in install.sh, render-thread network fetches that trip the
60s watchdog, a handful of genuine logic bugs, and a lot of batchable
perf/dedup wins for the Pi.

Severity: P0 security/data-loss · P1 crash/robustness · P2 improvement · P3 nit.

---

## P0 — Security

- [ ] **P0-1 install.sh:327-328 — sudoers wildcard path traversal (VERIFIED)**
  `NOPASSWD: /bin/cp * /etc/systemd/system/*` and `sed -i * /etc/systemd/system/*`.
  sudoers `*` matches any argument string, including `../../cron.d/evil`, so the
  service user can write root-owned files anywhere. Fix: replace with a fixed-path
  wrapper script (e.g. `/usr/local/sbin/led-matrix-install-service`) that copies
  only `services/*.service` to `/etc/systemd/system/`, and allow only that +
  the four systemctl lines. Update auto_update.py `_reinstall_service_files()`
  to call the wrapper.
- [ ] **P0-2 install.sh:40, update.sh:171 — `eval echo "~$ACTUAL_USER"` injection (VERIFIED)**
  Replace with `getent passwd "$ACTUAL_USER" | cut -d: -f6`.

## P1 — Crash / watchdog-kill / data-loss

Core runtime:
- [ ] **P1-1 main.py:~269 — cv2.VideoCapture released in `try`, not `finally`** — fd leak on any exception in the frame loop. Move `cap.release()` to `finally`. Same leak in dead `handle_play_video()` (see P3-8: delete it).
- [ ] **P1-2 app_state.py:549-551 — IDLE-check/poll race (VERIFIED)** — watcher checks `self.mode is AppMode.IDLE` then polls; main thread can enter MENU between the two, and both threads drain the same event queue. Small window but real. Fix: guard mode transitions + poll with a lock, or have the main thread set a `_watcher_pause` Event before entering MENU/IN_GAME and wait for ack.
- [ ] **P1-3 settings_screen.py:248,253 + controller_screen.py:132-136 — save return ignored; `_dirty` cleared even when disk write fails** (read-only SD card case). Check return, log error, keep dirty.
- [ ] **P1-4 auto_update.py:702,715 — nuclear recovery (`git reset --hard`) skips `_backup_configs()`/`_restore_configs()`** — user config lost exactly when recovery runs. Wrap both nuclear paths.
- [ ] **P1-5 auto_update.py:557-619 — service-file placeholder substitution unverified** — if template path changes, `str.replace` no-ops and a wrong unit file is installed → crash loop. Assert placeholder absent post-substitution; skip write + warn otherwise.
- [ ] **P1-6 wifi/manager.py:231-263 — captive-portal probe doubles every connectivity check** — worst case ~210s main-thread block at boot. Only probe for captive portal once, after retries are exhausted.

Render-thread network fetches (watchdog kills at 60s of no frames):
- [ ] **P1-7 stock_ticker.py:575-605 — `_fetch_top_market_cap()` on render thread: 6×15s batches ≈ 91s worst case** — guaranteed watchdog kill in top_market_cap mode. Move universe refresh to a daemon thread; render from last cached list meanwhile.
- [ ] **P1-8 stock_ticker.py:536-560 — `_prefetch_window()` chains up to 4×(10s+10s)=80s of fetches on the render thread.** Move `_ensure_quote` into the background thread with a thread-safe results dict.
- [ ] **P1-9 album_art.py:209 — art fetch (up to 25s) on render thread at every album switch.** Prefetch next image on a daemon thread; keep showing current image until ready.
- [ ] **P1-10 github_stats.py:171 — 3-page fetch (≤31.5s) before first frame.** Show loading frame immediately; fetch in background.

Living world / games:
- [ ] **P1-11 villager_ai.py:488 — `_respawn_if_empty` missing `0 <= sy < DISPLAY_HEIGHT` bounds guard (VERIFIED)** — mined-out columns can leave out-of-range heights → IndexError kills the sim thread. Copy the guard from line 1607.
- [ ] **P1-12 persistence.py — `start_time` accepted by `save_world()` but never written** — day/night phase resets to dawn on every restore. Persist `elapsed`; restore `start_time = time.time() - elapsed`.
- [ ] **P1-13 rubiks_cube.py:218-223 — B-face double rotation (VERIFIED)** — `apply_move` already rotated the face at line 146/148; the B branch rotates it again and never cycles B edges. Delete the double rotation and implement the B edge cycle (or at minimum delete lines 218-223 so B is a face-only turn like before, visually consistent).
- [ ] **P1-14 billiards.py — only module drawing per-pixel with `canvas.SetPixel` (~4,286 calls/frame; ~25k extra during cue animation).** Port to the standard PIL SetImage pattern with a pre-rendered felt/borders/pockets background.
- [ ] **P1-15 billiards.py:401,430 — raw `time.sleep(1)` / `sleep(0.04)` not interruptible** (helper already imported). Use `interruptible_sleep`.
- [ ] **P1-16 fractal.py:156-202 — Mandelbrot 4,096×300 Python iters/frame at max zoom (~1fps on Pi 4, worse on Zero).** Cap `max_iter` at 80 (no visible difference at 64×64).
- [ ] **P1-17 services/led-matrix.service — no `WatchdogSec`, `MemoryMax`, `OOMPolicy`.** Add `WatchdogSec=90` + `sd_notify` pings in the main loop, `MemoryMax=512M`, `OOMPolicy=stop`.
- [ ] **P1-18 update.sh — missing `set -euo pipefail`** — failed pip install still exits 0 and restarts the service on broken deps.

## P2 — Correctness / robustness improvements

- [ ] **P2-1 time_display.py:624,637,649 — World Clock offsets hardcoded to CST and wrong (VERIFIED)**: UTC shown as local+5 (CST is UTC-6), Tokyo +14-from-CST breaks during CDT, London literally displays UTC. Compute from `datetime.now(timezone.utc)` + real tz offsets.
- [ ] **P2-2 bitcoin_price.py:70-73 — no stale-data fallback; blank display on API failure.** Cache last price; render it with a stale marker.
- [ ] **P2-3 github_stats.py:54-71 — rate-limit 403 silently zeroes the heatmap; no Retry-After respect; no on-disk cache.**
- [ ] **P2-4 update_screen.py:94,107 — force-update hardcodes `origin/main`**, ignoring `github_branch` config.
- [ ] **P2-5 main.py:30 / app_state.py:240 — INTERNET_FEATURES duplicated** — move to feature_registry.py.
- [ ] **P2-6 main.py:163 — 60s frame-hang watchdog kills slideshow with >60s holds** — slideshow already re-pushes held frames every 0.5s (verify), but fractal.py:315-318 dragon-curve hold loop pushes no frames (kills at duration≥~250s) — add SetImage to the hold loop.
- [ ] **P2-7 stock_ticker.py:118 + sp500_heatmap.py:98 + github_stats.py:71 — courtesy `time.sleep` in fetch loops ignores stop event** — use `Event.wait()`.
- [ ] **P2-8 sp500_heatmap.py:249-252 — module-level `_bg_started` never reset across feature re-entries** — eager prefetch skipped on later runs.
- [ ] **P2-9 wifi/manager.py:395 — `disconnect()` hardcodes wlan0.**
- [ ] **P2-10 version.py:43 — git subprocess (5s timeout) on menu open** — cache; prefer VERSION file.
- [ ] **P2-11 main.py:34-55 — `_check_internet()` re-reads config.json every carousel cycle; 3s timeout tight for cold DNS.**
- [ ] **P2-12 app_state.py:355 — config re-read each cycle; transient read failure drops to bare defaults for a cycle** — keep last-good config.
- [ ] **P2-13 galaga.py — feature-parity outlier**: `run(matrix, duration)` only (no controller/interactive mode), imports only `should_stop` (no banner/rumble/interruptible_sleep), `ImageFont.load_default()` at lines 423/645 instead of `_fonts`.
- [ ] **P2-14 living_world sim thread perf**: `_find_farm_site` O(structures+trees+farms) per candidate column (villager_ai.py:121-169 — precompute occupied-x set); `_handle_villager_trading` O(N²) every AI tick (villager_ai.py:411-426).
- [ ] **P2-15 simulator fidelity**: linear brightness vs hardware gamma (~2.2) hides night-scene visibility bugs (simulator/matrix.py:223-233); `Font.LoadFont` fakes BDF metrics from filename (graphics.py:88-104).
- [ ] **P2-16 test coverage gaps**: no test for main.py watchdog/zombie-reap; no save_world→load_world disk roundtrip test; `_handle_reproduction` untested.
- [ ] **P2-17 main.py time.time() for feature-duration/join deadlines** (heartbeat already monotonic) — NTP step on RTC-less Pi skews windows; switch to monotonic.
- [ ] **P2-18 Per-frame perf batch (Pi)**:
  - time_display.py: 4096-px gradient per frame ×3 modes; both images fully re-rendered during crossfade (snapshot prev once); 360-iter seconds arc
  - fire.py:69: 4096 `random.uniform`/frame — precompute noise rows
  - wireframe.py:317-320: shape rebuilt+renormalized per frame — module-level cache
  - rubiks_cube.py:341-344: 1,296 trig calls/frame — hoist cos/sin per axis
  - space_invaders.py:226, tanks.py:341: `load_default()` per frame — hoist
  - tanks.py:243: `random.Random(99)` per frame — hoist
  - tanks.py:302-312: terrain per-pixel redraw — pre-render, patch craters
  - matrix_rain.py:84: ~600 `draw.text`/frame — pre-render glyphs
  - plasma.py/rainbow_waves.py: per-pixel atan2/sqrt — precompute angle/dist tables
  - game_of_life.py: new grids per frame — double-buffer swap
- [ ] **P2-19 Dedup batch**:
  - system_stats.py:40-118: full FONT_5X7 + helpers copy-pasted from _fonts.py — import instead
  - `_hsv_to_rgb` copies in time_display, lava_lamp, rainbow_waves, fractal — use _utils
  - video_player.py:487: imports text helpers from boot_screen instead of _fonts
  - album_art.py: `_fetch_album_art` + unused `_fetch_album_info` duplicate the same API call — merge
  - `ImageFont.load_default()` in bitcoin_price/sp500/countdown/github_stats/logo_wholefoods vs shared 5×7 font — standardize

## P3 — Nits / polish

- [ ] P3-1 controller.py:791-794 — START+SELECT combo line unreachable (solo START returns first). Solo-START quit IS the documented behavior, so just delete the dead line — unless we want START=pause someday, then reorder.
- [ ] P3-2 main.py:555-563 — feature_error.json non-atomic, no history; sp500 cache write non-atomic (both low-stakes).
- [ ] P3-3 auto_update.py:282 — config/.backup/ grows unbounded; keep last 5.
- [ ] P3-4 menu_system.py:136 — registry rebuilt every menu open; cache.
- [ ] P3-5 settings_screen.py:360 — `_controller` class attr → instance attr.
- [ ] P3-6 app_state / update_screen dead code — `_try_hard_reset()` (update_screen.py:154), `handle_play_video()` (main.py:207) — delete.
- [ ] P3-7 time_display.py:727 — `'current_image' in dir()` scope check → init None before loop.
- [ ] P3-8 base6_clock.py:135 — unbounded wall-clock into sin() — use elapsed-since-start.
- [ ] P3-9 qr_code.py:77-83 — `random.seed(hash(content))` is PYTHONHASHSEED-randomized — use hashlib for stable fake pattern.
- [ ] P3-10 slideshow.py:52-54 — `draw.text` without font arg — Pillow-version-dependent rendering.
- [ ] P3-11 villager_ai.py:1497 — `grass_fires=None` default silently disables fire response — default to `()`.
- [ ] P3-12 world_updates.py:596-598 — caravan oscillates forever at water crossings until trade timer expires.
- [ ] P3-13 villager_ai.py:478-492 — extinction respawn always at world center, may be far from all structures.
- [ ] P3-14 simulation.py:415-420 — dynamic import + wall-clock check per frame for snapshot throttle — hoist import, tick-based throttle.
- [ ] P3-15 weather.py:79 — comment/condition off-by-one (>90 vs >=90) — fix comment.
- [ ] P3-16 boot_screen.py:259, hail_mary_clock.py:338 — imports inside loops/functions — hoist.
- [ ] P3-17 tic_tac_toe.py:310-314 — fade loop without should_stop check (~300ms max).
- [ ] P3-18 space_invaders/tanks/tic_tac_toe — no interactive controller mode (best candidates among toys).
- [ ] P3-19 render loops allocate new PIL Image per frame broadly — consider reusable buffer pattern where cheap.

## Suggested fix batches

1. **Security/ops** (P0-1, P0-2, P1-17, P1-18) — install.sh sudoers wrapper, getent, systemd hardening, update.sh strict mode. Needs care: sudoers change must ship together with the auto_update.py wrapper call.
2. **Core runtime robustness** (P1-1..P1-6, P2-4, P2-5, P2-10, P2-11, P2-12, P2-17, P3-3..P3-6) — one commit.
3. **Render-thread fetch refactor** (P1-7..P1-10, P2-2, P2-3, P2-7, P2-8) — background-fetch pattern shared across stock_ticker/album_art/github_stats/bitcoin.
4. **Correctness fixes** (P1-11..P1-13, P2-1, P2-6, P3-9, P3-11, P3-12) — living world, rubiks, world clock, fractal hold.
5. **Perf batch** (P1-14..P1-16, P2-14, P2-18) — billiards port + per-frame hoists; sim-testable.
6. **Dedup/consistency** (P2-13, P2-19, P3-7, P3-8, P3-10, P3-15..P3-17) — fonts, hsv, galaga parity.
7. **Tests** (P2-16) — watchdog test, persistence roundtrip, reproduction handler.

Counts: 2 P0 · 18 P1 · 19 P2 · 19 P3.
