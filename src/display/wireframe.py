#!/usr/bin/env python3
"""Rotating wireframe 3D polygons for 64x64 LED matrix.

Classic demoscene-style spinning wireframe shapes: cube, tetrahedron,
octahedron, icosahedron, torus, and more. Cycles through shapes.
Shape selection and timing are configurable via config/wireframe.json.
"""

import json
import math
import os
import time
import logging
from PIL import Image, ImageDraw
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
CX, CY = WIDTH // 2, HEIGHT // 2
FRAME_INTERVAL = 1.0 / 30
SCALE = 22  # Projection scale
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "wireframe.json",
)

# Target bounding-sphere radius -- the cube spans +-1, so its radius is
# sqrt(3).  Every shape is normalised to this same radius so that they
# all appear the same visual size on screen.
_TARGET_RADIUS = math.sqrt(3)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _load_config():
    """Load wireframe configuration from config/wireframe.json."""
    defaults = {
        "shapes": {
            "cube": True, "tetrahedron": True, "octahedron": True,
            "icosahedron": True, "diamond": True, "pyramid": True,
            "star": True, "torus": True,
        },
        "seconds_per_shape": 10,
        "rotation_speed": 1.0,
    }
    try:
        with open(CONFIG_PATH, "r") as fh:
            cfg = json.load(fh)
        # Merge with defaults
        for key in defaults:
            if key not in cfg:
                cfg[key] = defaults[key]
        return cfg
    except Exception:
        logger.warning("Could not load wireframe config, using defaults")
        return defaults


# ---------------------------------------------------------------------------
# Normalisation helper
# ---------------------------------------------------------------------------

def _normalise(vertices):
    """Scale *vertices* so the bounding-sphere radius equals _TARGET_RADIUS."""
    if not vertices:
        return vertices
    max_r = max(math.sqrt(x * x + y * y + z * z) for x, y, z in vertices)
    if max_r < 1e-6:
        return vertices
    factor = _TARGET_RADIUS / max_r
    return [(x * factor, y * factor, z * factor) for x, y, z in vertices]


# ---------------------------------------------------------------------------
# 3D Shape Definitions
# ---------------------------------------------------------------------------
# Each function returns (vertices, edges, color).
# Vertices are automatically normalised by run() so the visual size is
# identical for every shape.

