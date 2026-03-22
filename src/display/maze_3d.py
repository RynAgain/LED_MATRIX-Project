#!/usr/bin/env python3
"""First-person 3D maze raycaster for 64x64 LED matrix.

Wolfenstein 3D-style rendering of a procedurally generated maze.
An AI agent navigates using left-hand wall-following with smooth
camera interpolation. Regenerates a new maze when solved.
"""

import math
import random
import time
import logging
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 30
FOV = math.pi / 3          # 60-degree field of view
HALF_FOV = FOV / 2
MAX_DEPTH = 16.0            # Maximum ray cast distance
MOVE_SPEED = 3.0            # Grid cells per second for smooth interpolation
TURN_SPEED = math.pi * 1.5  # Radians per second for smooth turning

# Wall colours indexed by wall type (1-4)
WALL_COLORS = [
    (80, 40, 40),    # Type 0 fallback -- dark red
    (60, 120, 200),  # Type 1 -- blue
    (200, 80, 50),   # Type 2 -- orange-red
    (50, 180, 80),   # Type 3 -- green
    (180, 140, 50),  # Type 4 -- gold
]

# Ceiling / floor colours
CEIL_COLOR = (8, 8, 20)
FLOOR_COLOR = (15, 12, 10)


# ---------------------------------------------------------------------------
# Maze generation  (recursive back-tracker / DFS)
# ---------------------------------------------------------------------------

def _generate_maze(cols, rows):
    """Generate a maze grid. Returns 2D list where 0=path, 1-4=wall type.

    The grid has dimensions (2*rows+1) x (2*cols+1) so that walls occupy
    their own cells between path cells.
    """
    grid_h = 2 * rows + 1
    grid_w = 2 * cols + 1
    # Start with all walls -- assign random wall types 1-4
    grid = [[random.randint(1, 4) for _ in range(grid_w)] for _ in range(grid_h)]

    # Carve paths
    def _cell(r, c):
        return 2 * r + 1, 2 * c + 1

    visited = [[False] * cols for _ in range(rows)]
    stack = [(0, 0)]
    visited[0][0] = True
    r0, c0 = _cell(0, 0)
    grid[r0][c0] = 0

    while stack:
        cr, cc = stack[-1]
        neighbours = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = cr + dr, cc + dc
            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc]:
                neighbours.append((nr, nc, dr, dc))

        if not neighbours:
            stack.pop()
            continue

        nr, nc, dr, dc = random.choice(neighbours)
        visited[nr][nc] = True

        # Carve the wall between current and neighbour
        wr, wc = _cell(cr, cc)
        grid[wr + dr][wc + dc] = 0
        # Carve the neighbour cell
        nr2, nc2 = _cell(nr, nc)
        grid[nr2][nc2] = 0

        stack.append((nr, nc))

    return grid, grid_h, grid_w


def _find_start_end(grid, grid_h, grid_w):
    """Find a start position (top-left area) and end (bottom-right area)."""
    start = None
    end = None
    # Start: first open cell from top-left
    for r in range(grid_h):
        for c in range(grid_w):
            if grid[r][c] == 0:
                start = (r, c)
                break
        if start:
            break
    # End: first open cell from bottom-right
    for r in range(grid_h - 1, -1, -1):
        for c in range(grid_w - 1, -1, -1):
            if grid[r][c] == 0:
                end = (r, c)
                break
        if end:
            break
    return start, end


# ---------------------------------------------------------------------------
# Raycasting engine
# ---------------------------------------------------------------------------

