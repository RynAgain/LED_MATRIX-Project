"""
Unit tests for the data-driven menu system (src/menu/, Phase 3 + Settings).

These tests are **headless-safe** (SDL dummy drivers via conftest's autouse
fixture) and need **no physical controller**. They drive :class:`MenuSystem` and
:class:`SettingsScreen` with a scripted fake controller (reusing the pattern from
``tests/test_app_state.py`` / ``tests/test_input.py``) and a fake matrix that
captures ``SetImage`` calls and brightness.

Covered:

* UP/DOWN move selection, including REPEAT auto-scroll and wrap-around.
* A enters the Games submenu; selecting a game returns ``MenuResult.launch_game``.
* B pops the submenu then resumes at the root; START resumes from anywhere.
* Quit gesture (START+SELECT held) -> ``MenuResult.quit`` / resume semantics.
* Scrolling viewport when item count exceeds the visible rows.
* Settings: LEFT/RIGHT adjust brightness within the clamp range, A/B confirm,
  the value is persisted to a temp ``config.json`` **atomically**, and brightness
  is applied live to the fake matrix.
"""

import json
import os

import pytest

# Ensure dummy SDL drivers even if this module is imported directly.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from src.app_state import MenuResultKind, PLAYABLE_GAMES
from src.display import _shared
from src.feature_registry import FEATURE_MODULES
from src.input import Button, EventType, InputEvent
from src.menu import MenuSystem
from src.menu.carousel_screen import CarouselScreen
from src.menu.menu_data import (
    MENU_DEMOS,
    ItemAction,
    build_demos_menu,
    build_games_menu,
    build_main_menu,
    build_menu_registry,
)
from src.menu.settings_screen import (
    BRIGHTNESS_MAX,
    BRIGHTNESS_MIN,
    SettingsScreen,
    load_settings,
    save_settings,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeMatrix:
    """Minimal matrix stand-in: records SetImage calls and brightness."""

    def __init__(self):
        self.images = []
        self.brightness = 80

    def SetImage(self, image, *a, **kw):
        self.images.append(image)

    def Clear(self):
        pass


class FakeController:
    """Scripted controller.

    ``event_script`` is a list of "batches"; each :meth:`poll_events` call pops
    and returns the next batch, then ``[]`` forever. ``held`` is the set of
    currently-held logical buttons (drives ``is_pressed`` and thus ``wants_quit``).
    """

    def __init__(self, event_script=None, held=None, quitting=False):
        self._script = list(event_script or [])
        self._held = set(held or set())
        self._quitting = quitting
        self.poll_count = 0

    def poll_events(self):
        self.poll_count += 1
        if self._script:
            return self._script.pop(0)
        return []

    def is_pressed(self, button):
        return button in self._held

    def is_connected(self):
        return True

    def is_quitting(self):
        return self._quitting

    def start_hold_seconds(self):
        return 0.0


def _press(button):
    """A one-batch event script entry: a single PRESSED event."""
    return [InputEvent(button, EventType.PRESSED, 0.0)]


def _repeat(button):
    """A one-batch event script entry: a single REPEAT event."""
    return [InputEvent(button, EventType.REPEAT, 0.0)]


@pytest.fixture(autouse=True)
def _clear_shared_stop():
    """Reset the global _shared stop flag around every test."""
    _shared.clear_stop()
    yield
    _shared.clear_stop()


@pytest.fixture
def config():
    return {
        "display_duration": 30,
        "matrix_hardware": {"brightness": 50, "rows": 64, "cols": 64},
        "sequence": [{"name": "snake", "type": "game", "enabled": True}],
    }


def _make_menu(config=None, **kw):
    """Build a MenuSystem with no frame sleep (fps=0) for fast tests."""
    return MenuSystem(config or {}, fps=0, **kw)


# ---------------------------------------------------------------------------
# menu_data: structure + extensibility
# ---------------------------------------------------------------------------
class TestMenuData:
    def test_main_menu_structure(self):
        menu = build_main_menu()
        labels = [i.label for i in menu.items]
        assert labels == ["GAMES", "DEMOS", "CAROUSEL", "CONTROLS", "SETTINGS", "RESUME"]
        actions = [i.action for i in menu.items]
        assert actions == [
            ItemAction.OPEN_SUBMENU,
            ItemAction.OPEN_SUBMENU,
            ItemAction.OPEN_CAROUSEL,
            ItemAction.OPEN_CONTROLS,
            ItemAction.OPEN_SETTINGS,
            ItemAction.RESUME_IDLE,
        ]

    def test_games_menu_from_playable(self):
        menu = build_games_menu()
        game_items = [i for i in menu.items if i.action is ItemAction.LAUNCH_GAME]
        names = {i.payload for i in game_items}
        # Every playable game appears exactly once.
        assert names == set(PLAYABLE_GAMES)
        # Each carries its feature name as payload.
        for item in game_items:
            assert item.payload in PLAYABLE_GAMES
        # A Back item is appended.
        assert menu.items[-1].action is ItemAction.BACK

    def test_games_menu_is_data_driven(self):
        """Adding a game to the playable set adds a row -- no engine edit."""
        menu = build_games_menu(playable={"snake", "tetris", "pong", "breakout"})
        names = {i.payload for i in menu.items if i.action is ItemAction.LAUNCH_GAME}
        assert "breakout" in names

    def test_registry_resolves_games(self):
        reg = build_menu_registry()
        from src.menu.menu_data import MENU_GAMES
        assert MENU_GAMES in reg


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
class TestNavigation:
    def test_down_moves_selection(self, config):
        menu = _make_menu(config)
        # DOWN once, then START to resume (so run() terminates deterministically).
        ctrl = FakeController(event_script=[_press(Button.DOWN), _press(Button.START)])
        matrix = FakeMatrix()
        result = menu.run(matrix, ctrl)
        assert result.kind is MenuResultKind.RESUME
        # Renders happened (initial + after move).
        assert len(matrix.images) >= 2

    def test_up_wraps_to_bottom(self, config):
        """UP from the first item wraps to the last (RESUME)."""
        menu = _make_menu(config)
        # UP wraps selection to last item ("RESUME"); A then activates it.
        ctrl = FakeController(event_script=[_press(Button.UP), _press(Button.A)])
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.RESUME

    def test_repeat_autoscroll_moves_selection(self, config):
        """A REPEAT DOWN event also advances the cursor (held auto-scroll)."""
        menu = _make_menu(config)
        # REPEAT DOWN x5 lands on RESUME (idx 5); A activates it.
        # Main menu: GAMES(0), DEMOS(1), CAROUSEL(2), CONTROLS(3), SETTINGS(4), RESUME(5)
        ctrl = FakeController(event_script=[
            _repeat(Button.DOWN), _repeat(Button.DOWN),
            _repeat(Button.DOWN), _repeat(Button.DOWN),
            _repeat(Button.DOWN),
            _press(Button.A),
        ])
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.RESUME

    def test_a_enters_games_submenu_then_launch(self, config):
        """A on GAMES pushes the submenu; A on first game launches it."""
        menu = _make_menu(config)
        # Main: GAMES selected (idx 0) -> A pushes Games submenu.
        # Games submenu first item is SNAKE -> A launches it.
        ctrl = FakeController(event_script=[
            _press(Button.A),  # enter Games
            _press(Button.A),  # launch first game
        ])
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.LAUNCH_GAME
        assert result.payload in PLAYABLE_GAMES
        # With stable ordering, snake is first.
        assert result.payload == "snake"

    def test_launch_specific_game(self, config):
        """Navigate to TETRIS in the Games submenu and launch it."""
        menu = _make_menu(config)
        ctrl = FakeController(event_script=[
            _press(Button.A),     # enter Games (snake idx0, tetris idx1, pong idx2)
            _press(Button.DOWN),  # -> tetris
            _press(Button.A),     # launch
        ])
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.LAUNCH_GAME
        assert result.payload == "tetris"

    def test_b_pops_submenu_then_resumes_at_root(self, config):
        """B in a submenu pops to root; B again at root resumes to idle."""
        menu = _make_menu(config)
        ctrl = FakeController(event_script=[
            _press(Button.A),  # enter Games submenu
            _press(Button.B),  # pop back to Main Menu (does NOT resume)
            _press(Button.B),  # at root -> resume
        ])
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.RESUME

    def test_b_in_submenu_does_not_resume(self, config):
        """A single B inside a submenu must pop, not return to idle."""
        menu = _make_menu(config)
        ctrl = FakeController(event_script=[
            _press(Button.A),      # enter Games
            _press(Button.B),      # pop to Main (stack now just root)
            _press(Button.START),  # explicit resume to end the loop
        ])
        result = menu.run(FakeMatrix(), ctrl)
        # We reached resume only via START, proving the first B did not resume.
        assert result.kind is MenuResultKind.RESUME
        assert len(menu._stack) == 1  # back at the root

    def test_start_resumes_from_submenu(self, config):
        """START resumes to idle from anywhere, including a submenu."""
        menu = _make_menu(config)
        ctrl = FakeController(event_script=[
            _press(Button.A),      # enter Games
            _press(Button.START),  # resume from inside the submenu
        ])
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.RESUME

    def test_resume_item_returns_resume(self, config):
        """Selecting the RESUME item returns MenuResult.resume()."""
        menu = _make_menu(config)
        # Main menu: GAMES(0), DEMOS(1), CAROUSEL(2), CONTROLS(3), SETTINGS(4), RESUME(5)
        ctrl = FakeController(event_script=[
            _press(Button.DOWN),  # DEMOS
            _press(Button.DOWN),  # CAROUSEL
            _press(Button.DOWN),  # CONTROLS
            _press(Button.DOWN),  # SETTINGS
            _press(Button.DOWN),  # RESUME
            _press(Button.A),
        ])
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.RESUME

    def test_quit_window_close(self, config):
        menu = _make_menu(config)
        ctrl = FakeController(quitting=True)
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.QUIT

    def test_quit_gesture_resumes(self, config):
        """START+SELECT held (wants_quit) backs the menu out to idle."""
        menu = _make_menu(config)
        ctrl = FakeController(held={Button.START, Button.SELECT})
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.RESUME

    def test_should_stop_resumes(self, config):
        menu = _make_menu(config)
        ctrl = FakeController()
        _shared.request_stop()
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.RESUME


# ---------------------------------------------------------------------------
# Scrolling / viewport
# ---------------------------------------------------------------------------
class TestScrolling:
    def test_viewport_clamps_to_window(self):
        from src.menu.menu_system import VISIBLE_ROWS, MenuSystem as MS

        count = VISIBLE_ROWS + 5
        # Selection at top -> window starts at 0.
        first, last = MS._viewport(count, 0)
        assert first == 0
        assert last - first == VISIBLE_ROWS
        # Selection at bottom -> window ends at count.
        first, last = MS._viewport(count, count - 1)
        assert last == count
        assert last - first == VISIBLE_ROWS
        # Small lists show everything.
        first, last = MS._viewport(3, 1)
        assert (first, last) == (0, 3)

    def test_scroll_follows_selection_with_many_items(self):
        """A menu with more items than fit scrolls the viewport with the cursor."""
        from src.menu.menu_data import Menu, MenuItem
        from src.menu.menu_system import VISIBLE_ROWS

        many = Menu(
            "big", "BIG",
            [MenuItem(f"ITEM{i}", ItemAction.RESUME_IDLE) for i in range(12)],
        )
        menu = _make_menu({})
        # Inject the big menu as the root.
        menu._stack = [[many, 0]]
        matrix = FakeMatrix()
        menu._render(matrix)
        assert matrix.images, "render produced an image"

        # Move down past the visible window; viewport must follow.
        for _ in range(VISIBLE_ROWS + 2):
            menu._move_selection(+1)
        first, last = menu._viewport(len(many.items), menu._selected)
        assert first <= menu._selected < last
        assert first > 0  # we have scrolled


# ---------------------------------------------------------------------------
# Settings: persistence + live brightness
# ---------------------------------------------------------------------------
class TestSettingsPersistence:
    def test_save_settings_atomic_and_preserves_keys(self, tmp_path):
        """save_settings merges into existing JSON without clobbering siblings."""
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps({
            "display_duration": 30,
            "log_level": "DEBUG",
            "matrix_hardware": {"brightness": 50, "rows": 64, "gpio_slowdown": 4},
            "sequence": [{"name": "snake", "enabled": True}],
        }))

        ok = save_settings(str(cfg_path), {
            "display_duration": 90,
            "matrix_hardware": {"brightness": 75},
        })
        assert ok

        data = json.loads(cfg_path.read_text())
        # Touched keys updated.
        assert data["display_duration"] == 90
        assert data["matrix_hardware"]["brightness"] == 75
        # Sibling keys preserved (deep merge, not overwrite).
        assert data["log_level"] == "DEBUG"
        assert data["matrix_hardware"]["rows"] == 64
        assert data["matrix_hardware"]["gpio_slowdown"] == 4
        assert data["sequence"] == [{"name": "snake", "enabled": True}]
        # No stray temp files left behind.
        leftovers = list(tmp_path.glob("*.tmp"))
        assert not leftovers

    def test_load_settings_missing_returns_empty(self, tmp_path):
        assert load_settings(str(tmp_path / "nope.json")) == {}

    def test_brightness_clamped_to_range(self, config, tmp_path):
        """LEFT below min / RIGHT above max clamps to the configured range."""
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config))

        matrix = FakeMatrix()
        screen = SettingsScreen(matrix, config=dict(config),
                                config_path=str(cfg_path), fps=0)
        bright = screen.settings[0]
        assert bright.label == "BRIGHT"
        # Drive far below minimum.
        for _ in range(100):
            bright.adjust(-1)
        assert bright.value == BRIGHTNESS_MIN
        # Drive far above maximum.
        for _ in range(100):
            bright.adjust(+1)
        assert bright.value == BRIGHTNESS_MAX

    def test_settings_adjust_persists_and_applies_live(self, config, tmp_path):
        """RIGHT raises brightness (live on matrix), B persists atomically."""
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config))

        baseline = config["matrix_hardware"]["brightness"]
        matrix = FakeMatrix()
        matrix.brightness = baseline
        screen = SettingsScreen(matrix, config=json.loads(json.dumps(config)),
                                config_path=str(cfg_path), fps=0)

        # BRIGHT is selected first. RIGHT (PRESSED) raises by one step, then B
        # exits and persists.
        ctrl = FakeController(event_script=[
            _press(Button.RIGHT),
            _press(Button.B),
        ])
        screen.attach_controller(ctrl)
        screen.run()

        expected = baseline + 5
        # Applied live to the matrix immediately.
        assert matrix.brightness == expected
        # Persisted atomically to config.json.
        data = json.loads(cfg_path.read_text())
        assert data["matrix_hardware"]["brightness"] == expected
        # Other keys untouched.
        assert data["display_duration"] == config["display_duration"]

    def test_settings_repeat_adjusts(self, config, tmp_path):
        """A REPEAT RIGHT event also adjusts the value (held auto-repeat)."""
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config))

        baseline = config["matrix_hardware"]["brightness"]
        matrix = FakeMatrix()
        matrix.brightness = baseline
        screen = SettingsScreen(matrix, config=json.loads(json.dumps(config)),
                                config_path=str(cfg_path), fps=0)
        ctrl = FakeController(event_script=[
            _repeat(Button.RIGHT),
            _repeat(Button.RIGHT),
            _press(Button.B),
        ])
        screen.attach_controller(ctrl)
        screen.run()
        assert matrix.brightness == baseline + 10

    def test_settings_duration_adjust_persists(self, config, tmp_path):
        """DOWN to DEMO duration, LEFT decrements, B persists."""
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config))

        screen = SettingsScreen(FakeMatrix(), config=dict(config),
                                config_path=str(cfg_path), fps=0)
        ctrl = FakeController(event_script=[
            _press(Button.DOWN),   # focus DEMO duration
            _press(Button.LEFT),   # -5s
            _press(Button.A),      # persist (stay)
            _press(Button.B),      # back
        ])
        screen.attach_controller(ctrl)
        screen.run()
        data = json.loads(cfg_path.read_text())
        assert data["display_duration"] == config["display_duration"] - 5

    def test_settings_no_change_no_write(self, config, tmp_path):
        """If nothing is adjusted, B exits without rewriting the file."""
        cfg_path = tmp_path / "config.json"
        original = json.dumps(config)
        cfg_path.write_text(original)
        mtime = os.path.getmtime(cfg_path)

        screen = SettingsScreen(FakeMatrix(), config=dict(config),
                                config_path=str(cfg_path), fps=0)
        ctrl = FakeController(event_script=[_press(Button.B)])
        screen.attach_controller(ctrl)
        screen.run()
        # _dirty stayed False -> file content unchanged.
        assert cfg_path.read_text() == original


