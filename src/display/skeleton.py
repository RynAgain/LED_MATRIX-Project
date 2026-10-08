#!/usr/bin/env python3
"""Dancing skeleton for a 64x64 LED matrix.

A skeleton dances in a moonlit graveyard: a beat clock (``BPM``) drives a
handful of choreographed moves (sway, arms up, twist, kicks, hops, floss)
that swap every few bars, its jaw chatters on the beat, and its eye
sockets glow.

The skeleton is procedural, not sprite art: :class:`SkeletonState` holds a
pose of scalars (hip offset, torso lean, per-limb angles) that each move
writes as a *target*; the live pose eases toward that target every frame,
so a move change never snaps. :func:`joints` turns a pose into panel
coordinates and is the only place kinematics live.

Rendering follows the same split as ``pumpkin.py``: the sky, moon and
graveyard never change and are pre-rendered once into a base layer; each
frame only draws the shadow and the bones on a copy of it. State is pure
``dt`` arithmetic with no drawing calls, so long soaks are testable
headlessly.
"""

import time
import math
import random
import logging

from PIL import Image, ImageDraw

from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 24

# --- Scene ---------------------------------------------------------------
SKY_TOP = (5, 4, 14)
SKY_BOTTOM = (24, 14, 34)
MOON_CENTER = (12, 11)
MOON_R = 6
MOON_COLOR = (240, 238, 212)
MOON_SHADOW = (196, 192, 164)
STAR_COLOR = (255, 255, 240)
GROUND_Y = 56
GROUND = (26, 30, 24)
GROUND_EDGE = (44, 52, 38)
GRAVE = (72, 74, 78)
GRAVE_SHADE = (46, 48, 52)
SHADOW = (14, 16, 14)
STARS = [
    (5, 24, 0.0), (20, 5, 1.1), (29, 12, 2.3), (40, 4, 0.4),
    (58, 9, 3.1), (48, 18, 1.7), (34, 23, 2.8), (62, 30, 0.9),
    (2, 33, 4.2), (25, 30, 5.0),
]

# --- Bones ---------------------------------------------------------------
BONE = (234, 230, 214)
BONE_SHADE = (150, 146, 132)
SOCKET = (14, 12, 10)
EYE_GLOW = (255, 146, 34)

CX = 32.0                  # hips rest here, sway is measured from it
HIP_Y = 38.0
SPINE_LEN = 12.0
SKULL_R = 5.0
SHOULDER_HALF = 5.0
HIP_HALF = 3.0
UPPER_ARM, LOWER_ARM = 7.0, 6.0
THIGH, SHIN = 8.0, 8.0

# --- Beat ----------------------------------------------------------------
BPM = 112.0
BEAT = 60.0 / BPM
BLEND_RATE = 12.0          # pose easing per second; higher = snappier
MOVE_BEATS = (8, 8, 16)    # a move lasts one of these, chosen at random


def _rest_pose():
    """Neutral standing pose. Every move writes a full pose over this."""
    return {
        "sway": 0.0,        # px, hips left/right
        "bob": 0.0,         # px, hips up (negative) / down
        "lean": 0.0,        # deg, torso tilt, positive = to the skeleton's right
        "head_tilt": 0.0,   # deg, relative to the torso
        "jaw": 0.0,         # 0 shut .. 1 wide
        # Limb angles are absolute, measured from straight down, positive
        # meaning outward from the body on that limb's own side.
        "arm_u_r": 30.0, "arm_l_r": 30.0,
        "arm_u_l": 30.0, "arm_l_l": 30.0,
        "leg_u_r": 8.0, "leg_l_r": 8.0,
        "leg_u_l": 8.0, "leg_l_l": 8.0,
    }


# --------------------------------------------------------------------------
# moves
# --------------------------------------------------------------------------
# Each move is f(t) -> pose, where ``t`` is beats elapsed within the move
# (a float, so it is continuous). Two-beat cycles read as "one move per
# bar" at 112 BPM, which is what makes the dance look deliberate rather
# than jittery.

def _move_sway(t):
    s = math.sin(math.tau * t / 2)
    pulse = abs(math.sin(math.pi * t))
    p = _rest_pose()
    p.update(
        sway=5.0 * s, bob=-2.0 * pulse, lean=7.0 * s, head_tilt=-5.0 * s,
        jaw=0.7 * pulse,
        arm_u_r=45.0 + 25.0 * s, arm_l_r=70.0 + 30.0 * s,
        arm_u_l=45.0 - 25.0 * s, arm_l_l=70.0 - 30.0 * s,
        leg_u_r=10.0 + 5.0 * s, leg_l_r=6.0,
        leg_u_l=10.0 - 5.0 * s, leg_l_l=6.0,
    )
    return p