def _cast_ray(grid, grid_h, grid_w, px, py, angle):
    """Cast a single ray and return (distance, wall_type, hit_side).

    hit_side: 0 = vertical wall face, 1 = horizontal wall face
    """
    sin_a = math.sin(angle)
    cos_a = math.cos(angle)

    # Avoid division by zero
    if abs(cos_a) < 1e-8:
        cos_a = 1e-8 if cos_a >= 0 else -1e-8
    if abs(sin_a) < 1e-8:
        sin_a = 1e-8 if sin_a >= 0 else -1e-8

    # --- Vertical intersections (stepping in x) ---
    x_step = 1 if cos_a > 0 else -1
    x_first = (int(px) + (1 if cos_a > 0 else 0)) - px
    v_dist = MAX_DEPTH
    v_type = 1
    t = x_first / cos_a
    dt = abs(1.0 / cos_a)
    for _ in range(int(MAX_DEPTH) + 1):
        if t > MAX_DEPTH:
            break
        hx = px + t * cos_a
        hy = py + t * sin_a
        # Map cell
        mx = int(hx) if cos_a > 0 else int(hx) - 1
        my = int(hy)
        if 0 <= my < grid_h and 0 <= mx < grid_w:
            if grid[my][mx] != 0:
                v_dist = t
                v_type = grid[my][mx]
                break
        elif mx < 0 or mx >= grid_w or my < 0 or my >= grid_h:
            break
        t += dt

    # --- Horizontal intersections (stepping in y) ---
    y_step = 1 if sin_a > 0 else -1
    y_first = (int(py) + (1 if sin_a > 0 else 0)) - py
    h_dist = MAX_DEPTH
    h_type = 1
    t = y_first / sin_a
    dt = abs(1.0 / sin_a)
    for _ in range(int(MAX_DEPTH) + 1):
        if t > MAX_DEPTH:
            break
        hx = px + t * cos_a
        hy = py + t * sin_a
        mx = int(hx)
        my = int(hy) if sin_a > 0 else int(hy) - 1
        if 0 <= my < grid_h and 0 <= mx < grid_w:
            if grid[my][mx] != 0:
                h_dist = t
                h_type = grid[my][mx]
                break
        elif mx < 0 or mx >= grid_w or my < 0 or my >= grid_h:
            break
        t += dt

    if v_dist < h_dist:
        return v_dist, v_type, 0
    else:
        return h_dist, h_type, 1


