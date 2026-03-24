#!/usr/bin/env python3
"""3D ball rolling over procedural terrain with hills and valleys.

A shaded sphere rolls across a heightmap-based landscape rendered in
pseudo-3D perspective. The ball obeys gravity -- accelerating downhill
and decelerating uphill. The camera tracks the ball from behind.
New terrain is generated continuously as the ball rolls forward.
"""

import math
import random
import time
import logging
from PIL import Image, ImageDraw
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 30

# Terrain generation
TERRAIN_W = 80       # Width of the heightmap in samples
TERRAIN_D = 120      # Depth of the heightmap in samples
TILE_SIZE = 1.0      # World units per grid cell

# Rendering
VIEW_COLS = 64       # Columns to render
VIEW_ROWS = 40       # Rows of terrain depth to draw
CAM_HEIGHT = 6.0     # Camera height above terrain
CAM_DIST = 8.0       # Camera distance behind ball
HORIZON_Y = 18       # Screen Y of the horizon line

# Physics
GRAVITY = 12.0       # Gravity factor for slope acceleration
FRICTION = 0.92      # Velocity damping per frame
BALL_RADIUS = 0.6    # World-space ball radius

# Colour palette for terrain heights
_TERRAIN_COLORS = [
    (-2.0, (20, 50, 120)),   # Deep water -- dark blue
    (-0.5, (30, 80, 160)),   # Shallow water -- blue
    (0.0,  (50, 140, 60)),   # Lowland -- green
    (1.5,  (100, 160, 50)),  # Grassland -- yellow-green
    (3.0,  (140, 120, 60)),  # Hills -- brown
    (5.0,  (180, 170, 160)), # Mountain -- grey
    (7.0,  (240, 240, 255)), # Peak -- white
]


# ---------------------------------------------------------------------------
# Procedural heightmap  (layered sine noise)
# ---------------------------------------------------------------------------

class _Terrain:
    """Procedural terrain heightmap using layered sinusoidal noise."""

    def __init__(self, seed=None):
        rng = random.Random(seed)
        # Generate several octaves of sine-based noise
        self._octaves = []
        for _ in range(5):
            freq_x = rng.uniform(0.05, 0.25)
            freq_z = rng.uniform(0.05, 0.25)
            phase_x = rng.uniform(0, 2 * math.pi)
            phase_z = rng.uniform(0, 2 * math.pi)
            amp = rng.uniform(0.5, 2.5)
            self._octaves.append((freq_x, freq_z, phase_x, phase_z, amp))

    def height(self, wx, wz):
        """Get terrain height at world coordinates (wx, wz)."""
        h = 0.0
        for fx, fz, px, pz, amp in self._octaves:
            h += amp * math.sin(wx * fx + px) * math.cos(wz * fz + pz)
        return h

    def normal(self, wx, wz, eps=0.1):
        """Approximate surface normal at (wx, wz) via finite differences."""
        hc = self.height(wx, wz)
        hx = self.height(wx + eps, wz)
        hz = self.height(wx, wz + eps)
        # Normal = cross product of tangent vectors
        nx = -(hx - hc) / eps
        nz = -(hz - hc) / eps
        ny = 1.0
        length = math.sqrt(nx * nx + ny * ny + nz * nz)
        if length < 1e-6:
            return 0.0, 1.0, 0.0
        return nx / length, ny / length, nz / length

    def slope(self, wx, wz, dx, dz):
        """Return the downhill slope component in direction (dx, dz)."""
        eps = 0.15
        h0 = self.height(wx, wz)
        h1 = self.height(wx + dx * eps, wz + dz * eps)
        return -(h1 - h0) / eps


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _terrain_color(h):
    """Map a terrain height to an RGB colour via the palette."""
    if h <= _TERRAIN_COLORS[0][0]:
        return _TERRAIN_COLORS[0][1]
    if h >= _TERRAIN_COLORS[-1][0]:
        return _TERRAIN_COLORS[-1][1]
    for i in range(len(_TERRAIN_COLORS) - 1):
        h0, c0 = _TERRAIN_COLORS[i]
        h1, c1 = _TERRAIN_COLORS[i + 1]
        if h0 <= h <= h1:
            t = (h - h0) / (h1 - h0)
            r = int(c0[0] + (c1[0] - c0[0]) * t)
            g = int(c0[1] + (c1[1] - c0[1]) * t)
            b = int(c0[2] + (c1[2] - c0[2]) * t)
            return (r, g, b)
    return _TERRAIN_COLORS[-1][1]