# ---------------------------------------------------------------------------
# Settings reached inline through the menu
# ---------------------------------------------------------------------------
class TestSettingsInline:
    def test_open_settings_inline_then_resume(self, config, tmp_path):
        """A on SETTINGS opens the inline screen; adjusting + back returns to the
        menu (NOT to the state machine), and we can still resume afterward."""
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config))

        baseline = config["matrix_hardware"]["brightness"]
        menu = MenuSystem(json.loads(json.dumps(config)),
                          config_path=str(cfg_path), fps=0)
        matrix = FakeMatrix()
        matrix.brightness = baseline

        # Main: GAMES(0), DEMOS(1), CAROUSEL(2), CONTROLS(3), SETTINGS(4), RESUME(5).
        ctrl = FakeController(event_script=[
            _press(Button.DOWN),   # -> DEMOS
            _press(Button.DOWN),   # -> CAROUSEL
            _press(Button.DOWN),   # -> CONTROLS
            _press(Button.DOWN),   # -> SETTINGS
            _press(Button.A),      # open inline settings (screen.run starts)
            _press(Button.RIGHT),  # brightness +5 (consumed by settings screen)
            _press(Button.B),      # back out of settings -> returns to menu
            _press(Button.START),  # resume to idle from the menu
        ])
        result = menu.run(matrix, ctrl)

        assert result.kind is MenuResultKind.RESUME
        # Brightness change applied + persisted via the inline screen.
        assert matrix.brightness == baseline + 5
        data = json.loads(cfg_path.read_text())
        assert data["matrix_hardware"]["brightness"] == baseline + 5


