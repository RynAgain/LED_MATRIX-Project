"""
Rubik's Cube -- 3D rotating Rubik's cube demo for 64x64 LED matrix.

Renders a solid-faced 3×3 Rubik's cube with perspective projection that
slowly rotates in 3D space. Periodically performs face rotations (scramble
then solve) for visual interest. The cube takes up ~60-70% of the display.

Features:
- Solid colored faces with visible grid lines
- Smooth 3D rotation (tumbling on multiple axes)
- Face-turn animations (quarter turns with smooth interpolation)
- Scramble sequence followed by reverse solve
- Painter's algorithm for correct face ordering
- No dependencies beyond PIL (pure math projection)
"""

import time
import math
import random
import logging
from PIL import Image, ImageDraw
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
CX, CY = WIDTH // 2, HEIGHT // 2
FRAME_INTERVAL = 1.0 / 24  # 24 FPS
CUBE_SCALE = 20  # Cube half-size in pixels (~40px total = 62% of 64)

# Face colors (classic Rubik's scheme)
FACE_COLORS = {
    'U': (255, 255, 255),   # White (up)
    'D': (255, 220, 0),     # Yellow (down)
    'F': (200, 0, 0),       # Red (front)
    'B': (255, 100, 0),     # Orange (back)
    'L': (0, 100, 200),     # Blue (left)
    'R': (0, 180, 0),       # Green (right)
}

# Grid line color (dark, visible between stickers)
GRID_COLOR = (10, 10, 10)
BG_COLOR = (0, 0, 0)

# Face definitions: each face has 9 stickers (3x3 grid)
# Face normals and orientations for constructing 3D geometry
FACE_DEFS = {
    'F': {'normal': (0, 0, 1), 'up': (0, -1, 0), 'right': (1, 0, 0)},
    'B': {'normal': (0, 0, -1), 'up': (0, -1, 0), 'right': (-1, 0, 0)},
    'U': {'normal': (0, -1, 0), 'up': (0, 0, -1), 'right': (1, 0, 0)},
    'D': {'normal': (0, 1, 0), 'up': (0, 0, 1), 'right': (1, 0, 0)},
    'R': {'normal': (1, 0, 0), 'up': (0, -1, 0), 'right': (0, 0, -1)},
    'L': {'normal': (-1, 0, 0), 'up': (0, -1, 0), 'right': (0, 0, 1)},
}


# ---------------------------------------------------------------------------
# Turn permutations, derived from geometry
# ---------------------------------------------------------------------------
# Each sticker slot (face, row, col) has an exact integer 3D center
# (scaled x3 so 0.66 offsets become the integer 2) and an outward normal --
# the SAME geometry get_sticker_quads() renders from.  A quarter turn of
# face F rotates every sticker in F's layer (dot(center, F.normal) >= 2)
# by +/-90 degrees about that normal; the destination slot is the unique
# slot whose (center, normal) matches the rotated pair.  Deriving the
# tables this way makes every move a bijection on the 54 stickers by
# construction -- the previous hand-written edge cycles were wrong for
# several faces and produced impossible sticker states.

def _turn_rot90(v, n, sign):
    """Rotate integer vector v a quarter turn about unit axis n.
    sign +1: v' = n x v + n(n.v);  sign -1: the inverse rotation."""
    d = n[0] * v[0] + n[1] * v[1] + n[2] * v[2]
    if sign > 0:
        c = (n[1] * v[2] - n[2] * v[1],
             n[2] * v[0] - n[0] * v[2],
             n[0] * v[1] - n[1] * v[0])
    else:
        c = (v[1] * n[2] - v[2] * n[1],
             v[2] * n[0] - v[0] * n[2],
             v[0] * n[1] - v[1] * n[0])
    return (c[0] + n[0] * d, c[1] + n[1] * d, c[2] + n[2] * d)


def _sticker_center(fdef, row, col):
    n, u, r = fdef['normal'], fdef['up'], fdef['right']
    return tuple(3 * n[i] + 2 * (col - 1) * r[i] + 2 * (row - 1) * u[i]
                 for i in range(3))


def _build_turn_perms():
    slots = {}   # (face,row,col) -> (center, normal)
    lookup = {}  # (center, normal) -> (face,row,col)
    for fname, fdef in FACE_DEFS.items():
        for row in range(3):
            for col in range(3):
                key = (fname, row, col)
                geo = (_sticker_center(fdef, row, col), fdef['normal'])
                slots[key] = geo
                lookup[geo] = key
    perms = {}
    for fname, fdef in FACE_DEFS.items():
        axis = fdef['normal']
        for cw in (True, False):
            sign = -1 if cw else 1
            mapping = {}  # dst -> src
            for src, (c, sn) in slots.items():
                if sum(c[i] * axis[i] for i in range(3)) < 2:
                    continue  # not in this face's layer
                dst = lookup[(_turn_rot90(c, axis, sign),
                              _turn_rot90(sn, axis, sign))]
                mapping[dst] = src
            assert len(mapping) == 21  # 9 face + 12 band stickers
            perms[(fname, cw)] = mapping
    return perms