def _shade(color, factor):
    """Apply a brightness factor to an RGB tuple."""
    return (
        max(0, min(255, int(color[0] * factor))),
        max(0, min(255, int(color[1] * factor))),
        max(0, min(255, int(color[2] * factor))),
    )


# ---------------------------------------------------------------------------
# Ball physics
# ---------------------------------------------------------------------------

class _Ball:
    """Ball that rolls over terrain obeying gravity."""

    def __init__(self, terrain, x=0.0, z=0.0):
        self.terrain = terrain
        self.x = x
        self.z = z
        self.vx = 0.0
        self.vz = 2.0  # Initial forward velocity
        self.y = terrain.height(x, z) + BALL_RADIUS

    def update(self, dt):
        # Slope forces
        slope_x = self.terrain.slope(self.x, self.z, 1.0, 0.0)
        slope_z = self.terrain.slope(self.x, self.z, 0.0, 1.0)

        self.vx += slope_x * GRAVITY * dt
        self.vz += slope_z * GRAVITY * dt

        # Minimum forward speed so the ball always moves
        speed = math.sqrt(self.vx * self.vx + self.vz * self.vz)
        if speed < 1.5:
            self.vz = max(self.vz, 1.5)

        # Friction
        self.vx *= FRICTION
        self.vz *= FRICTION

        # Clamp max speed
        speed = math.sqrt(self.vx * self.vx + self.vz * self.vz)
        max_speed = 8.0
        if speed > max_speed:
            scale = max_speed / speed
            self.vx *= scale
            self.vz *= scale

        # Move
        self.x += self.vx * dt
        self.z += self.vz * dt

        # Ground height
        self.y = self.terrain.height(self.x, self.z) + BALL_RADIUS


# ---------------------------------------------------------------------------
# 3D Rendering
# ---------------------------------------------------------------------------

