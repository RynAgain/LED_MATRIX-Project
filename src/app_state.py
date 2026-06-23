#!/usr/bin/env python3
"""
Application state machine (Phase 2 of the controller-UI overhaul).

This module implements the top-level :class:`AppStateMachine` that replaces the
inline ``while not _shutdown`` loop in :func:`src.main.main`. Control flows
from a USB gamepad (or keyboard fallback) through :class:`src.input.Controller`
rather than the old (removed) file-polling web-command watcher.

State model (CONTROLLER_OVERHAUL.md §3)
---------------------------------------
* :class:`AppMode` -- the three top-level states implemented in this phase
  (``IDLE``, ``MENU``, ``IN_GAME``). ``SETTINGS`` from the design is modeled as a
  *pushed menu screen* handled inside the (real) menu in Phase 3, so it is **not**
  a distinct top-level mode here -- it is a clean extension point: the menu
  returns a :class:`MenuResult` of kind :data:`MenuResultKind.OPEN_SETTINGS` and
  the state machine treats it as "stay in MENU" for now.
* :class:`DemoCarousel` -- the idle demo feature-cycling logic extracted verbatim
  (by *delegation*, not duplication) from ``src/main.py``. It reuses
  ``run_feature``, ``_check_internet``, ``_check_schedule``, ``load_config`` and
  the ``_shared`` stop mechanism so the idle behavior is byte-for-byte what it is
  today, plus a single new exit condition: a ``menu_requested`` callback that
  lets a START press break the carousel into MENU within a frame.
* :class:`AppStateMachine` -- owns the matrix + controller + config and drives
  the transition table.

Menu seam for Phase 3 (CONTROLLER_OVERHAUL.md §4)
-------------------------------------------------
The real menu UI does not exist yet. To make the state machine testable now and
to give Phase 3 a trivial swap-in point, we define a small protocol
:class:`MenuController` and a result type :class:`MenuResult`. A
:class:`PlaceholderMenu` implements the protocol minimally. Phase 3 replaces the
placeholder with ``src/menu/`` by passing ``AppStateMachine(menu=RealMenu(...))``;
no state-machine changes are required.

pygame event-queue / QUIT coexistence
--------------------------------------
The :class:`src.input.Controller` is the single owner of ``pygame.event.get()``
(see its module docstring). The state machine observes window-close via
``controller.is_quitting()`` instead of letting the simulator independently drain
``QUIT``. All running display features still call ``matrix.SetImage``; controller
polling happens in the state-machine loops *around* them (and, during a demo, in
a background input thread that calls ``request_stop()``).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

try:  # Python 3.8+ has typing.Protocol; fall back gracefully if ever absent.
    from typing import Protocol
except ImportError:  # pragma: no cover - all supported versions have Protocol
    Protocol = object  # type: ignore

from src.display._shared import request_stop, clear_stop, should_stop
from src.input import Button, EventType, wants_quit

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Top-level modes (CONTROLLER_OVERHAUL.md §3.1)
# ---------------------------------------------------------------------------
class AppMode(Enum):
    """Top-level application states driven by :class:`AppStateMachine`.

    ``SETTINGS`` from the design spec is intentionally *not* a member here: it is
    a sub-screen pushed inside the menu (Phase 3) and surfaces to the state
    machine only as a :class:`MenuResult`. Keeping it out of this enum is the
    clean extension point the spec asks for -- adding settings logic later does
    not require touching the top-level state set.
    """

    IDLE = "IDLE"        # demo carousel (current default behavior)
    MENU = "MENU"        # on-matrix menu navigation
    IN_GAME = "IN_GAME"  # playable game running with the controller


# ---------------------------------------------------------------------------
# Playable games (CONTROLLER_OVERHAUL.md §4.2). Single source of truth for which
# features the menu may launch interactively. Adding a game later is one line.
# ---------------------------------------------------------------------------
PLAYABLE_GAMES = {"snake", "tetris", "pong", "starfox", "barricade"}


# ---------------------------------------------------------------------------
# Menu seam for Phase 3 (CONTROLLER_OVERHAUL.md §4.4)
# ---------------------------------------------------------------------------
class MenuResultKind(Enum):
    """What the menu decided the app should do after the menu loop returns."""

    RESUME = "RESUME"              # back to the demo carousel (IDLE)
    LAUNCH_GAME = "LAUNCH_GAME"    # enter IN_GAME with payload = feature name
    LAUNCH_DEMO = "LAUNCH_DEMO"    # run a feature as demo (no controller) then return to MENU
    OPEN_SETTINGS = "OPEN_SETTINGS"  # deferred to Phase 3/4; stay in MENU for now
    QUIT = "QUIT"                  # request a clean application shutdown


@dataclass(frozen=True)
class MenuResult:
    """Outcome of a menu interaction.

    :param kind: one of :class:`MenuResultKind`.
    :param payload: optional data; for ``LAUNCH_GAME`` this is the feature name
        (e.g. ``"snake"``).
    """

    kind: MenuResultKind
    payload: Optional[str] = None

    # Convenience constructors so call-sites read naturally.
    @staticmethod
    def resume() -> "MenuResult":
        return MenuResult(MenuResultKind.RESUME)

    @staticmethod
    def launch_game(name: str) -> "MenuResult":
        return MenuResult(MenuResultKind.LAUNCH_GAME, name)

    @staticmethod
    def launch_demo(name: str) -> "MenuResult":
        return MenuResult(MenuResultKind.LAUNCH_DEMO, name)

    @staticmethod
    def open_settings() -> "MenuResult":
        return MenuResult(MenuResultKind.OPEN_SETTINGS)

    @staticmethod
    def quit() -> "MenuResult":
        return MenuResult(MenuResultKind.QUIT)


class MenuController(Protocol):
    """Interface the real Phase-3 menu will implement.

    The state machine depends only on this seam, so swapping
    :class:`PlaceholderMenu` for the real ``src/menu/`` system is a one-line
    constructor injection (``AppStateMachine(menu=RealMenu(...))``).
    """

    def run(self, matrix, controller) -> MenuResult:  # pragma: no cover - protocol
        """Render + navigate the menu until a terminal action; return it."""
        ...


# ---------------------------------------------------------------------------
# Placeholder menu (testability only; replaced wholesale in Phase 3)
# ---------------------------------------------------------------------------
class PlaceholderMenu:
    """A trivial, dependency-light menu so transitions are exercisable now.

    Behavior (deliberately minimal -- Phase 3 supplies the real UI):

    * Draws a simple centered ``MENU`` label using the existing
      ``src.display._fonts`` / ``src.display._utils`` helpers, if available
      (best-effort; never required for the state machine to work).
    * **A** launches the first playable game found in the configured sequence
      (falls back to ``"snake"`` if none is configured), returning
      :func:`MenuResult.launch_game`.
    * **B** resumes the demo carousel, returning :func:`MenuResult.resume`.
    * Window-close / quit gesture returns :func:`MenuResult.quit`.

    It polls ``controller.poll_events()`` each frame at ~30 FPS and honors
    ``should_stop()`` so process shutdown is responsive.
    """

    def __init__(self, config: Optional[dict] = None, fps: float = 30.0):
        self._config = config or {}
        self._frame_dt = 1.0 / fps if fps > 0 else 0.0

    def set_config(self, config: dict) -> None:
        """Allow the state machine to refresh our view of config between cycles."""
        self._config = config or {}

    def _first_playable(self) -> str:
        """Return the first playable game name from config, defaulting to snake."""
        for feat in self._config.get("sequence", []):
            name = feat.get("name")
            if name in PLAYABLE_GAMES:
                return name
        return "snake"

    def _draw(self, matrix) -> None:
        """Best-effort 'MENU' label. Failures are swallowed (placeholder only)."""
        try:
            from PIL import Image, ImageDraw
            from src.display import _fonts

            img = Image.new("RGB", (64, 64))
            draw = ImageDraw.Draw(img)
            text = "MENU"
            try:
                width = _fonts._text_width(text, scale=1)
            except Exception:  # noqa: BLE001
                width = len(text) * 6
            _fonts._draw_text(draw, text, (64 - width) // 2, 28, (255, 255, 255))
            matrix.SetImage(img)
        except Exception:  # noqa: BLE001 - placeholder rendering is non-critical
            pass

    def run(self, matrix, controller) -> MenuResult:
        """Loop until A / B / quit; see class docstring for the mapping."""
        self._draw(matrix)
        while True:
            if should_stop():
                # Process shutdown requested elsewhere; treat as resume so the
                # state machine returns to IDLE and the outer loop exits cleanly.
                return MenuResult.resume()

            if controller.is_quitting():
                return MenuResult.quit()

            for event in controller.poll_events():
                if event.type is EventType.PRESSED:
                    if event.button is Button.A:
                        return MenuResult.launch_game(self._first_playable())
                    if event.button is Button.B:
                        return MenuResult.resume()

            # Quit gesture (Start+Select / hold-Start) also exits the menu to
            # idle, mirroring the in-game quit semantics for consistency.
            if wants_quit(controller):
                return MenuResult.resume()

            if self._frame_dt:
                time.sleep(self._frame_dt)


# ---------------------------------------------------------------------------
# Demo carousel (CONTROLLER_OVERHAUL.md §3.4) -- reuses src/main.py helpers
# ---------------------------------------------------------------------------
# Features that require internet connectivity. Mirrors src/main.INTERNET_FEATURES
# but kept local so this module does not force a hard import cycle at definition
# time; the values are identical (validated by tests).
INTERNET_FEATURES = {
    "bitcoin_price", "weather", "stock_ticker", "sp500_heatmap",
    "video_player", "github_stats",
}


class DemoCarousel:
    """Idle demo feature-cycler extracted from ``src/main.py``'s main loop.

    This class is a thin *orchestrator* over the existing ``src/main.py``
    helpers -- it deliberately does **not** reimplement the watchdog, schedule
    or feature-run logic. It imports those functions lazily from ``src.main`` so
    behavior stays in one place and there is no circular import at module-load
    time.

    One full :meth:`run_cycle` reproduces exactly today's behavior:

    * one ``_check_internet()`` per cycle, skipping :data:`INTERNET_FEATURES`
      when offline;
    * per-feature ``duration`` (capped at 300s) with ``clear_stop()`` before each
      feature and ``run_feature`` (which itself uses ``_run_feature_with_watchdog``);
    * a 0.5s pause between features;
    * config reload + ``_check_schedule()`` night-mode/brightness/feature
      filtering between cycles.

    The single *new* behavior is the ``menu_requested`` callback: when it returns
    True (a START press detected by the background input thread, which also
    called ``request_stop()``), the carousel stops promptly and returns control
    so the state machine can transition IDLE -> MENU.
    """

    def __init__(self, matrix, config: dict, shutdown_event: threading.Event,
                 menu_requested: Optional[Callable[[], bool]] = None):
        """
        :param matrix: the shared RGBMatrix (or simulator / proxy).
        :param config: the current parsed ``config.json`` dict.
        :param shutdown_event: process-wide shutdown :class:`threading.Event`.
        :param menu_requested: callable returning True when the user pressed
            START during the demo (set by the state machine's input thread).
            Defaults to "never" so :class:`DemoCarousel` is usable standalone.
        """
        self.matrix = matrix
        self.config = config or {}
        self._shutdown = shutdown_event
        self._menu_requested = menu_requested or (lambda: False)
        self._refresh_enabled()

    def _refresh_enabled(self) -> None:
        """Recompute ``duration`` and the enabled-feature list from config."""
        self.duration = self.config.get("display_duration", 60)
        sequence = self.config.get("sequence", [])
        self.enabled_features = [f for f in sequence if f.get("enabled", False)]

    def update_config(self, config: dict) -> None:
        """Replace the config snapshot (e.g. after a settings change)."""
        self.config = config or {}
        self._refresh_enabled()

    def _should_break(self) -> bool:
        """True if the carousel must stop (shutdown or menu requested)."""
        return self._shutdown.is_set() or self._menu_requested()

    def run_cycle(self) -> None:
        """Run a single full pass over the enabled features.

        Returns early (without raising) if shutdown or a menu request occurs.
        Reloads config + applies the schedule at the end of the pass, exactly as
        the legacy main loop did between cycles.
        """
        # Lazy import keeps src.app_state importable from src.main and vice
        # versa without a circular-import error at module load.
        from src.main import (
            _check_internet, _check_schedule, load_config, run_feature,
        )

        internet_available = _check_internet()
        if not internet_available:
            logger.info(
                "Internet unavailable this cycle -- internet features will be skipped"
            )

        for feature in self.enabled_features:
            if self._should_break():
                return

            name = feature.get("name", "unknown")

            if name in INTERNET_FEATURES and not internet_available:
                logger.info("Skipping %s (no internet)", name)
                continue

            feat_duration = min(feature.get("duration", self.duration), 300)
            clear_stop()
            run_feature(name, self.matrix, feat_duration)

            # A feature may have returned because the input thread called
            # request_stop() on a START press; check the menu flag before moving
            # on so we surface the transition promptly.
            if self._should_break():
                return

            if not self._shutdown.is_set():
                time.sleep(0.5)
                if self._should_break():
                    return

        # Between-cycle config reload + schedule application (unchanged logic).
        if not self._shutdown.is_set():
            self.config = load_config()
            self._refresh_enabled()

            schedule_override = _check_schedule()
            if schedule_override:
                if "brightness" in schedule_override:
                    try:
                        self.matrix.brightness = schedule_override["brightness"]
                    except Exception:  # noqa: BLE001
                        pass
                allowed = schedule_override.get("allowed_features", [])
                if allowed:
                    self.enabled_features = [
                        f for f in self.enabled_features
                        if f.get("name") in allowed
                    ]
                    if not self.enabled_features:
                        self.enabled_features = [
                            {"name": "time_display", "type": "utility",
                             "enabled": True}
                        ]
            else:
                # Restore normal brightness when no schedule override is active
                default_brightness = self.config.get("matrix_hardware", {}).get("brightness", 80)
                try:
                    self.matrix.brightness = default_brightness
                except Exception:  # noqa: BLE001
                    pass

            if not self.enabled_features:
                logger.warning(
                    "No features enabled after config reload, waiting 30s..."
                )
                # Interruptible so a START press / shutdown is still responsive.
                self._shutdown.wait(timeout=30)


# ---------------------------------------------------------------------------
# State machine (CONTROLLER_OVERHAUL.md §3.2 / §3.3)
# ---------------------------------------------------------------------------
class AppStateMachine:
    """Top-level state machine. Replaces the inline loop in ``main.main()``.

    Transition table (as implemented this phase):

    ===========  ==============================================  ==========
    From         Trigger                                         To
    ===========  ==============================================  ==========
    IDLE         START pressed (during demo)                     MENU
    IDLE         (no input)                                      IDLE (next demo)
    MENU         A on a playable game (MenuResult.LAUNCH_GAME)   IN_GAME
    MENU         B / Resume / quit gesture (MenuResult.RESUME)   IDLE
    MENU         MenuResult.OPEN_SETTINGS (deferred)             MENU
    MENU         MenuResult.QUIT                                 shutdown
    IN_GAME      wants_quit(controller) or game returns          MENU
    *any*        controller.is_quitting()                        shutdown
    ===========  ==============================================  ==========

    The matrix is owned by this object. ``controller`` is the single, shared
    :class:`src.input.Controller`. A small daemon input thread watches for START
    during IDLE and calls ``request_stop()`` (reusing ``_shared``) so the running
    demo breaks within a frame -- the in-process replacement for the deleted
    ``_command_watcher``.
    """

    # Seconds after entering IDLE before START/A can open the menu.
    # Prevents accidental menu activation during gameplay transitions.
    # Matches the menu's own grace period for consistency.
    START_DEBOUNCE_SECONDS = 2.0

    def __init__(self, matrix, controller, config: dict,
                 shutdown_event: Optional[threading.Event] = None,
                 menu: Optional[MenuController] = None,
                 input_poll_hz: float = 60.0):
        """
        :param matrix: shared RGBMatrix / simulator / proxy (owned here).
        :param controller: shared :class:`src.input.Controller`.
        :param config: parsed ``config.json``.
        :param shutdown_event: process shutdown event; created if omitted.
        :param menu: a :class:`MenuController`; defaults to :class:`PlaceholderMenu`
            so Phase 3 can inject the real menu with no other changes.
        :param input_poll_hz: poll rate of the background START-watcher thread.
        """
        self.matrix = matrix
        self.controller = controller
        self.config = config or {}
        self._shutdown = shutdown_event or threading.Event()
        self.mode = AppMode.IDLE
        self.menu = menu if menu is not None else self._default_menu()

        # Set by the background input thread when START is pressed during IDLE.
        self._menu_requested = threading.Event()
        self._input_poll_interval = 1.0 / input_poll_hz if input_poll_hz > 0 else 0.05
        self._input_thread: Optional[threading.Thread] = None

        # Debounce tracking for START button: monotonic timestamp of the last
        # time the menu was closed (returned to IDLE) or the system booted.
        # START presses within START_DEBOUNCE_SECONDS of this time are ignored.
        self._last_idle_entry_time: float = time.monotonic()

        self._carousel = DemoCarousel(
            matrix, self.config, self._shutdown,
            menu_requested=self._menu_requested.is_set,
        )

    def _default_menu(self) -> "MenuController":
        """Construct the default Phase-3 :class:`MenuSystem`.

        Imported lazily so ``src.menu`` (which imports :class:`MenuResult` from
        this module) does not create an import cycle at module-load time. Falls
        back to :class:`PlaceholderMenu` only if the real menu cannot be imported
        (e.g. a partial install) so the state machine is never left without a
        menu.
        """
        try:
            from src.menu import MenuSystem
            return MenuSystem(self.config)
        except Exception:  # noqa: BLE001 - defensive; keep the app bootable
            logger.warning(
                "Falling back to PlaceholderMenu (could not import MenuSystem)",
                exc_info=True,
            )
            return PlaceholderMenu(self.config)

    # ----- background input thread (replaces _command_watcher) ---------------
    def _input_watch_loop(self) -> None:
        """Daemon loop: during IDLE, set the menu flag + request_stop on START.

        Mirrors how the old ``_command_watcher`` polled ``command.json`` and
        called ``request_stop()``; the trigger is now a gamepad START press (or
        keyboard fallback) rather than a file write. It also surfaces a
        window-close (``is_quitting()``) as a shutdown request.

        IMPORTANT: This thread only polls the controller when in IDLE mode.
        In MENU and IN_GAME modes, the foreground loop owns the controller and
        calls ``poll_events()`` itself. Polling from both threads would race on
        the event buffer and reset directional held-state, causing the game to
        miss D-pad/analog stick input.
        """
        logger.info("Input watcher thread started")
        while not self._shutdown.is_set():
            # Only poll the controller when in IDLE mode. In MENU/IN_GAME the
            # foreground loop owns input exclusively -- polling here would drain
            # the event buffer and reset directional held-state, causing the
            # game/menu to miss D-pad/analog stick input.
            if self.mode is AppMode.IDLE:
                try:
                    events = self.controller.poll_events()
                except Exception:  # noqa: BLE001 - never let the watcher die
                    events = []

                if self.controller.is_quitting():
                    self._shutdown.set()
                    break

                for ev in events:
                    if ev.type is EventType.PRESSED and ev.button in (Button.START, Button.A):
                        # Debounce: ignore presses within grace period of entering
                        # IDLE (prevents accidental menu activation during
                        # gameplay transitions or rapid button mashing).
                        elapsed_since_idle = time.monotonic() - self._last_idle_entry_time
                        if elapsed_since_idle < self.START_DEBOUNCE_SECONDS:
                            logger.debug(
                                "%s debounced (%.2fs < %.2fs)",
                                ev.button.value, elapsed_since_idle,
                                self.START_DEBOUNCE_SECONDS,
                            )
                            break
                        logger.info("%s pressed during demo -> requesting MENU",
                                    ev.button.value)
                        self._menu_requested.set()
                        request_stop()
                        break
            else:
                # Still check for window-close even when not polling events,
                # since is_quitting() reads a flag set by the foreground poll.
                if self.controller.is_quitting():
                    self._shutdown.set()
                    break

            self._shutdown.wait(timeout=self._input_poll_interval)
        logger.info("Input watcher thread stopped")

    def _start_input_thread(self) -> None:
        if self._input_thread is None:
            self._input_thread = threading.Thread(
                target=self._input_watch_loop, daemon=True
            )
            self._input_thread.start()

    # ----- per-mode handlers -------------------------------------------------
    def _run_idle(self) -> None:
        """IDLE: run one carousel cycle; START (via the input thread) -> MENU."""
        self._carousel.run_cycle()
        if self._menu_requested.is_set():
            # Consume the request and transition. clear_stop() lets the next
            # feature (or the menu) run without the stale stop flag set.
            self._menu_requested.clear()
            clear_stop()
            self.mode = AppMode.MENU

    def _run_menu(self) -> None:
        """MENU: delegate to the (placeholder or real) menu, then transition."""
        clear_stop()
        if hasattr(self.menu, "set_config"):
            try:
                self.menu.set_config(self.config)
            except Exception:  # noqa: BLE001
                pass

        result = self.menu.run(self.matrix, self.controller)
        kind = result.kind

        if kind is MenuResultKind.LAUNCH_GAME:
            self._pending_game = result.payload
            self.mode = AppMode.IN_GAME
        elif kind is MenuResultKind.LAUNCH_DEMO:
            self._run_demo(result.payload)
            # After the demo finishes, return to MENU (stay in MENU mode).
            self.mode = AppMode.MENU
        elif kind is MenuResultKind.QUIT:
            self._shutdown.set()
        elif kind is MenuResultKind.OPEN_SETTINGS:
            # Deferred to Phase 3/4: settings is a pushed menu screen. For now
            # stay in MENU so the seam exists without settings logic here.
            self.mode = AppMode.MENU
        else:  # RESUME (or anything unexpected) -> back to the demo carousel.
            self.mode = AppMode.IDLE
            self._last_idle_entry_time = time.monotonic()

    def _run_demo(self, name: str) -> None:
        """Run a feature in demo mode (no controller) for its configured duration.

        Called when the user selects a demo from the Demos submenu. The feature
        runs with ``controller=None`` (non-interactive) for up to 30 seconds (or
        the configured ``display_duration``), then returns so the state machine
        can re-enter the menu.
        """
        if not name:
            return
        clear_stop()
        from src.main import run_feature
        try:
            duration = self.config.get("display_duration", 30)
            # Cap demo viewing at the configured duration (default 30s).
            duration = min(duration, 300)
            run_feature(name, self.matrix, duration, controller=None)
        except Exception:  # noqa: BLE001 - a crashing demo must not crash the app
            logger.error("Demo '%s' crashed; returning to menu", name, exc_info=True)
        finally:
            clear_stop()

    def _run_game(self) -> None:
        """IN_GAME: launch the chosen playable game with the controller.

        Per the §5 playability contract, ``run_feature`` forwards the controller
        to the game; the game returns on ``wants_quit(controller)`` or game-over.
        On return we always go back to MENU. (Game modules themselves are
        extended in Phase 5; here we just wire the launch + return transition.)
        """
        name = getattr(self, "_pending_game", None)
        self._pending_game = None
        if not name:
            self.mode = AppMode.MENU
            return

        clear_stop()
        from src.main import run_feature
        try:
            duration = self.config.get("display_duration", 60)
            # Forward the controller so the game runs interactively. run_feature
            # gains an optional controller kwarg in this phase; demos never pass
            # one (CONTROLLER_OVERHAUL.md §5.1). Game modules themselves are
            # converted to honor it in Phase 5.
            run_feature(name, self.matrix, duration, controller=self.controller)
        except Exception:  # noqa: BLE001 - a crashing game must not crash the app
            logger.error("Game '%s' crashed; returning to menu", name, exc_info=True)
        finally:
            clear_stop()

        # A game always returns to the menu (quit-combo or game-over).
        self.mode = AppMode.MENU

    # ----- top-level loop ----------------------------------------------------
    def run(self) -> None:
        """Top-level loop: dispatch on :attr:`mode` until shutdown.

        Replaces the ``while not _shutdown.is_set()`` loop in ``main.main()``.
        Starts the background input thread (START-watcher) once, then dispatches
        per-mode handlers. Window-close (``controller.is_quitting()``) sets the
        shutdown event and exits cleanly.
        """
        self._start_input_thread()
        logger.info("Entering state machine loop (mode=%s)", self.mode.value)

        try:
            while not self._shutdown.is_set():
                # Global QUIT check (the input thread also sets this, but check
                # here too so a foreground-mode return reacts immediately).
                if self.controller.is_quitting():
                    logger.info("Window close / QUIT observed -> shutting down")
                    self._shutdown.set()
                    break

                if self.mode is AppMode.IDLE:
                    self._run_idle()
                elif self.mode is AppMode.MENU:
                    self._run_menu()
                elif self.mode is AppMode.IN_GAME:
                    self._run_game()
                else:  # pragma: no cover - defensive; unknown mode -> idle
                    logger.warning("Unknown mode %r, reverting to IDLE", self.mode)
                    self.mode = AppMode.IDLE
                    self._last_idle_entry_time = time.monotonic()
        finally:
            logger.info("State machine loop exited")

    def request_shutdown(self) -> None:
        """Signal the state machine (and its input thread) to stop ASAP."""
        self._shutdown.set()