# ---------------------------------------------------------------------------
# Demos submenu
# ---------------------------------------------------------------------------
class TestDemosSubmenu:
    def test_demos_menu_lists_all_features(self):
        """build_demos_menu() includes every feature from the registry."""
        menu = build_demos_menu()
        demo_items = [i for i in menu.items if i.action is ItemAction.LAUNCH_DEMO]
        payloads = {i.payload for i in demo_items}
        # Every feature in the registry should appear.
        assert payloads == set(FEATURE_MODULES.keys())
        # A BACK item is appended.
        assert menu.items[-1].action is ItemAction.BACK

    def test_demos_menu_in_registry(self):
        """The demos submenu is in the menu registry."""
        reg = build_menu_registry()
        assert MENU_DEMOS in reg
        assert reg[MENU_DEMOS].id == MENU_DEMOS

    def test_navigate_into_demos_submenu(self, config):
        """A on DEMOS (idx 1) pushes the demos submenu."""
        menu = _make_menu(config)
        # Main: GAMES(0), DEMOS(1) -> A enters demos submenu.
        # Then B pops back, START resumes.
        ctrl = FakeController(event_script=[
            _press(Button.DOWN),  # -> DEMOS
            _press(Button.A),     # enter Demos submenu
            _press(Button.B),     # pop back to Main
            _press(Button.START), # resume
        ])
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.RESUME

    def test_select_demo_returns_launch_demo(self, config):
        """Selecting a demo in the Demos submenu returns LAUNCH_DEMO."""
        menu = _make_menu(config)
        # Main: GAMES(0), DEMOS(1) -> A enters demos submenu.
        # First item in demos submenu is the first feature alphabetically.
        ctrl = FakeController(event_script=[
            _press(Button.DOWN),  # -> DEMOS
            _press(Button.A),     # enter Demos submenu
            _press(Button.A),     # select first demo
        ])
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.LAUNCH_DEMO
        # Payload is a valid feature name.
        assert result.payload in FEATURE_MODULES