def _move_arms_up(t):
    w = math.sin(math.tau * t)
    pulse = abs(math.sin(math.pi * t))
    p = _rest_pose()
    p.update(
        bob=-3.0 * pulse, lean=3.0 * w, head_tilt=4.0 * w, jaw=0.9 * pulse,
        arm_u_r=150.0 + 12.0 * w, arm_l_r=168.0 + 22.0 * w,
        arm_u_l=150.0 - 12.0 * w, arm_l_l=168.0 - 22.0 * w,
        leg_u_r=14.0, leg_l_r=4.0,
        leg_u_l=14.0, leg_l_l=4.0,
    )
    return p


def _move_twist(t):
    s = math.sin(math.tau * t / 2)
    p = _rest_pose()
    p.update(
        sway=-4.0 * s, bob=-1.5 * abs(s), lean=14.0 * s, head_tilt=-8.0 * s,
        jaw=0.4 + 0.4 * abs(s),
        arm_u_r=60.0 - 40.0 * s, arm_l_r=95.0 - 45.0 * s,
        arm_u_l=60.0 + 40.0 * s, arm_l_l=95.0 + 45.0 * s,
        leg_u_r=12.0, leg_l_r=10.0 + 6.0 * s,
        leg_u_l=12.0, leg_l_l=10.0 - 6.0 * s,
    )
    return p


def _move_kick(t):
    k = math.sin(math.tau * t / 2)
    right, left = max(0.0, k), max(0.0, -k)
    p = _rest_pose()
    p.update(
        sway=-3.0 * k, bob=-1.0, lean=-6.0 * k, jaw=0.8 * max(right, left),
        arm_u_r=85.0, arm_l_r=100.0,
        arm_u_l=85.0, arm_l_l=100.0,
        leg_u_r=8.0 + 55.0 * right, leg_l_r=8.0 + 40.0 * right,
        leg_u_l=8.0 + 55.0 * left, leg_l_l=8.0 + 40.0 * left,
    )
    return p


def _move_hop(t):
    # One hop per beat: a crouch on the first third, then air time.
    phase = t % 1.0
    air = math.sin(math.pi * min(1.0, max(0.0, (phase - 0.25) / 0.75)))
    crouch = max(0.0, 1.0 - phase / 0.25)
    p = _rest_pose()
    p.update(
        bob=-11.0 * air + 3.0 * crouch, jaw=0.9 * air,
        arm_u_r=40.0 + 110.0 * air, arm_l_r=40.0 + 130.0 * air,
        arm_u_l=40.0 + 110.0 * air, arm_l_l=40.0 + 130.0 * air,
        leg_u_r=10.0 + 18.0 * crouch + 12.0 * air,
        leg_l_r=6.0 + 30.0 * crouch + 34.0 * air,
        leg_u_l=10.0 + 18.0 * crouch + 12.0 * air,
        leg_l_l=6.0 + 30.0 * crouch + 34.0 * air,
    )
    return p


def _move_floss(t):
    f = math.sin(math.tau * t / 2)
    p = _rest_pose()
    # Both arms swing to the same side while the hips counter-swing, so the
    # sign on the left arm is flipped relative to its own side.
    p.update(
        sway=-6.0 * f, bob=-1.5 * abs(f), lean=-9.0 * f, head_tilt=6.0 * f,
        jaw=0.3 + 0.5 * abs(f),
        arm_u_r=70.0 + 45.0 * f, arm_l_r=85.0 + 55.0 * f,
        arm_u_l=70.0 - 45.0 * f, arm_l_l=85.0 - 55.0 * f,
        leg_u_r=12.0 + 4.0 * f, leg_l_r=8.0,
        leg_u_l=12.0 - 4.0 * f, leg_l_l=8.0,
    )
    return p


MOVES = (_move_sway, _move_arms_up, _move_twist, _move_kick, _move_hop,
         _move_floss)


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------

