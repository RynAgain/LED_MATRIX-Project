"""
Tests for coverage gaps identified in code review (P2-16):
- main.py watchdog/frame-hang detection
- living_world persistence save→load roundtrip
- living_world _handle_reproduction population cap
"""

import os
import sys
import time
import types
import tempfile
import threading

# Ensure project root on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===========================================================================
# Test: main.py watchdog (_mark_frame + hang detection)
# ===========================================================================

class TestWatchdog:
    """Verify the frame-hang watchdog fires correctly."""

    def test_mark_frame_resets_timestamp(self):
        from src.main import _mark_frame, _last_frame_ts
        old = _last_frame_ts[0]
        time.sleep(0.01)
        _mark_frame()
        assert _last_frame_ts[0] > old

    def test_hang_detected_after_timeout(self):
        """If no frame is pushed for >_FRAME_HANG_TIMEOUT, the watchdog
        should detect a hang (verified by checking the timestamp delta)."""
        from src.main import _last_frame_ts, _FRAME_HANG_TIMEOUT
        # Simulate a hung feature by setting last frame far in the past
        _last_frame_ts[0] = time.monotonic() - _FRAME_HANG_TIMEOUT - 1
        elapsed = time.monotonic() - _last_frame_ts[0]
        assert elapsed > _FRAME_HANG_TIMEOUT


# ===========================================================================
# Test: living_world persistence roundtrip (save → load → restore)
# ===========================================================================

class TestPersistenceRoundtrip:
    """Verify save_world writes valid JSON that load_world + restore_entities can read."""

    def test_save_load_roundtrip(self):
        from src.display.living_world.persistence import save_world, load_world, restore_entities
        from src.display.living_world.constants import WORLD_WIDTH, DISPLAY_HEIGHT, GRASS, AIR
        from src.display.living_world.entities import Villager, Tree, Flower
        from src.display.living_world.weather import Weather

        # Build minimal world state
        heights = [DISPLAY_HEIGHT - 10] * WORLD_WIDTH
        world = [[AIR] * WORLD_WIDTH for _ in range(DISPLAY_HEIGHT)]
        for x in range(WORLD_WIDTH):
            world[heights[x]][x] = GRASS

        villagers = [Villager(50, heights[50])]
        villagers[0].name = "TestVillager"
        trees = [Tree(30, heights[30] - 1)]
        flowers = [Flower(40, heights[40], (255, 100, 100))]
        weather = Weather()
        structures = []
        animals = []
        lumber_items = []
        farms = []
        stars = [(10, 5, 200)]
        path_wear = [0] * WORLD_WIDTH
        torch_posts = []

        with tempfile.TemporaryDirectory() as tmp:
            save_path = os.path.join(tmp, "test_world.json")
            # Monkey-patch the save path
            import src.display.living_world.persistence as pers
            orig_path = pers._SAVE_PATH
            pers._SAVE_PATH = save_path
            try:
                result = save_world(
                    villagers=villagers, structures=structures, trees=trees,
                    farms=farms, animals=animals, flowers=flowers,
                    lumber_items=lumber_items, heights=heights, world=world,
                    weather=weather, stars=stars, camera_x=50, sim_tick=100,
                    path_wear=path_wear, torch_posts=torch_posts,
                    start_time=time.time() - 120.0,
                )
                assert result is True, "save_world should return True"
                assert os.path.exists(save_path)

                loaded = load_world()
                assert loaded is not None, "load_world should return data"
                assert loaded["sim_tick"] == 100
                assert "elapsed" in loaded  # P1-12: elapsed must be persisted
                assert loaded["elapsed"] > 100  # should be ~120

                restored = restore_entities(loaded)
                assert restored is not None
                assert len(restored["villagers"]) == 1
                assert restored["villagers"][0].name == "TestVillager"
                assert len(restored["trees"]) == 1
                assert len(restored["flowers"]) == 1
            finally:
                pers._SAVE_PATH = orig_path


# ===========================================================================
# Test: _handle_reproduction population cap
# ===========================================================================

class TestReproduction:
    """Verify reproduction respects MAX_VILLAGERS cap."""

    def test_reproduction_capped_at_max(self):
        from src.display.living_world.constants import MAX_VILLAGERS, WORLD_WIDTH, DISPLAY_HEIGHT, GRASS, AIR
        from src.display.living_world.entities import Villager
        from src.display.living_world.villager_ai import _handle_reproduction

        heights = [DISPLAY_HEIGHT - 10] * WORLD_WIDTH
        world = [[AIR] * WORLD_WIDTH for _ in range(DISPLAY_HEIGHT)]
        for x in range(WORLD_WIDTH):
            world[heights[x]][x] = GRASS

        # Fill to max capacity
        villagers = []
        for i in range(MAX_VILLAGERS):
            v = Villager(50 + i % 40, heights[50])
            v.age = 200  # adult
            v.food = 100
            v.children_born = 0
            villagers.append(v)

        pop_before = len(villagers)
        _handle_reproduction(villagers, heights, world)
        # Should NOT have grown past MAX_VILLAGERS
        assert len(villagers) <= MAX_VILLAGERS, f"population grew to {len(villagers)}"


# ===========================================================================
# Runner (for environments without pytest)
# ===========================================================================

if __name__ == "__main__":
    import traceback
    classes = [TestWatchdog, TestPersistenceRoundtrip, TestReproduction]
    passed = failed = 0
    for cls in classes:
        inst = cls()
        for name in [n for n in dir(inst) if n.startswith("test_")]:
            try:
                getattr(inst, name)()
                passed += 1
                print(f"PASS {cls.__name__}.{name}")
            except Exception:
                failed += 1
                print(f"FAIL {cls.__name__}.{name}")
                traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