# ---------------------------------------------------------------------------
# Carousel screen: toggle + persist
# ---------------------------------------------------------------------------
class TestCarouselScreen:
    def test_carousel_toggle_and_persist(self, tmp_path):
        """A toggles a feature's enabled state; B saves to config.json."""
        cfg = {
            "display_duration": 30,
            "matrix_hardware": {"brightness": 50},
            "sequence": [
                {"name": "fire", "type": "effect", "enabled": True},
                {"name": "plasma", "type": "effect", "enabled": False},
                {"name": "snake", "type": "game", "enabled": True},
            ],
        }
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(cfg))

        matrix = FakeMatrix()
        screen = CarouselScreen(matrix, config=json.loads(json.dumps(cfg)),
                                config_path=str(cfg_path), fps=0)
        # First item is "fire" (enabled=True). A toggles it OFF.
        ctrl = FakeController(event_script=[
            _press(Button.A),  # toggle fire -> OFF
            _press(Button.B),  # save and exit
        ])
        screen.attach_controller(ctrl)
        screen.run()

        data = json.loads(cfg_path.read_text())
        assert data["sequence"][0]["enabled"] is False  # fire toggled OFF
        assert data["sequence"][1]["enabled"] is False  # plasma unchanged
        assert data["sequence"][2]["enabled"] is True   # snake unchanged

    def test_carousel_toggle_multiple(self, tmp_path):
        """Multiple toggles work correctly."""
        cfg = {
            "sequence": [
                {"name": "fire", "type": "effect", "enabled": True},
                {"name": "plasma", "type": "effect", "enabled": False},
            ],
        }
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(cfg))

        screen = CarouselScreen(FakeMatrix(), config=json.loads(json.dumps(cfg)),
                                config_path=str(cfg_path), fps=0)
        # Toggle fire OFF, move down, toggle plasma ON, then save.
        ctrl = FakeController(event_script=[
            _press(Button.A),     # toggle fire -> OFF
            _press(Button.DOWN),  # -> plasma
            _press(Button.A),     # toggle plasma -> ON
            _press(Button.B),     # save and exit
        ])
        screen.attach_controller(ctrl)
        screen.run()

        data = json.loads(cfg_path.read_text())
        assert data["sequence"][0]["enabled"] is False  # fire toggled OFF
        assert data["sequence"][1]["enabled"] is True   # plasma toggled ON

    def test_carousel_no_change_no_write(self, tmp_path):
        """If nothing is toggled, B exits without rewriting the file."""
        cfg = {
            "sequence": [
                {"name": "fire", "type": "effect", "enabled": True},
            ],
        }
        original = json.dumps(cfg)
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(original)

        screen = CarouselScreen(FakeMatrix(), config=json.loads(original),
                                config_path=str(cfg_path), fps=0)
        ctrl = FakeController(event_script=[_press(Button.B)])
        screen.attach_controller(ctrl)
        screen.run()
        # File content unchanged.
        assert cfg_path.read_text() == original

    def test_carousel_preserves_other_config_keys(self, tmp_path):
        """Persisting carousel changes does not clobber other config keys."""
        cfg = {
            "display_duration": 99,
            "log_level": "DEBUG",
            "matrix_hardware": {"brightness": 75},
            "sequence": [
                {"name": "fire", "type": "effect", "enabled": True, "duration": 45},
            ],
        }
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(cfg))

        screen = CarouselScreen(FakeMatrix(), config=json.loads(json.dumps(cfg)),
                                config_path=str(cfg_path), fps=0)
        ctrl = FakeController(event_script=[
            _press(Button.A),  # toggle fire -> OFF
            _press(Button.B),  # save
        ])
        screen.attach_controller(ctrl)
        screen.run()

        data = json.loads(cfg_path.read_text())
        # Toggled field changed.
        assert data["sequence"][0]["enabled"] is False
        # Other fields preserved.
        assert data["display_duration"] == 99
        assert data["log_level"] == "DEBUG"
        assert data["matrix_hardware"]["brightness"] == 75
        assert data["sequence"][0]["duration"] == 45
        assert data["sequence"][0]["type"] == "effect"

    def test_carousel_inline_from_menu(self, config, tmp_path):
        """A on CAROUSEL (idx 2) opens the inline carousel screen."""
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config))

        menu = MenuSystem(json.loads(json.dumps(config)),
                          config_path=str(cfg_path), fps=0)
        matrix = FakeMatrix()

        # Main: GAMES(0), DEMOS(1), CAROUSEL(2), CONTROLS(3), SETTINGS(4), RESUME(5).
        ctrl = FakeController(event_script=[
            _press(Button.DOWN),   # -> DEMOS
            _press(Button.DOWN),   # -> CAROUSEL
            _press(Button.A),      # open carousel screen
            _press(Button.B),      # back out of carousel -> returns to menu
            _press(Button.START),  # resume to idle from the menu
        ])
        result = menu.run(matrix, ctrl)
        assert result.kind is MenuResultKind.RESUME