def _project(wx, wy, wz, cam_x, cam_y, cam_z):
    """Project world point to screen coordinates relative to camera."""
    # Camera looks along +Z
    rx = wx - cam_x
    ry = wy - cam_y
    rz = wz - cam_z

    if rz < 0.5:
        return None  # Behind camera

    # Perspective
    fov_scale = 40.0
    sx = int(WIDTH // 2 + rx * fov_scale / rz)
    sy = int(HORIZON_Y - ry * fov_scale / rz)

    return sx, sy


def _render_terrain(image, draw, terrain, cam_x, cam_y, cam_z):
    """Render terrain as coloured horizontal scanlines (back to front)."""
    # Draw sky gradient
    for y in range(HORIZON_Y + 1):
        t = y / max(HORIZON_Y, 1)
        r = int(8 + 20 * t)
        g = int(8 + 15 * t)
        b = int(30 + 40 * t)
        draw.line([(0, y), (WIDTH - 1, y)], fill=(r, g, b))

    # Render terrain rows from far to near
    for row_i in range(VIEW_ROWS, 0, -1):
        wz = cam_z + row_i * 0.8  # World Z for this row
        depth_factor = max(0.25, 1.0 - row_i / VIEW_ROWS)

        prev_sx = None
        prev_sy = None
        prev_color = None

        for col_i in range(VIEW_COLS + 1):
            wx = cam_x + (col_i - VIEW_COLS // 2) * 0.6
            wy = terrain.height(wx, wz)

            proj = _project(wx, wy, wz, cam_x, cam_y, cam_z)
            if proj is None:
                prev_sx = None
                continue

            sx, sy = proj
            base_color = _terrain_color(wy)

            # Simple directional lighting
            nx, ny, nz = terrain.normal(wx, wz)
            light = max(0.3, min(1.0, ny * 0.7 + 0.3))
            color = _shade(base_color, light * depth_factor)

            if prev_sx is not None and prev_color is not None:
                # Fill column between previous and current
                if 0 <= prev_sx < WIDTH or 0 <= sx < WIDTH:
                    # Draw a line segment for this terrain strip
                    clamped_sy = max(0, min(HEIGHT - 1, sy))
                    clamped_prev_sy = max(0, min(HEIGHT - 1, prev_sy))
                    for fill_y in range(min(clamped_sy, clamped_prev_sy), HEIGHT):
                        mid_x = (prev_sx + sx) // 2
                        if 0 <= mid_x < WIDTH and 0 <= fill_y < HEIGHT:
                            existing = image.getpixel((mid_x, fill_y))
                            # Only draw if closer (simple painter's algo)
                            if existing == (0, 0, 0) or fill_y >= HORIZON_Y:
                                image.putpixel((mid_x, fill_y), color)

            prev_sx = sx
            prev_sy = sy
            prev_color = color


def _render_terrain_fast(image, terrain, cam_x, cam_y, cam_z):
    """Fast terrain renderer using column-based projection."""
    pixels = image.load()

    # Sky gradient
    for y in range(HEIGHT):
        if y <= HORIZON_Y:
            t = y / max(HORIZON_Y, 1)
            r = int(5 + 15 * t)
            g = int(5 + 10 * t)
            b = int(20 + 40 * t)
            for x in range(WIDTH):
                pixels[x, y] = (r, g, b)

    # For each screen column, cast through terrain rows front-to-back
    for sx in range(WIDTH):
        max_sy = HEIGHT  # Track lowest drawn pixel (from bottom)

        for row_i in range(1, VIEW_ROWS + 1):
            rz = row_i * 0.6
            wz = cam_z + rz
            wx = cam_x + (sx - WIDTH // 2) * rz / 40.0

            wy = terrain.height(wx, wz)
            ry = wy - cam_y
            if rz < 0.5:
                continue

            fov_scale = 40.0
            sy = int(HORIZON_Y - ry * fov_scale / rz)
            sy = max(0, min(HEIGHT - 1, sy))

            if sy < max_sy:
                # Determine colour
                base_color = _terrain_color(wy)
                depth_factor = max(0.3, 1.0 - rz / (VIEW_ROWS * 0.6))
                nx, ny_n, nz = terrain.normal(wx, wz, eps=0.3)
                light = max(0.3, min(1.0, ny_n * 0.6 + 0.4))
                color = _shade(base_color, light * depth_factor)

                for fill_y in range(sy, max_sy):
                    if 0 <= fill_y < HEIGHT:
                        pixels[sx, fill_y] = color

                max_sy = sy


def _render_ball(image, draw, ball, cam_x, cam_y, cam_z):
    """Render the ball as a shaded circle."""
    proj = _project(ball.x, ball.y, ball.z, cam_x, cam_y, cam_z)
    if proj is None:
        return

    sx, sy = proj
    rz = ball.z - cam_z
    if rz < 0.5:
        return

    # Screen-space radius
    screen_r = max(2, int(BALL_RADIUS * 40.0 / rz))

    # Draw shaded sphere
    for dy in range(-screen_r, screen_r + 1):
        for dx in range(-screen_r, screen_r + 1):
            dist_sq = dx * dx + dy * dy
            if dist_sq <= screen_r * screen_r:
                px = sx + dx
                py = sy + dy
                if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                    # Spherical shading
                    nz_ball = math.sqrt(max(0, 1.0 - dist_sq / (screen_r * screen_r)))
                    light = max(0.3, nz_ball * 0.7 + (-dx / (screen_r + 1)) * 0.2 + 0.3)
                    r = min(255, int(220 * light))
                    g = min(255, int(60 * light))
                    b = min(255, int(60 * light))
                    image.putpixel((px, py), (r, g, b))

    # Highlight
    hx = sx - screen_r // 3
    hy = sy - screen_r // 3
    if 0 <= hx < WIDTH and 0 <= hy < HEIGHT and screen_r >= 3:
        image.putpixel((hx, hy), (255, 200, 200))


def _render_shadow(image, ball, cam_x, cam_y, cam_z, terrain):
    """Render ball shadow on terrain."""
    ground_y = terrain.height(ball.x, ball.z)
    proj = _project(ball.x, ground_y, ball.z, cam_x, cam_y, cam_z)
    if proj is None:
        return

    sx, sy = proj
    rz = ball.z - cam_z
    if rz < 0.5:
        return

    shadow_r = max(1, int(BALL_RADIUS * 30.0 / rz))

    for dy in range(-shadow_r, shadow_r + 1):
        for dx in range(-shadow_r - 1, shadow_r + 2):
            if dx * dx + dy * dy <= (shadow_r + 1) * (shadow_r + 1):
                px = sx + dx
                py = sy + dy
                if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                    c = image.getpixel((px, py))
                    # Darken existing pixel
                    image.putpixel((px, py), (c[0] // 2, c[1] // 2, c[2] // 2))


# ---------------------------------------------------------------------------
# Trail effect
# ---------------------------------------------------------------------------

class _Trail:
    """Stores recent ball positions for a fading trail effect."""

    def __init__(self, max_len=30):
        self.positions = []
        self.max_len = max_len

    def add(self, x, z):
        self.positions.append((x, z))
        if len(self.positions) > self.max_len:
            self.positions.pop(0)

    def render(self, image, terrain, cam_x, cam_y, cam_z):
        for i, (tx, tz) in enumerate(self.positions):
            ty = terrain.height(tx, tz) + 0.05
            proj = _project(tx, ty, tz, cam_x, cam_y, cam_z)
            if proj is None:
                continue
            sx, sy = proj
            if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
                alpha = i / len(self.positions)
                c = image.getpixel((sx, sy))
                r = min(255, int(c[0] * 0.7 + 80 * alpha))
                g = min(255, int(c[1] * 0.7 + 20 * alpha))
                b = min(255, int(c[2] * 0.7 + 20 * alpha))
                image.putpixel((sx, sy), (r, g, b))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(matrix, duration=60):
    """Run the 3D terrain ball roller display."""
    start_time = time.time()
    terrain = _Terrain(seed=random.randint(0, 99999))
    ball = _Ball(terrain, x=0.0, z=5.0)
    trail = _Trail(max_len=25)
    trail_timer = 0.0

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            dt = FRAME_INTERVAL

            # Regenerate terrain every 45 seconds for variety
            elapsed = time.time() - start_time
            if int(elapsed) % 45 == 0 and int(elapsed) > 0 and abs(elapsed - int(elapsed)) < dt:
                terrain = _Terrain(seed=random.randint(0, 99999))
                ball.terrain = terrain

            ball.update(dt)

            # Trail
            trail_timer += dt
            if trail_timer >= 0.1:
                trail.add(ball.x, ball.z)
                trail_timer = 0.0

            # Camera follows ball from behind
            cam_x = ball.x
            cam_z = ball.z - CAM_DIST
            cam_y = ball.y + CAM_HEIGHT

            # Render
            image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))

            _render_terrain_fast(image, terrain, cam_x, cam_y, cam_z)
            trail.render(image, terrain, cam_x, cam_y, cam_z)
            _render_shadow(image, ball, cam_x, cam_y, cam_z, terrain)
            _render_ball(image, ImageDraw.Draw(image), ball, cam_x, cam_y, cam_z)

            matrix.SetImage(image)

            frame_elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - frame_elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in terrain_ball: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