TURN_PERMS = _build_turn_perms()


# ---------------------------------------------------------------------------
# 3D math helpers
# ---------------------------------------------------------------------------

def _rotate_x(point, angle):
    x, y, z = point
    c, s = math.cos(angle), math.sin(angle)
    return (x, y * c - z * s, y * s + z * c)


def _rotate_y(point, angle):
    x, y, z = point
    c, s = math.cos(angle), math.sin(angle)
    return (x * c + z * s, y, -x * s + z * c)


def _rotate_z(point, angle):
    x, y, z = point
    c, s = math.cos(angle), math.sin(angle)
    return (x * c - y * s, x * s + y * c, z)


def _project(point):
    """Perspective projection from 3D to 2D screen coords."""
    x, y, z = point
    # Simple perspective: objects further away appear smaller
    fov = 3.5
    z_offset = fov + z * 0.02  # Prevent division issues
    if z_offset < 0.5:
        z_offset = 0.5
    scale = fov / z_offset * CUBE_SCALE
    sx = int(CX + x * scale)
    sy = int(CY + y * scale)
    return (sx, sy)


def _face_z_center(corners):
    """Get average Z of a face's corners (for sorting)."""
    return sum(c[2] for c in corners) / len(corners)


# ---------------------------------------------------------------------------
# Cube state
# ---------------------------------------------------------------------------

