# Star Fox: Corneria rebuild

## Scope
Approved first slice: one polished self-playing Corneria mission. Keep controller gameplay, shared laser/collision math, menu entry, and local settings. User approved pushing the previewed Corneria slice on 2026-10-08. Preserve remote main and unrelated Pinball work; device installation remains unverified.

## Live references
- `src/display/starfox.py`: `_Ship.draw`, `_AI.decide`, `_WaveManager.update`, `_draw_hud`, and `run` provide the existing movement, combat, wave, HUD, and lifecycle contracts.
- `src/display/zelda_quest/preview.py`: Pillow-based scenery composed separately from gameplay.
- `tests/test_starfox_sim.py`: aiming, boss lifecycle, AI, and controller physics regression tests.
- `tests/test_missile_command.py`: seeded simulation and real-render checks.

## Implementation
- [x] Shaded Arwing with bank/roll geometry and twin exhaust; daytime Corneria with layered hills, river, road, and passing structures.
- [x] Demo-only mission progression: fly-in, three combat formations, boss, victory flyout, clean restart. No wall-clock stage swaps in demo mode.
- [x] Velocity-aware autopilot steering and predictive dodging; short readable callouts.
- [x] Unit and real-loop tests, full repository test run, lint, compile check, and animated real-render preview completed. Full-suite failures remain documented below.

## Verification
Focused verification: 45 tests pass, including five seeded 1,800-frame real-render loops, mission completion/restart, controller routing, death recovery, deadline/stop, and HUD/armor regressions. Changed-code flake8 and full source/test compileall pass. Preview uses real run() output at normal 30 FPS timing, sampled every third frame. Seed 0 completes in 857 frames (28.6 seconds). Contact sheet inspected; early boss death and radio/combo overlap discovered during preview were fixed and regression-tested.

Independent read-only review: no blocking correctness, lifecycle, rendering, or controller compatibility findings. One cosmetic note remains: the wave-two KEEP LOW! callout accompanies a pylon that is avoided laterally, not vertically. Full repository suite: 1,614 passed, 11 failed, 23 warnings in 216.04 seconds. All 11 failures are the same pre-existing input/event-order test IDs recorded before this work; no new failing IDs and no Star Fox failures. The earlier sequence-sync failure did not recur. Warnings are existing Pillow getdata deprecations. The full suite is not green. An additional simulator smoke command was blocked by a tool safety rule before execution; no hardware verification is claimed.

This Python application has no standalone package build. The previous full-suite run recorded 12 unrelated input/config failures; compare any failures before attributing them to this change.


Coverage: starfox.py 88.5%, starfox_scene.py 100%; 236/243 changed executable lines covered. Uncovered changed lines are moved legacy other-stage rendering and the no-target reticle fallback. No new external I/O, secrets, configuration, or runtime dependencies.

## Publication

Publish as a fast-forward of origin/main, preserving the already-published Pinball commit c2b1842. Use an isolated Git index so the current checkout and staging area stay unchanged. Source hashes match the tested preview.