class SkeletonState:
    """Beat clock, move choreography and eased pose. Pure -- no drawing."""

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.elapsed = 0.0            # seconds since the dance started
        self.move = 0
        self.move_start = 0.0         # beats, when the current move began
        self.move_beats = self.rng.choice(MOVE_BEATS)
        self.pose = _rest_pose()

    @property
    def beats(self):
        return self.elapsed / BEAT

    def target_pose(self):
        return MOVES[self.move](self.beats - self.move_start)

    def _next_move(self):
        choices = [i for i in range(len(MOVES)) if i != self.move]
        self.move = self.rng.choice(choices)
        self.move_start = self.beats
        self.move_beats = self.rng.choice(MOVE_BEATS)

    def update(self, dt):
        self.elapsed += dt
        if self.beats - self.move_start >= self.move_beats:
            self._next_move()
        target = self.target_pose()
        ease = min(1.0, dt * BLEND_RATE)
        for key, value in target.items():
            self.pose[key] += (value - self.pose[key]) * ease


def _limb(x, y, angle_deg, length, side):
    """End point of a bone of ``length`` leaving ``(x, y)``.

    ``angle_deg`` is measured from straight down and grows outward, so the
    same angle mirrors correctly for ``side`` -1 (the skeleton's left).
    """
    a = math.radians(angle_deg)
    return x + math.sin(a) * length * side, y + math.cos(a) * length


def joints(pose):
    """Pose scalars -> named panel coordinates. The only kinematics here."""
    hx = CX + pose["sway"]
    hy = HIP_Y + pose["bob"]
    lean = math.radians(pose["lean"])
    ux, uy = math.sin(lean), -math.cos(lean)          # up along the spine
    px, py = -uy, ux                                  # spine's right normal

    chest = (hx + ux * SPINE_LEN, hy + uy * SPINE_LEN)
    head = math.radians(pose["lean"] + pose["head_tilt"])
    neck = (chest[0] + math.sin(head) * 2.0, chest[1] - math.cos(head) * 2.0)
    skull = (chest[0] + math.sin(head) * (SKULL_R + 4.0),
             chest[1] - math.cos(head) * (SKULL_R + 4.0))

    out = {
        "hip": (hx, hy),
        "chest": chest,
        "neck": neck,
        "skull": skull,
        "shoulder_r": (chest[0] + px * SHOULDER_HALF, chest[1] + py * SHOULDER_HALF),
        "shoulder_l": (chest[0] - px * SHOULDER_HALF, chest[1] - py * SHOULDER_HALF),
        "hip_r": (hx + HIP_HALF, hy),
        "hip_l": (hx - HIP_HALF, hy),
    }
    for tag, side in (("r", 1), ("l", -1)):
        elbow = _limb(*out["shoulder_" + tag], pose["arm_u_" + tag], UPPER_ARM, side)
        out["elbow_" + tag] = elbow
        out["hand_" + tag] = _limb(*elbow, pose["arm_l_" + tag], LOWER_ARM, side)
        knee = _limb(*out["hip_" + tag], pose["leg_u_" + tag], THIGH, side)
        out["knee_" + tag] = knee
        out["foot_" + tag] = _limb(*knee, pose["leg_l_" + tag], SHIN, side)
    return out


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def _lerp(a, b, t):
    return a + (b - a) * t


def _lerp_color(c0, c1, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(_lerp(a, b, t))) for a, b in zip(c0, c1))


def _build_base():
    """Sky gradient + moon + graveyard, rendered once."""
    img = Image.new("RGB", (WIDTH, HEIGHT), SKY_BOTTOM)
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        draw.line([(0, y), (WIDTH - 1, y)],
                  fill=_lerp_color(SKY_TOP, SKY_BOTTOM, y / (HEIGHT - 1)))

    # The moon is pasted through its own alpha so the crescent bite reveals
    # the real sky gradient instead of a flat patch of one sky colour.
    mx, my = MOON_CENTER
    c = MOON_R + 1
    moon = Image.new("RGBA", (c * 2, c * 2), (0, 0, 0, 0))
    md = ImageDraw.Draw(moon)
    md.ellipse([c - MOON_R, c - MOON_R, c + MOON_R, c + MOON_R],
               fill=MOON_COLOR + (255,))
    md.ellipse([c - 1, c - 3, c + 1, c - 1], fill=MOON_SHADOW + (255,))
    md.ellipse([c - 3, c + 1, c - 1, c + 3], fill=MOON_SHADOW + (255,))
    md.ellipse([c - MOON_R * 1.5, c - MOON_R * 1.2,
                c + MOON_R * 0.5, c + MOON_R * 1.2], fill=(0, 0, 0, 0))
    img.paste(moon, (mx - c, my - c), moon)

    for gx, gh in ((7, 12), (54, 9), (44, 6)):
        top = GROUND_Y - gh
        draw.rectangle([gx, top + 2, gx + 5, GROUND_Y], fill=GRAVE_SHADE)
        draw.rectangle([gx, top + 2, gx + 3, GROUND_Y], fill=GRAVE)
        draw.ellipse([gx, top, gx + 5, top + 5], fill=GRAVE_SHADE)
        draw.ellipse([gx, top, gx + 3, top + 4], fill=GRAVE)

    draw.rectangle([0, GROUND_Y, WIDTH - 1, HEIGHT - 1], fill=GROUND)
    draw.line([(0, GROUND_Y), (WIDTH - 1, GROUND_Y)], fill=GROUND_EDGE)
    return img