def _cube():
    v = [
        (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
        (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
    ]
    e = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    return v, e, (0, 200, 255)


def _tetrahedron():
    v = [
        (1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1),
    ]
    e = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    return v, e, (255, 100, 50)


def _octahedron():
    v = [
        (0, 1, 0), (0, -1, 0),
        (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1),
    ]
    e = [
        (0, 2), (0, 3), (0, 4), (0, 5),
        (1, 2), (1, 3), (1, 4), (1, 5),
        (2, 4), (4, 3), (3, 5), (5, 2),
    ]
    return v, e, (50, 255, 50)


def _icosahedron():
    phi = (1 + math.sqrt(5)) / 2
    s = 1 / math.sqrt(1 + phi * phi)
    p = phi * s
    v = [
        (-s, p, 0), (s, p, 0), (-s, -p, 0), (s, -p, 0),
        (0, -s, p), (0, s, p), (0, -s, -p), (0, s, -p),
        (p, 0, -s), (p, 0, s), (-p, 0, -s), (-p, 0, s),
    ]
    e = [
        (0, 1), (0, 5), (0, 7), (0, 10), (0, 11),
        (1, 5), (1, 7), (1, 8), (1, 9),
        (2, 3), (2, 4), (2, 6), (2, 10), (2, 11),
        (3, 4), (3, 6), (3, 8), (3, 9),
        (4, 5), (4, 9), (4, 11),
        (5, 9), (5, 11),
        (6, 7), (6, 8), (6, 10),
        (7, 8), (7, 10),
        (8, 9),
        (10, 11),
    ]
    return v, e, (255, 50, 255)


def _diamond():
    """Double pyramid / bipyramid."""
    v = [
        (0, 1.5, 0), (0, -1.5, 0),
        (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1),
    ]
    e = [
        (0, 2), (0, 3), (0, 4), (0, 5),
        (1, 2), (1, 3), (1, 4), (1, 5),
        (2, 4), (4, 3), (3, 5), (5, 2),
    ]
    return v, e, (255, 255, 50)


def _star():
    """3D star shape."""
    v = []
    e = []
    for i in range(5):
        angle = math.radians(i * 72 - 90)
        v.append((math.cos(angle) * 1.2, math.sin(angle) * 1.2, 0))
    for i in range(5):
        angle = math.radians(i * 72 - 90 + 36)
        v.append((math.cos(angle) * 0.5, math.sin(angle) * 0.5, 0))
    v.append((0, 0, 1))
    v.append((0, 0, -1))

    for i in range(5):
        e.append((i, (i * 2 + 5) % 5 + 5))
        e.append(((i + 1) % 5, i + 5))
    for i in range(5):
        e.append((i, 10))
        e.append((i, 11))

    return v, e, (255, 200, 0)


def _pyramid():
    v = [
        (0, -1.2, 0),
        (-1, 0.8, -1), (1, 0.8, -1), (1, 0.8, 1), (-1, 0.8, 1),
    ]
    e = [
        (0, 1), (0, 2), (0, 3), (0, 4),
        (1, 2), (2, 3), (3, 4), (4, 1),
    ]
    return v, e, (100, 200, 255)


def _torus_wireframe():
    """Simple torus approximation."""
    v = []
    e = []
    R = 0.9
    r = 0.4
    segs = 8
    rings = 6

    for i in range(segs):
        theta = 2 * math.pi * i / segs
        for j in range(rings):
            phi = 2 * math.pi * j / rings
            x = (R + r * math.cos(phi)) * math.cos(theta)
            y = r * math.sin(phi)
            z = (R + r * math.cos(phi)) * math.sin(theta)
            v.append((x, y, z))

    for i in range(segs):
        for j in range(rings):
            idx = i * rings + j
            next_j = i * rings + (j + 1) % rings
            e.append((idx, next_j))
            next_i = ((i + 1) % segs) * rings + j
            e.append((idx, next_i))

    return v, e, (255, 100, 200)


# Registry: key must match the key names in config/wireframe.json "shapes"
_SHAPE_REGISTRY = {
    "cube": ("Cube", _cube),
    "tetrahedron": ("Tetrahedron", _tetrahedron),
    "octahedron": ("Octahedron", _octahedron),
    "icosahedron": ("Icosahedron", _icosahedron),
    "diamond": ("Diamond", _diamond),
    "pyramid": ("Pyramid", _pyramid),
    "star": ("Star", _star),
    "torus": ("Torus", _torus_wireframe),
}

# Deterministic display order
_SHAPE_ORDER = [
    "cube", "tetrahedron", "octahedron", "icosahedron",
    "diamond", "pyramid", "star", "torus",
]


# ---------------------------------------------------------------------------
# 3D math
# ---------------------------------------------------------------------------

def _rotate(vertices, ax, ay, az):
    """Rotate vertices around X, Y, Z axes."""
    cos_x, sin_x = math.cos(ax), math.sin(ax)
    cos_y, sin_y = math.cos(ay), math.sin(ay)
    cos_z, sin_z = math.cos(az), math.sin(az)

    rotated = []
    for x, y, z in vertices:
        y1 = y * cos_x - z * sin_x
        z1 = y * sin_x + z * cos_x
        x2 = x * cos_y + z1 * sin_y
        z2 = -x * sin_y + z1 * cos_y
        x3 = x2 * cos_z - y1 * sin_z
        y3 = x2 * sin_z + y1 * cos_z
        rotated.append((x3, y3, z2))
    return rotated


def _project(vertices, scale=SCALE):
    """Project 3D vertices to 2D screen coordinates with perspective."""
    projected = []
    for x, y, z in vertices:
        depth = z + 3
        if depth < 0.5:
            depth = 0.5
        factor = scale / depth
        sx = int(CX + x * factor)
        sy = int(CY + y * factor)
        projected.append((sx, sy))
    return projected


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(matrix, duration=60):
    """Run the wireframe polygon display."""
    cfg = _load_config()
    shape_duration = cfg.get("seconds_per_shape", 10)
    speed_mult = cfg.get("rotation_speed", 1.0)

    # Build active shape list from config
    enabled_shapes = cfg.get("shapes", {})
    active = []
    for key in _SHAPE_ORDER:
        if enabled_shapes.get(key, True):
            if key in _SHAPE_REGISTRY:
                active.append(_SHAPE_REGISTRY[key])

    if not active:
        logger.warning("No wireframe shapes enabled, using all")
        active = [_SHAPE_REGISTRY[k] for k in _SHAPE_ORDER]

    start_time = time.time()
    ax, ay, az = 0.0, 0.0, 0.0

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()

            elapsed = time.time() - start_time
            shape_idx = int(elapsed / shape_duration) % len(active)

            name, shape_fn = active[shape_idx]
            vertices, edges, color = shape_fn()

            # -- Normalise so every shape has the same bounding radius --
            vertices = _normalise(vertices)

            rotated = _rotate(vertices, ax, ay, az)
            projected = _project(rotated)

            image = Image.new("RGB", (WIDTH, HEIGHT), (2, 2, 6))
            draw = ImageDraw.Draw(image)

            # Draw edges with depth-based brightness
            for i, j in edges:
                if i < len(projected) and j < len(projected):
                    x1, y1 = projected[i]
                    x2, y2 = projected[j]

                    z_avg = (rotated[i][2] + rotated[j][2]) / 2
                    brightness = max(0.3, min(1.0, 0.7 - z_avg * 0.2))

                    r = int(color[0] * brightness)
                    g = int(color[1] * brightness)
                    b = int(color[2] * brightness)

                    draw.line([(x1, y1), (x2, y2)], fill=(r, g, b))

            # Draw vertices as bright dots
            for idx, (sx, sy) in enumerate(projected):
                if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
                    z = rotated[idx][2]
                    dot_bright = max(0.5, min(1.0, 0.8 - z * 0.15))
                    r = min(255, int(color[0] * dot_bright * 1.3))
                    g = min(255, int(color[1] * dot_bright * 1.3))
                    b = min(255, int(color[2] * dot_bright * 1.3))
                    draw.point((sx, sy), fill=(r, g, b))

            # Shape name at bottom
            try:
                from PIL import ImageFont
                font = ImageFont.load_default()
                tx = (WIDTH - len(name) * 6) // 2
                draw.text((tx, HEIGHT - 9), name, fill=(60, 60, 80), font=font)
            except Exception:
                pass

            matrix.SetImage(image)

            ax += 0.03 * speed_mult
            ay += 0.05 * speed_mult
            az += 0.02 * speed_mult

            frame_elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - frame_elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in wireframe: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