# ---------------------------------------------------------------------------
# Controller mapping screen: toggle invert_y + persist
# ---------------------------------------------------------------------------
class TestControllerScreen:
    def test_toggle_invert_y_and_persist(self, tmp_path):
        """A on INVERT Y toggles the value; B saves to controller.json."""
        ctrl_cfg = {
            "buttons": {"2": "A", "3": "B", "9": "START", "6": "SELECT"},
            "hat_index": 0,
            "axis_x": 0,
            "axis_y": 1,
            "invert_y": False,
            "deadzone": 0.5,
        }
        cfg_path = tmp_path / "controller.json"
        cfg_path.write_text(json.dumps(ctrl_cfg))

        from src.menu.controller_screen import ControllerScreen

        matrix = FakeMatrix()
        # Navigate: DOWN x4 to reach INVERT Y (idx 4), A to toggle, B to save.
        ctrl = FakeController(event_script=[
            _press(Button.DOWN),  # REMAP B
            _press(Button.DOWN),  # REMAP START
            _press(Button.DOWN),  # REMAP SELECT
            _press(Button.DOWN),  # INVERT Y
            _press(Button.A),     # toggle -> True
            _press(Button.B),     # save and exit
        ])
        screen = ControllerScreen(matrix, controller=ctrl,
                                  config_path=str(cfg_path), fps=0)
        screen.run()

        data = json.loads(cfg_path.read_text())
        assert data["invert_y"] is True

    def test_toggle_invert_y_twice(self, tmp_path):
        """Toggling invert_y twice returns to original value."""
        ctrl_cfg = {
            "buttons": {"2": "A", "3": "B", "9": "START", "6": "SELECT"},
            "hat_index": 0,
            "axis_x": 0,
            "axis_y": 1,
            "invert_y": True,
            "deadzone": 0.5,
        }
        cfg_path = tmp_path / "controller.json"
        cfg_path.write_text(json.dumps(ctrl_cfg))

        from src.menu.controller_screen import ControllerScreen

        matrix = FakeMatrix()
        ctrl = FakeController(event_script=[
            _press(Button.DOWN),  # REMAP B
            _press(Button.DOWN),  # REMAP START
            _press(Button.DOWN),  # REMAP SELECT
            _press(Button.DOWN),  # INVERT Y
            _press(Button.A),     # toggle -> False
            _press(Button.A),     # toggle -> True again
            _press(Button.B),     # save and exit
        ])
        screen = ControllerScreen(matrix, controller=ctrl,
                                  config_path=str(cfg_path), fps=0)
        screen.run()

        data = json.loads(cfg_path.read_text())
        assert data["invert_y"] is True

    def test_save_and_back_item(self, tmp_path):
        """Selecting SAVE+BACK persists and exits."""
        ctrl_cfg = {
            "buttons": {"2": "A", "3": "B", "9": "START", "6": "SELECT"},
            "hat_index": 0,
            "axis_x": 0,
            "axis_y": 1,
            "invert_y": False,
            "deadzone": 0.5,
        }
        cfg_path = tmp_path / "controller.json"
        cfg_path.write_text(json.dumps(ctrl_cfg))

        from src.menu.controller_screen import ControllerScreen

        matrix = FakeMatrix()
        # Navigate to INVERT Y, toggle, then DOWN to SAVE+BACK, A to activate.
        ctrl = FakeController(event_script=[
            _press(Button.DOWN),  # REMAP B
            _press(Button.DOWN),  # REMAP START
            _press(Button.DOWN),  # REMAP SELECT
            _press(Button.DOWN),  # INVERT Y
            _press(Button.A),     # toggle -> True
            _press(Button.DOWN),  # SAVE+BACK
            _press(Button.A),     # activate save+back
        ])
        screen = ControllerScreen(matrix, controller=ctrl,
                                  config_path=str(cfg_path), fps=0)
        screen.run()

        data = json.loads(cfg_path.read_text())
        assert data["invert_y"] is True

    def test_no_change_no_write(self, tmp_path):
        """If nothing is changed, B exits without rewriting the file."""
        ctrl_cfg = {
            "buttons": {"2": "A", "3": "B", "9": "START", "6": "SELECT"},
            "hat_index": 0,
            "axis_x": 0,
            "axis_y": 1,
            "invert_y": False,
            "deadzone": 0.5,
        }
        original = json.dumps(ctrl_cfg)
        cfg_path = tmp_path / "controller.json"
        cfg_path.write_text(original)

        from src.menu.controller_screen import ControllerScreen

        matrix = FakeMatrix()
        ctrl = FakeController(event_script=[_press(Button.B)])
        screen = ControllerScreen(matrix, controller=ctrl,
                                  config_path=str(cfg_path), fps=0)
        screen.run()

        # File content unchanged (no write when not dirty).
        assert json.loads(cfg_path.read_text()) == ctrl_cfg

    def test_controls_inline_from_menu(self, config, tmp_path):
        """A on CONTROLS (idx 3) opens the inline controller screen."""
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(config))

        menu = MenuSystem(json.loads(json.dumps(config)),
                          config_path=str(cfg_path), fps=0)
        matrix = FakeMatrix()

        # Main: GAMES(0), DEMOS(1), CAROUSEL(2), CONTROLS(3), SETTINGS(4), RESUME(5).
        ctrl = FakeController(event_script=[
            _press(Button.DOWN),   # -> DEMOS
            _press(Button.DOWN),   # -> CAROUSEL
            _press(Button.DOWN),   # -> CONTROLS
            _press(Button.A),      # open controller screen
            _press(Button.B),      # back out of controls -> returns to menu
            _press(Button.START),  # resume to idle from the menu
        ])
        result = menu.run(matrix, ctrl)
        assert result.kind is MenuResultKind.RESUME
