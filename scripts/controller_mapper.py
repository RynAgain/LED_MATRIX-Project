#!/usr/bin/env python3
"""
Controller Mapping GUI -- Visual tool to test and configure your gamepad.

Run with:
    venv\\Scripts\\python scripts/controller_mapper.py

Features:
  - Live display of all raw button, axis, and hat states
  - Click a logical button (A, B, START, SELECT) then press the physical button
    to assign it
  - Axis auto-detection for X/Y stick
  - Deadzone slider
  - Invert-Y toggle
  - Save directly to config/controller.json
"""

import os
import sys
import json
import threading
import time

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import tkinter as tk
from tkinter import ttk, messagebox

import pygame

CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "controller.json")


class ControllerMapperApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Controller Mapper - LED Matrix Project")
        self.root.geometry("750x650")
        self.root.resizable(True, True)

        # State
        self.joystick = None
        self.running = True
        self.waiting_for = None  # Which logical button we're waiting to map
        self.mapping = {
            "buttons": {},  # int -> str (logical name)
            "hat_index": 0,
            "axis_x": 0,
            "axis_y": 1,
            "invert_y": False,
            "deadzone": 0.5,
        }
        self.waiting_for_axis = None  # "x" or "y" when detecting axis

        # Load existing config
        self._load_config()

        # Init pygame
        pygame.init()
        pygame.joystick.init()

        # Build UI
        self._build_ui()

        # Try to connect joystick
        self._connect_joystick()

        # Start polling thread
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

        # Handle close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_config(self):
        """Load existing controller.json if present."""
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.mapping["hat_index"] = data.get("hat_index", 0)
            self.mapping["axis_x"] = data.get("axis_x", 0)
            self.mapping["axis_y"] = data.get("axis_y", 1)
            self.mapping["invert_y"] = data.get("invert_y", False)
            self.mapping["deadzone"] = data.get("deadzone", 0.5)
            raw_buttons = data.get("buttons", {})
            for idx_str, name in raw_buttons.items():
                try:
                    self.mapping["buttons"][int(idx_str)] = name
                except (ValueError, TypeError):
                    pass
        except (FileNotFoundError, json.JSONDecodeError):
            # Use defaults
            self.mapping["buttons"] = {0: "A", 1: "B", 9: "START", 8: "SELECT"}

    def _build_ui(self):
        """Build the tkinter UI."""
        # --- Header ---
        header = ttk.Frame(self.root, padding=10)
        header.pack(fill="x")

        self.status_label = ttk.Label(header, text="No controller detected",
                                       font=("Segoe UI", 11, "bold"))
        self.status_label.pack(side="left")

        ttk.Button(header, text="Refresh", command=self._connect_joystick).pack(side="right")

        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=10)

        # --- Main content in two columns ---
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)

        # Left column: Raw input display
        left = ttk.LabelFrame(main, text="Raw Input (Live)", padding=10)
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.raw_text = tk.Text(left, width=35, height=25, font=("Consolas", 9),
                                state="disabled", bg="#1e1e1e", fg="#00ff00")
        self.raw_text.pack(fill="both", expand=True)

        # Right column: Mapping configuration
        right = ttk.LabelFrame(main, text="Button Mapping", padding=10)
        right.pack(side="right", fill="both", expand=True, padx=(5, 0))

        # Button mapping section
        btn_frame = ttk.Frame(right)
        btn_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(btn_frame, text="Click 'Map' then press the physical button:",
                  font=("Segoe UI", 9)).pack(anchor="w")

        self.map_buttons = {}
        self.map_labels = {}
        for logical in ["A", "B", "START", "SELECT"]:
            row = ttk.Frame(btn_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=f"{logical}:", width=8).pack(side="left")
            lbl = ttk.Label(row, text=self._get_button_display(logical),
                           width=12, relief="sunken", anchor="center")
            lbl.pack(side="left", padx=5)
            self.map_labels[logical] = lbl
            btn = ttk.Button(row, text="Map", width=5,
                           command=lambda l=logical: self._start_mapping(l))
            btn.pack(side="left")
            self.map_buttons[logical] = btn

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=10)

        # Axis mapping section
        axis_frame = ttk.LabelFrame(right, text="Analog Stick Axes", padding=5)
        axis_frame.pack(fill="x", pady=(0, 10))

        # X axis
        ax_row = ttk.Frame(axis_frame)
        ax_row.pack(fill="x", pady=2)
        ttk.Label(ax_row, text="X Axis:", width=8).pack(side="left")
        self.axis_x_label = ttk.Label(ax_row, text=str(self.mapping["axis_x"]),
                                       width=4, relief="sunken", anchor="center")
        self.axis_x_label.pack(side="left", padx=5)
        ttk.Button(ax_row, text="Detect", width=6,
                  command=lambda: self._start_axis_detect("x")).pack(side="left")

        # Y axis
        ay_row = ttk.Frame(axis_frame)
        ay_row.pack(fill="x", pady=2)
        ttk.Label(ay_row, text="Y Axis:", width=8).pack(side="left")
        self.axis_y_label = ttk.Label(ay_row, text=str(self.mapping["axis_y"]),
                                       width=4, relief="sunken", anchor="center")
        self.axis_y_label.pack(side="left", padx=5)
        ttk.Button(ay_row, text="Detect", width=6,
                  command=lambda: self._start_axis_detect("y")).pack(side="left")

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=10)

        # Options section
        opts_frame = ttk.LabelFrame(right, text="Options", padding=5)
        opts_frame.pack(fill="x", pady=(0, 10))

        # Deadzone
        dz_row = ttk.Frame(opts_frame)
        dz_row.pack(fill="x", pady=2)
        ttk.Label(dz_row, text="Deadzone:").pack(side="left")
        self.deadzone_var = tk.DoubleVar(value=self.mapping["deadzone"])
        self.deadzone_scale = ttk.Scale(dz_row, from_=0.1, to=0.9,
                                         variable=self.deadzone_var, orient="horizontal")
        self.deadzone_scale.pack(side="left", fill="x", expand=True, padx=5)
        self.deadzone_display = ttk.Label(dz_row, text=f"{self.mapping['deadzone']:.2f}",
                                           width=5)
        self.deadzone_display.pack(side="right")
        self.deadzone_var.trace_add("write", self._on_deadzone_change)

        # Invert Y
        self.invert_y_var = tk.BooleanVar(value=self.mapping["invert_y"])
        ttk.Checkbutton(opts_frame, text="Invert Y axis",
                       variable=self.invert_y_var,
                       command=self._on_invert_change).pack(anchor="w", pady=2)

        # Hat index
        hat_row = ttk.Frame(opts_frame)
        hat_row.pack(fill="x", pady=2)
        ttk.Label(hat_row, text="Hat (D-pad) index:").pack(side="left")
        self.hat_var = tk.IntVar(value=self.mapping["hat_index"])
        ttk.Spinbox(hat_row, from_=0, to=3, width=3,
                   textvariable=self.hat_var,
                   command=self._on_hat_change).pack(side="left", padx=5)

        # --- Footer with Save button ---
        footer = ttk.Frame(self.root, padding=10)
        footer.pack(fill="x")

        self.waiting_label = ttk.Label(footer, text="", foreground="blue",
                                        font=("Segoe UI", 9, "italic"))
        self.waiting_label.pack(side="left")

        ttk.Button(footer, text="Save Config", command=self._save_config,
                  style="Accent.TButton").pack(side="right", padx=5)
        ttk.Button(footer, text="Run Calibration CLI",
                  command=self._run_calibration).pack(side="right", padx=5)

    def _get_button_display(self, logical):
        """Get display text for a logical button's current physical mapping."""
        for idx, name in self.mapping["buttons"].items():
            if name == logical:
                return f"Button {idx}"
        return "(unmapped)"

    def _connect_joystick(self):
        """Try to connect to joystick 0."""
        try:
            pygame.joystick.quit()
            pygame.joystick.init()
            if pygame.joystick.get_count() > 0:
                self.joystick = pygame.joystick.Joystick(0)
                self.joystick.init()
                name = self.joystick.get_name()
                info = (f"{name} | "
                       f"Buttons: {self.joystick.get_numbuttons()} | "
                       f"Axes: {self.joystick.get_numaxes()} | "
                       f"Hats: {self.joystick.get_numhats()}")
                self.status_label.config(text=info, foreground="green")
            else:
                self.joystick = None
                self.status_label.config(text="No controller detected",
                                         foreground="red")
        except Exception as e:
            self.status_label.config(text=f"Error: {e}", foreground="red")

    def _start_mapping(self, logical):
        """Start waiting for a physical button press to map to logical."""
        self.waiting_for = logical
        self.waiting_label.config(
            text=f"Press the physical button for '{logical}'...")
        # Highlight the button being mapped
        for name, btn in self.map_buttons.items():
            btn.config(state="disabled" if name != logical else "normal")

    def _start_axis_detect(self, which):
        """Start waiting for an axis movement to detect X or Y."""
        self.waiting_for_axis = which
        axis_name = "horizontal (left/right)" if which == "x" else "vertical (up/down)"
        self.waiting_label.config(
            text=f"Move the analog stick {axis_name}...")

    def _on_deadzone_change(self, *args):
        val = self.deadzone_var.get()
        self.mapping["deadzone"] = round(val, 2)
        self.deadzone_display.config(text=f"{val:.2f}")

    def _on_invert_change(self):
        self.mapping["invert_y"] = self.invert_y_var.get()

    def _on_hat_change(self):
        self.mapping["hat_index"] = self.hat_var.get()

    def _save_config(self):
        """Save current mapping to config/controller.json."""
        data = {
            "buttons": {str(idx): name for idx, name in self.mapping["buttons"].items()},
            "hat_index": self.mapping["hat_index"],
            "axis_x": self.mapping["axis_x"],
            "axis_y": self.mapping["axis_y"],
            "invert_y": self.mapping["invert_y"],
            "deadzone": self.mapping["deadzone"],
        }
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            messagebox.showinfo("Saved",
                              f"Controller config saved to:\n{CONFIG_PATH}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config:\n{e}")

    def _run_calibration(self):
        """Launch the CLI calibration in a new terminal."""
        import subprocess
        cmd = f'start cmd /k "cd /d {PROJECT_ROOT} && venv\\Scripts\\python -m src.input.controller calibrate"'
        os.system(cmd)

    def _poll_loop(self):
        """Background thread: poll joystick and update UI."""
        while self.running:
            if self.joystick is None:
                time.sleep(0.1)
                continue

            try:
                pygame.event.pump()
            except Exception:
                time.sleep(0.1)
                continue

            # Build raw state text
            lines = []
            num_buttons = self.joystick.get_numbuttons()
            num_axes = self.joystick.get_numaxes()
            num_hats = self.joystick.get_numhats()

            # Buttons
            lines.append("=== BUTTONS ===")
            pressed_buttons = []
            for i in range(num_buttons):
                if self.joystick.get_button(i):
                    pressed_buttons.append(i)
                    # Check if we're waiting to map a button
                    if self.waiting_for is not None:
                        self._assign_button(i)

            if pressed_buttons:
                lines.append(f"  PRESSED: {pressed_buttons}")
            else:
                lines.append("  (none pressed)")

            # Axes
            lines.append("")
            lines.append("=== AXES ===")
            for i in range(num_axes):
                val = self.joystick.get_axis(i)
                bar = self._axis_bar(val)
                marker = ""
                if i == self.mapping["axis_x"]:
                    marker = " [X]"
                elif i == self.mapping["axis_y"]:
                    marker = " [Y]"
                lines.append(f"  {i}: {val:+.3f} {bar}{marker}")

                # Check if we're detecting an axis
                if self.waiting_for_axis and abs(val) > 0.7:
                    self._assign_axis(i)

            # Hats
            lines.append("")
            lines.append("=== HATS (D-PAD) ===")
            for i in range(num_hats):
                hat = self.joystick.get_hat(i)
                direction = self._hat_direction(hat)
                marker = " [ACTIVE]" if i == self.mapping["hat_index"] else ""
                lines.append(f"  {i}: ({hat[0]:+d}, {hat[1]:+d}) {direction}{marker}")

            # Logical state summary
            lines.append("")
            lines.append("=== CURRENT MAPPING ===")
            for idx, name in sorted(self.mapping["buttons"].items()):
                lines.append(f"  Btn {idx} -> {name}")
            lines.append(f"  Axis X={self.mapping['axis_x']}, "
                        f"Y={self.mapping['axis_y']}")
            lines.append(f"  Deadzone={self.mapping['deadzone']:.2f}, "
                        f"InvertY={self.mapping['invert_y']}")

            # Update the text widget from the main thread
            text = "\n".join(lines)
            self.root.after(0, self._update_raw_text, text)

            time.sleep(0.033)  # ~30 Hz

    def _assign_button(self, physical_idx):
        """Assign a physical button to the waiting logical button."""
        logical = self.waiting_for
        self.waiting_for = None

        # Remove any existing mapping for this physical button
        self.mapping["buttons"] = {
            k: v for k, v in self.mapping["buttons"].items()
            if v != logical
        }
        # Assign new mapping
        self.mapping["buttons"][physical_idx] = logical

        # Update UI from main thread
        def _update():
            self.waiting_label.config(
                text=f"Mapped Button {physical_idx} -> {logical}")
            self.map_labels[logical].config(text=f"Button {physical_idx}")
            for btn in self.map_buttons.values():
                btn.config(state="normal")
        self.root.after(0, _update)

    def _assign_axis(self, axis_idx):
        """Assign a detected axis to X or Y."""
        which = self.waiting_for_axis
        self.waiting_for_axis = None

        if which == "x":
            self.mapping["axis_x"] = axis_idx
        else:
            self.mapping["axis_y"] = axis_idx

        def _update():
            self.waiting_label.config(
                text=f"Detected axis {axis_idx} as {'X' if which == 'x' else 'Y'}")
            if which == "x":
                self.axis_x_label.config(text=str(axis_idx))
            else:
                self.axis_y_label.config(text=str(axis_idx))
        self.root.after(0, _update)

    def _update_raw_text(self, text):
        """Update the raw input display (must be called from main thread)."""
        self.raw_text.config(state="normal")
        self.raw_text.delete("1.0", "end")
        self.raw_text.insert("1.0", text)
        self.raw_text.config(state="disabled")

    @staticmethod
    def _axis_bar(val, width=15):
        """Render a simple ASCII bar for an axis value."""
        center = width // 2
        pos = int((val + 1) / 2 * width)
        pos = max(0, min(width, pos))
        bar = list("-" * (width + 1))
        bar[center] = "|"
        bar[pos] = "#"
        return "[" + "".join(bar) + "]"

    @staticmethod
    def _hat_direction(hat):
        """Convert hat tuple to direction string."""
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

    def _on_close(self):
        """Clean shutdown."""
        self.running = False
        try:
            pygame.quit()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        """Start the tkinter main loop."""
        self.root.mainloop()


if __name__ == "__main__":
    app = ControllerMapperApp()
    app.run()