class RubiksCube:
    """3x3 Rubik's cube with face colors and rotation state."""

    def __init__(self):
        # Each face stores a 3x3 grid of color keys
        self.faces = {}
        for face_name in FACE_DEFS:
            self.faces[face_name] = [[face_name] * 3 for _ in range(3)]

        # Rotation angles
        self.rot_x = 0.45  # Initial tilt for nice 3D view
        self.rot_y = 0.35
        self.rot_z = 0.0

        # Face turn animation state
        self.turning_face = None
        self.turning_cw = True
        self.turn_angle = 0.0
        self.turn_target = 0.0
        self.turn_speed = 0.08
        self.turn_history = []  # for undo/solve

        # Scramble/solve state
        self.mode = 'rotate'  # 'rotate', 'scramble', 'solve'
        self.scramble_moves = []
        self.scramble_idx = 0
        self.mode_timer = 0

    def apply_move(self, face_name, clockwise=True):
        """Apply a quarter turn using the geometry-derived permutation."""
        old = {f: [row[:] for row in self.faces[f]] for f in self.faces}
        for (df, dr, dc), (sf, sr, sc) in TURN_PERMS[(face_name, clockwise)].items():
            self.faces[df][dr][dc] = old[sf][sr][sc]

    def get_sticker_quads(self):
        """Generate all visible sticker quads in 3D space.

        Returns list of (corners_3d, color) where corners_3d is 4 points.
        """
        quads = []
        sticker_size = 0.28  # Size of each sticker relative to face

        # Mid-turn: rotate the turning slice's stickers by the animated
        # angle about the turn axis.  Same rotation (and sign) as the state
        # permutation in apply_move, so the animation ends exactly where
        # the sticker state snaps to.  Previously the turn animation was
        # never rendered at all -- stickers teleported when the invisible
        # timer completed.
        turn = None
        if self.turning_face is not None:
            axis = FACE_DEFS[self.turning_face]['normal']
            ang = -self.turn_angle if self.turning_cw else self.turn_angle
            turn = (axis, math.cos(ang), math.sin(ang))

        for face_name, fdef in FACE_DEFS.items():
            nx, ny, nz = fdef['normal']
            ux, uy, uz = fdef['up']
            rx, ry, rz = fdef['right']

            for row in range(3):
                for col in range(3):
                    color_key = self.faces[face_name][row][col]
                    color = FACE_COLORS[color_key]

                    # Sticker center on face (range -1 to 1)
                    sc = (col - 1) * 0.66
                    sr = (row - 1) * 0.66

                    # Center point of this sticker in 3D
                    cx = nx + sc * rx + sr * ux
                    cy = ny + sc * ry + sr * uy
                    cz = nz + sc * rz + sr * uz

                    # Four corners of the sticker
                    corners = []
                    for dr, dc in [(-1, -1), (-1, 1), (1, 1), (1, -1)]:
                        px = cx + (dc * sticker_size * rx + dr * sticker_size * ux)
                        py = cy + (dc * sticker_size * ry + dr * sticker_size * uy)
                        pz = cz + (dc * sticker_size * rz + dr * sticker_size * uz)
                        corners.append((px, py, pz))

                    if turn is not None:
                        icen = _sticker_center(fdef, row, col)
                        ax = turn[0]
                        if (icen[0] * ax[0] + icen[1] * ax[1]
                                + icen[2] * ax[2]) >= 2:
                            ca, sa = turn[1], turn[2]
                            rot = []
                            for vx, vy, vz in corners:
                                d = ax[0] * vx + ax[1] * vy + ax[2] * vz
                                crx = ax[1] * vz - ax[2] * vy
                                cry = ax[2] * vx - ax[0] * vz
                                crz = ax[0] * vy - ax[1] * vx
                                rot.append((
                                    vx * ca + crx * sa + ax[0] * d * (1 - ca),
                                    vy * ca + cry * sa + ax[1] * d * (1 - ca),
                                    vz * ca + crz * sa + ax[2] * d * (1 - ca),
                                ))
                            corners = rot

                    quads.append((corners, color))

        return quads

    def update(self):
        """Update cube rotation and face-turn animation."""
        # Slow continuous tumble
        self.rot_y += 0.012
        self.rot_x += 0.007

        # Mode logic
        self.mode_timer += 1

        if self.mode == 'rotate':
            # Just tumble for a while, then start scramble
            if self.mode_timer > 120:  # ~5 seconds at 24fps
                self.mode = 'scramble'
                self.mode_timer = 0
                faces = list(FACE_DEFS.keys())
                self.scramble_moves = [(random.choice(faces), random.choice([True, False]))
                                       for _ in range(8)]
                self.scramble_idx = 0
                self.turn_history = []

        elif self.mode == 'scramble':
            if self.turning_face is None:
                if self.scramble_idx < len(self.scramble_moves):
                    face, cw = self.scramble_moves[self.scramble_idx]
                    self.turning_face = face
                    self.turning_cw = cw
                    self.turn_angle = 0.0
                    self.turn_target = math.pi / 2
                    self.turn_history.append((face, cw))
                    self.scramble_idx += 1
                else:
                    # Done scrambling, pause then solve
                    if self.mode_timer > 30:
                        self.mode = 'solve'
                        self.mode_timer = 0
                        self.scramble_idx = len(self.turn_history) - 1
            else:
                # Animate turn
                self.turn_angle += self.turn_speed
                if self.turn_angle >= self.turn_target:
                    # Snap: the state permutation lands exactly where the
                    # animated slice ends because both use the same rotation.
                    self.apply_move(self.turning_face, self.turning_cw)
                    self.turning_face = None

        elif self.mode == 'solve':
            if self.turning_face is None:
                if self.scramble_idx >= 0:
                    face, cw = self.turn_history[self.scramble_idx]
                    self.turning_face = face
                    self.turning_cw = not cw  # reverse move
                    self.turn_angle = 0.0
                    self.turn_target = math.pi / 2
                    self.scramble_idx -= 1
                else:
                    # Done solving, go back to rotate
                    if self.mode_timer > 60:
                        self.mode = 'rotate'
                        self.mode_timer = 0
            else:
                self.turn_angle += self.turn_speed
                if self.turn_angle >= self.turn_target:
                    self.apply_move(self.turning_face, self.turning_cw)
                    self.turning_face = None

    def draw(self):
        """Render the cube to a PIL Image."""
        image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(image)

        quads = self.get_sticker_quads()

        # Transform all quads by current rotation (trig precomputed once)
        cx, sx = math.cos(self.rot_x), math.sin(self.rot_x)
        cy, sy = math.cos(self.rot_y), math.sin(self.rot_y)
        cz, sz = math.cos(self.rot_z), math.sin(self.rot_z)
        transformed = []
        for corners, color in quads:
            rotated_corners = []
            for p in corners:
                x, y, z = p
                y, z = y * cx - z * sx, y * sx + z * cx
                x, z = x * cy + z * sy, -x * sy + z * cy
                x, y = x * cz - y * sz, x * sz + y * cz
                rotated_corners.append((x, y, z))

            # Back-face culling: only draw faces pointing toward camera
            # Normal = cross product of two edges
            e1 = (rotated_corners[1][0] - rotated_corners[0][0],
                  rotated_corners[1][1] - rotated_corners[0][1],
                  rotated_corners[1][2] - rotated_corners[0][2])
            e2 = (rotated_corners[2][0] - rotated_corners[0][0],
                  rotated_corners[2][1] - rotated_corners[0][1],
                  rotated_corners[2][2] - rotated_corners[0][2])
            normal_z = e1[0] * e2[1] - e1[1] * e2[0]

            if normal_z < 0:  # Facing camera
                z_depth = _face_z_center(rotated_corners)
                projected = [_project(p) for p in rotated_corners]
                # Darken based on depth for pseudo-lighting
                z_avg = sum(p[2] for p in rotated_corners) / 4
                light = max(0.4, min(1.0, 0.7 - z_avg * 0.15))
                lit_color = tuple(int(c * light) for c in color)
                transformed.append((z_depth, projected, lit_color))

        # Painter's algorithm: draw far faces first
        transformed.sort(key=lambda t: t[0], reverse=True)

        for _, projected, color in transformed:
            # Draw filled quad
            draw.polygon(projected, fill=color, outline=GRID_COLOR)

        return image


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(matrix, duration=60, controller=None):
    """Run the Rubik's cube demo.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds.
        controller: Unused (demo-only display).
    """
    start_time = time.time()
    cube = RubiksCube()

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break

            cube.update()
            image = cube.draw()
            matrix.SetImage(image)
            time.sleep(FRAME_INTERVAL)

    except Exception as e:
        logger.error("Error in rubiks_cube: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