def _draw_bone(draw, a, b, color=BONE):
    draw.line([a, b], fill=color, width=2)


def _draw_skull(draw, pose, j):
    sx, sy = j["skull"]
    r = SKULL_R
    draw.ellipse([sx - r, sy - r - 1, sx + r, sy + r - 1], fill=BONE)
    draw.ellipse([sx - r + 1, sy - r, sx + r - 1, sy - 1], fill=BONE)

    # The jaw is a separate block below a permanent dark gap, so a shut
    # mouth still reads as a mouth and an open one widens the gap instead
    # of drawing teeth on top of the cranium.
    drop = pose["jaw"] * 3.0
    draw.rectangle([sx - 2, sy + r - 3, sx + 2, sy + r - 2 + drop], fill=SOCKET)
    draw.rectangle([sx - 2, sy + r - 2 + drop, sx + 2, sy + r - 1 + drop], fill=BONE)

    for dx in (-2, 2):
        draw.rectangle([sx + dx - 1, sy - 2, sx + dx, sy], fill=SOCKET)
        draw.point((sx + dx, sy - 1), fill=EYE_GLOW)
    draw.point((sx, sy + 1), fill=SOCKET)


def _draw_ribs(draw, j):
    hx, hy = j["hip"]
    cx, cy = j["chest"]
    for frac, half in ((0.45, 3.5), (0.65, 4.0), (0.85, 3.5)):
        x = _lerp(hx, cx, frac)
        y = _lerp(hy, cy, frac)
        draw.line([(x - half, y), (x + half, y)], fill=BONE_SHADE)


def _render(base, state):
    """(pre-rendered base layer, SkeletonState) -> a fresh 64x64 RGB frame."""
    frame = base.copy()
    draw = ImageDraw.Draw(frame)
    pose = state.pose
    j = joints(pose)

    for x, y, phase in STARS:
        twinkle = 0.5 + 0.5 * math.sin(state.elapsed * 2.0 + phase)
        draw.point((x, y), fill=tuple(int(v * (0.65 + 0.35 * twinkle))
                                      for v in STAR_COLOR))

    # A shadow that shrinks as the hips rise is the only cue that a hop
    # leaves the ground rather than the whole figure being drawn higher.
    lift = max(0.0, -pose["bob"]) / 11.0
    half = 11.0 - 4.0 * lift
    draw.ellipse([j["hip"][0] - half, GROUND_Y + 1,
                  j["hip"][0] + half, GROUND_Y + 4], fill=SHADOW)

    for tag in ("l", "r"):
        _draw_bone(draw, j["hip_" + tag], j["knee_" + tag])
        _draw_bone(draw, j["knee_" + tag], j["foot_" + tag])
        fx, fy = j["foot_" + tag]
        draw.line([(fx - 2, fy), (fx + 1, fy)], fill=BONE)

    _draw_bone(draw, j["hip_l"], j["hip_r"])
    _draw_bone(draw, j["hip"], j["chest"])
    _draw_ribs(draw, j)
    _draw_bone(draw, j["shoulder_l"], j["shoulder_r"], BONE_SHADE)

    for tag in ("l", "r"):
        _draw_bone(draw, j["shoulder_" + tag], j["elbow_" + tag])
        _draw_bone(draw, j["elbow_" + tag], j["hand_" + tag])
        hx, hy = j["hand_" + tag]
        draw.rectangle([hx - 1, hy - 1, hx, hy], fill=BONE)

    _draw_bone(draw, j["chest"], j["neck"])
    _draw_skull(draw, pose, j)
    return frame


def run(matrix, duration=60):
    """Run the dancing skeleton screensaver for the specified duration."""
    base = _build_base()
    state = SkeletonState()
    start_time = time.time()
    last = start_time

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            dt = min(0.2, max(0.0, frame_start - last))
            last = frame_start

            state.update(dt)
            frame = _render(base, state)
            matrix.SetImage(frame)

            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    except Exception:
        logger.error("Error in skeleton demo", exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass


if __name__ == "__main__":
    print("This module should be imported and used with the LED matrix.")
    print("Please run src/main.py instead.")