def _render_frame(image, draw, grid, grid_h, grid_w, px, py, angle):
    """Render the 3D view into the PIL image."""
    for col in range(WIDTH):
        ray_angle = angle - HALF_FOV + (col / WIDTH) * FOV
        dist, wall_type, hit_side = _cast_ray(grid, grid_h, grid_w, px, py, ray_angle)

        # Fix fish-eye distortion
        dist *= math.cos(ray_angle - angle)
        if dist < 0.1:
            dist = 0.1

        # Wall height
        wall_h = min(HEIGHT, int(HEIGHT / dist))
        top = (HEIGHT - wall_h) // 2
        bottom = top + wall_h

        # Base colour from wall type
        wt = wall_type if 0 <= wall_type < len(WALL_COLORS) else 0
        base_r, base_g, base_b = WALL_COLORS[wt]

        # Distance shading
        shade = max(0.15, 1.0 - dist / MAX_DEPTH)
        # Side shading (horizontal hits are darker)
        if hit_side == 1:
            shade *= 0.7

        r = int(base_r * shade)
        g = int(base_g * shade)
        b = int(base_b * shade)

        # Draw ceiling
        if top > 0:
            draw.line([(col, 0), (col, top - 1)], fill=CEIL_COLOR)
        # Draw wall column
        draw.line([(col, top), (col, bottom)], fill=(r, g, b))
        # Draw floor
        if bottom < HEIGHT:
            # Floor shading by distance from center
            for row in range(bottom + 1, HEIGHT):
                floor_dist = (row - HEIGHT // 2) / (HEIGHT // 2) if row != HEIGHT // 2 else 0.01
                fl_shade = max(0.15, min(0.8, abs(floor_dist)))
                fr = int(FLOOR_COLOR[0] * fl_shade)
                fg = int(FLOOR_COLOR[1] * fl_shade)
                fb = int(FLOOR_COLOR[2] * fl_shade)
                image.putpixel((col, row), (fr, fg, fb))


# ---------------------------------------------------------------------------
# Mini-map overlay
# ---------------------------------------------------------------------------

def _draw_minimap(image, grid, grid_h, grid_w, px, py, angle, visited_cells):
    """Draw a small minimap in the top-left corner."""
    map_size = 15  # pixels
    scale = map_size / max(grid_h, grid_w)

    for r in range(grid_h):
        for c in range(grid_w):
            mx = int(c * scale)
            my = int(r * scale)
            if mx >= map_size or my >= map_size:
                continue
            if grid[r][c] != 0:
                image.putpixel((mx, my), (30, 30, 50))
            elif (r, c) in visited_cells:
                image.putpixel((mx, my), (20, 40, 20))
            else:
                image.putpixel((mx, my), (10, 10, 10))

    # Player dot
    dot_x = int(px * scale)
    dot_y = int(py * scale)
    if 0 <= dot_x < map_size and 0 <= dot_y < map_size:
        image.putpixel((dot_x, dot_y), (255, 255, 0))


# ---------------------------------------------------------------------------
# AI Navigator  (left-hand wall-following)
# ---------------------------------------------------------------------------

# Directions: 0=North(-y), 1=East(+x), 2=South(+y), 3=West(-x)
_DIR_DELTA = [(0, -1), (1, 0), (0, 1), (-1, 0)]
_DIR_ANGLE = [3 * math.pi / 2, 0, math.pi / 2, math.pi]


def _can_walk(grid, grid_h, grid_w, cx, cy, direction):
    """Check if AI can move one step in direction from (cx,cy)."""
    dx, dy = _DIR_DELTA[direction]
    nx, ny = cx + dx, cy + dy
    if 0 <= nx < grid_w and 0 <= ny < grid_h:
        return grid[ny][nx] == 0
    return False


class _AINavigator:
    """Left-hand wall-following maze solver with smooth interpolation."""

    def __init__(self, start_x, start_y, direction=1):
        self.gx = start_x  # Grid position (column)
        self.gy = start_y  # Grid position (row)
        self.dir = direction  # 0-3
        self.px = start_x + 0.5  # Smooth world position
        self.py = start_y + 0.5
        self.angle = _DIR_ANGLE[self.dir]
        self.target_px = self.px
        self.target_py = self.py
        self.target_angle = self.angle
        self.moving = False
        self.visited = {(start_y, start_x)}

    def _left(self):
        return (self.dir - 1) % 4

    def _right(self):
        return (self.dir + 1) % 4

    def decide_next(self, grid, grid_h, grid_w):
        """Decide next movement using left-hand rule."""
        # Try: turn left, go straight, turn right, turn around
        left = self._left()
        if _can_walk(grid, grid_h, grid_w, self.gx, self.gy, left):
            self.dir = left
            self._step_forward(grid, grid_h, grid_w)
        elif _can_walk(grid, grid_h, grid_w, self.gx, self.gy, self.dir):
            self._step_forward(grid, grid_h, grid_w)
        elif _can_walk(grid, grid_h, grid_w, self.gx, self.gy, self._right()):
            self.dir = self._right()
            self._step_forward(grid, grid_h, grid_w)
        else:
            # Dead end, turn around
            self.dir = (self.dir + 2) % 4

        self.target_angle = _DIR_ANGLE[self.dir]
        self.moving = True

    def _step_forward(self, grid, grid_h, grid_w):
        dx, dy = _DIR_DELTA[self.dir]
        self.gx += dx
        self.gy += dy
        self.target_px = self.gx + 0.5
        self.target_py = self.gy + 0.5
        self.visited.add((self.gy, self.gx))

    def update(self, dt):
        """Interpolate position and angle toward target."""
        # Smooth position
        speed = MOVE_SPEED * dt
        dx = self.target_px - self.px
        dy = self.target_py - self.py
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 0.02:
            factor = min(1.0, speed / dist)
            self.px += dx * factor
            self.py += dy * factor
        else:
            self.px = self.target_px
            self.py = self.target_py

        # Smooth angle (handle wrapping)
        da = self.target_angle - self.angle
        # Normalize to [-pi, pi]
        while da > math.pi:
            da -= 2 * math.pi
        while da < -math.pi:
            da += 2 * math.pi
        turn = TURN_SPEED * dt
        if abs(da) > 0.02:
            self.angle += max(-turn, min(turn, da))
        else:
            self.angle = self.target_angle

        # Normalize angle to [0, 2*pi]
        self.angle = self.angle % (2 * math.pi)

        # Check if arrived
        pos_done = abs(self.px - self.target_px) < 0.02 and abs(self.py - self.target_py) < 0.02
        ang_done = abs(da) < 0.05
        if pos_done and ang_done:
            self.moving = False

    def reached(self, end_x, end_y):
        return self.gx == end_x and self.gy == end_y


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(matrix, duration=60):
    """Run the 3D maze raycaster display."""
    start_time = time.time()
    maze_cols, maze_rows = 6, 6  # Maze complexity (cells, not grid size)

    try:
        while time.time() - start_time < duration:
            # Generate a new maze
            grid, grid_h, grid_w = _generate_maze(maze_cols, maze_rows)
            start, end = _find_start_end(grid, grid_h, grid_w)
            if not start or not end or start == end:
                continue

            sr, sc = start
            er, ec = end

            # Mark end with a special floor marker (we'll draw it in minimap)
            nav = _AINavigator(sc, sr, direction=1)
            decision_timer = 0.0
            decision_interval = 0.5  # Seconds between AI decisions

            maze_start = time.time()
            maze_timeout = 60  # Max seconds per maze before regenerating

            while time.time() - start_time < duration:
                frame_start = time.time()

                # AI logic
                dt = FRAME_INTERVAL
                decision_timer += dt

                if not nav.moving and decision_timer >= decision_interval:
                    decision_timer = 0.0
                    if nav.reached(ec, er):
                        # Maze solved! Flash briefly then new maze
                        _flash_solved(matrix)
                        break
                    nav.decide_next(grid, grid_h, grid_w)

                nav.update(dt)

                # Timeout -- regenerate
                if time.time() - maze_start > maze_timeout:
                    break

                # Render
                image = Image.new("RGB", (WIDTH, HEIGHT), CEIL_COLOR)
                draw = ImageDraw.Draw(image)

                _render_frame(image, draw, grid, grid_h, grid_w,
                              nav.px, nav.py, nav.angle)

                # Draw minimap
                _draw_minimap(image, grid, grid_h, grid_w,
                              nav.px, nav.py, nav.angle, nav.visited)

                # End marker on minimap
                emx = int(ec * (15 / max(grid_h, grid_w)))
                emy = int(er * (15 / max(grid_h, grid_w)))
                if 0 <= emx < 15 and 0 <= emy < 15:
                    image.putpixel((emx, emy), (255, 50, 50))

                matrix.SetImage(image)

                frame_elapsed = time.time() - frame_start
                sleep_time = FRAME_INTERVAL - frame_elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in maze_3d: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass


def _flash_solved(matrix):
    """Brief green flash when maze is solved."""
    for brightness in [80, 160, 255, 160, 80, 0]:
        image = Image.new("RGB", (WIDTH, HEIGHT), (0, brightness, 0))
        try:
            from PIL import ImageDraw as ID2, ImageFont
            d = ID2.Draw(image)
            font = ImageFont.load_default()
            d.text((12, 28), "SOLVED", fill=(255, 255, 255), font=font)
        except Exception:
            pass
        matrix.SetImage(image)
        time.sleep(0.08)
