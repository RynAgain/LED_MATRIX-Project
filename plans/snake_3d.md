# Third-person 3D Snake

## Scope and references

Upgrade the existing `snake` feature in place. Keep the 64x64 board rules,
autonomous demo, score/growth, menu registration and quit gesture. No config,
other-game, deployment or dependency changes. Gameplay stays on a flat board,
rendered in 3D from above and behind the head, not a free-flying snake.

Live patterns inspected:
- `src/display/snake.py`: SnakeGame state and demo/interactive lifecycle.
- `src/display/terrain_ball.py:182`: Pillow perspective projection and near-plane rejection.
- `src/display/wireframe.py:91`: cube vertices and faces/edges.
- `src/display/_shared.py:52`: cardinal controller input and shared shutdown helpers.
- `tests/test_playable_games.py:96`: real Snake run path, collision and quit contracts.

## Implementation plan

1. Add `src/display/snake_scene.py`: heading-relative chase camera, clipped
   perspective geometry, shaded solid segments, ground grid, red arena boundary,
   pulsing food and a small overview map so distant/behind-camera food is findable.
   Reuse `_draw_number`, `_lerp_color` and `_scale_color`.
2. Route Snake drawing and death animation through that renderer. Left/right
   turn relative to the snake, once per press (release to rearm). Up/neutral
   continue forward; down cannot reverse. Keep absolute `step(direction)` for
   AI and model tests. Preserve existing uncommitted work byte-for-byte outside
   these targeted edits.
3. Add projection, rendering, movement and real-loop input regressions. Update
   the feature tracker and README with controls and the presentation change.
4. Verify changed-file flake8, full pytest suite, Python compile/import checks
   (this interpreted project has no package/build target), and capture a preview
   from the actual renderer. Report hardware validation separately.

## Status

- Research, plan and implementation complete.
- Changed-file flake8 and full Python compileall passed. Focused playable/Snake: 40 passed; feature-registry/integration/Snake: 159 passed.
- Real-renderer preview: `artifacts/snake_3d_preview.png`; all four orientations: `artifacts/snake_3d_headings.png` (visually inspected).
- Independent read-only review: no critical findings; painter-order corner artifacts, HUD occlusion and Pi frame budget noted as minor/unverified.
- Local renderer timing (120 frames each): 0.29/0.69/1.31 ms per frame at length 3/30/100. Pi hardware timing and device validation pending.
- Initial full-suite result is recorded below; clean main-based release verification passed (see release section).

## Approved follow-up and publication (2026-11-03)

Ryan approved both fixes, verification, then push to main.

1. Minimap: draw food last, including when sharing a coarse cell with the head.
   Food takes that pixel; the heading line still indicates facing. Add overlap
   regressions for head, heading line, body and both food colors.
2. Input: poll at 120 Hz and queue at most two fresh relative turns; consume one
   per 15 Hz movement tick. Retain held-input rearming and stop/quit checks.
   Use monotonic deadlines without a catch-up burst. Very short taps below the
   input polling interval remain hardware-dependent, not guaranteed.
   Patterns: snake.py interactive loop, _shared.read_direction, controller.py
   poll_events/get_direction, tests/test_input.py FakeClock and FakePygame.
3. Verify deterministic timed tests plus the real Controller keyboard path.
   Build a clean candidate from origin/main with only Snake files and its docs;
   do not stage or restore the unrelated dirty working tree. Compile/lint/test
   that candidate and publish via a normal fast-forward push only.

Prior dirty-tree full suite completed: 1,698 passed, 16 failed (11 known input
fixture/event-order failures; 5 scheduling WIP failures). Concurrent old test
runs shared live config fixtures, so this result is not release-candidate proof.
No further concurrent suites against the same checkout. Candidate verification
will use a separate snapshot and valid main config.

Follow-up focused verification: 53 passed; changed-file flake8 and full compileall passed.

## Release verification (2026-11-04)

- Candidate is based on main `26e05c4`, with only six Snake source/test/doc files.
- Full candidate compileall, changed-code flake8 and whitespace checks passed.
- Improved Snake regressions: 43 passed, including 20ms render-cost timing and
  observing the fourth tick to prove a third queued turn is dropped, not delayed.
- 5,000 seeded model steps matched main exactly (AI, score, food, growth,
  collisions and direction). Actual step/draw preview verified food collection
  and two turns; minimap food remains visible over the heading line.
- Full candidate suite runs all modules with `tests/test_input.py` first. This
  avoids the known pre-existing fake-pygame/global simulator singleton ordering
  dependency without skipping tests or changing production input behavior.
  No default-order suite repair is claimed.
- Device installation and Pi timing remain unverified. This is code delivery
  through main; the updater keeps existing device settings and enable flags.
- Final focused playable/Snake run: 55 passed. Coverage: snake_scene.py 100%,
  snake.py 90.8%. Process-local mutations produced the expected six assertion
  failures each for slow input sampling and missing minimap rendering.
- Final independent review: no high/medium production defects. Initial timing
  concern was retracted after checking the pre-render deadline; two test-strength
  requests are covered by the additional timing/overflow regressions above.
- Full isolated main-based suite: 1,715 passed in 322.52 seconds, exit 0
  (input module first, all modules included). Two additional test-only regressions
  were subsequently added; final focused candidate verification covers those.
- Publication approved by Ryan: normal fast-forward push to main, six Snake
  files only. No config, other games, dependencies or generated artifacts.
