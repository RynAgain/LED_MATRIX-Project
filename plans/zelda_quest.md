# Zelda Quest

## Approved scope
Fully autonomous 64x64 forest and temple adventure with original pixel art, sword combat, hearts, key chest, locked gate, guardian, relic, and automatic restart. No controller, ROM, network, or added runtime dependency.

## References
- src/display/dungeon/game.py: seedable state separated from rendering.
- src/display/dungeon/__init__.py: run(matrix, duration=60).
- src/display/_shared.py: stop event and interruptible frame wait.
- src/display/_fonts.py and _utils.py: shared bitmap text.
- tests/test_dungeon.py: seeded progression and rendering tests.
- tests/test_sequence_sync.py: shipped config must contain every registry entry.

## Plan
1. Add state, renderer, and autonomous runner in src/display/zelda_quest.
2. Add registry and short menu label. Append only the enabled Zelda entry to config; preserve all existing changes.
3. Test reachability, AI completion, collision, combat, pickups, gate progression, restart, rendering, duration, stop, and discovery.
4. Run full pytest, flake8, compile checks, and simulator smoke test; inspect visual preview. No standalone build target exists for this Python application.

## Status
- [x] Research and approved plan
- [x] Implementation
- [x] Verification completed with documented existing full-suite input-order failures

## Verified so far
- 118 focused tests pass with 100% statement coverage across state, renderer, and runner.
- 96 permanent seed/frame-rate combinations prove repeated autonomous completion and collision invariants.
- Additional 150 one-minute simulations at 10, 24, and 60 updates/sec each completed three victories.
- Simulated 24-hour unattended run: 4,851 wins, 4,852 runs, minimum two hearts, at most two active pickups; no stuck runs or unbounded state.
- Stress testing exposed healing starvation during guardian combat; low-health AI now collects reachable hearts before attacking.
- Configured flake8 and whole-project compileall pass.
- Independent read-only review found no concrete bugs in autonomous behavior, lifecycle, rendering, or integration.
- Real feature dispatcher plus simulator works with no controller.
- Render plus simulation measured 0.173 ms/frame on the development PC (not a Pi hardware measurement).
- Generated and inspected forest, key chest, guardian, and victory preview; 25-second GIF is in the Aki temporary folder.

## Verification caveats
The full-suite run completed with 1,371 passes and 11 failures in pre-existing input/controller tests. Tests inject fake pygame, but after simulator tests the controller uses an existing simulator window event queue instead. All 25 input tests pass in isolation. Running input tests first and then repeating the full tests directory does not avoid failures in the second pass. No input/controller code was changed; do not claim the full suite is green.

An overlapping focused pytest run caused a config-fixture race and truncated config.json and schedule.json. Both were recovered to their inspected initial contents plus the intended Zelda addition, preserving the existing Skeleton entry. All subsequent pytest runs are serial; sequence tests pass.

## Release
User authorized pushing Zelda Quest to origin/main on 2026-10-06. Commit only Zelda source, tests, documentation, and its registry/menu/config entries. Keep existing Skeleton work and unrelated config edits uncommitted. Existing devices discover and enable the demo through registry sequence synchronization after updating. The installed updater timer checks every 30 minutes; its successful execution on the device is not verified from this development machine.

Do not start the live app updater during verification. Existing Skeleton work and unrelated config edits are out of scope.
