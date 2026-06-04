#!/usr/bin/env python3
"""
Controller debug utility -- shows raw joystick state in real-time.

Run with:
    venv\Scripts\python scripts/debug_controller.py

Displays:
  - All button states (pressed/released)
  - All axis values (analog sticks, triggers)
  - All hat (D-pad) values
  - Logical mapped events from the Controller class

Press Ctrl+C to exit.
"""

import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame


def clear_screen():
    """Clear terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def run_raw_debug():
    """Show raw pygame joystick data in a live-updating display."""
    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print("ERROR: No joystick/gamepad detected!")
        print("Plug in your USB controller and try again.")
        pygame.quit()
        return 1

    js = pygame.joystick.Joystick(0)
    js.init()

    print(f"Controller: {js.get_name()}")
    print(f"  Buttons: {js.get_numbuttons()}")
    print(f"  Axes:    {js.get_numaxes()}")
    print(f"  Hats:    {js.get_numhats()}")
    print(f"  Balls:   {js.get_numballs()}")
    print()
    print("=" * 60)
    print("Live input monitor (press Ctrl+C to exit)")
    print("=" * 60)
    print()

    # Also load the logical mapping for comparison
    try:
        from src.input.controller import load_mapping, Button
        mapping = load_mapping()
        print(f"Loaded mapping from config/controller.json:")
        for idx, btn in mapping.buttons.items():
            print(f"  Button {idx} -> {btn.value}")
        print(f"  Hat index: {mapping.hat_index}")
        print(f"  Axis X: {mapping.axis_x}, Axis Y: {mapping.axis_y}")
        print(f"  Invert Y: {mapping.invert_y}, Deadzone: {mapping.deadzone}")
    except Exception as e:
        print(f"  (Could not load mapping: {e})")
        mapping = None

    print()
    print("-" * 60)
    print("Watching for input... move sticks, press buttons, use D-pad")
    print("-" * 60)

    last_buttons = [False] * js.get_numbuttons()
    last_axes = [0.0] * js.get_numaxes()
    last_hats = [(0, 0)] * js.get_numhats()

    try:
        while True:
            pygame.event.pump()

            # Check buttons
            for i in range(js.get_numbuttons()):
                pressed = js.get_button(i)
                if pressed != last_buttons[i]:
                    state = "PRESSED" if pressed else "RELEASED"
                    mapped = ""
                    if mapping and i in mapping.buttons:
                        mapped = f"  -> {mapping.buttons[i].value}"
                    print(f"  [BUTTON {i:2d}] {state}{mapped}")
                    last_buttons[i] = pressed

            # Check axes
            for i in range(js.get_numaxes()):
                val = js.get_axis(i)
                # Only report significant changes (avoid noise)
                if abs(val - last_axes[i]) > 0.05:
                    bar = _axis_bar(val)
                    label = ""
                    if mapping:
                        if i == mapping.axis_x:
                            label = " (X-axis)"
                        elif i == mapping.axis_y:
                            label = " (Y-axis)"
                    print(f"  [AXIS   {i:2d}] {val:+.3f} {bar}{label}")
                    last_axes[i] = val

            # Check hats
            for i in range(js.get_numhats()):
                hat = js.get_hat(i)
                if hat != last_hats[i]:
                    direction = _hat_direction(hat)
                    print(f"  [HAT    {i:2d}] ({hat[0]:+d}, {hat[1]:+d}) = {direction}")
                    last_hats[i] = hat

            time.sleep(0.016)  # ~60 Hz polling

    except KeyboardInterrupt:
        print("\n\nExiting debug mode.")

    pygame.quit()
    return 0


def _axis_bar(val, width=20):
    """Render a simple ASCII bar for an axis value (-1 to +1)."""
    center = width // 2
    pos = int((val + 1) / 2 * width)
    pos = max(0, min(width, pos))
    bar = ["-"] * (width + 1)
    bar[center] = "|"
    bar[pos] = "#"
    return "[" + "".join(bar) + "]"


def _hat_direction(hat):
    """Convert hat tuple to a human-readable direction string."""
    hx, hy = hat
    dirs = []
    if hy > 0:
        dirs.append("UP")
    elif hy < 0:
        dirs.append("DOWN")
    if hx < 0:
        dirs.append("LEFT")
    elif hx > 0:
        dirs.append("RIGHT")
    return "+".join(dirs) if dirs else "CENTER"


if __name__ == "__main__":
    sys.exit(run_raw_debug())
