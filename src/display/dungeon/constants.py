"""Tuning constants for the dungeon crawl."""

import math

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 30

# --- map ---------------------------------------------------------------------
MAP_W, MAP_H = 24, 24

# Tile codes. Anything >= T_FLOOR is walkable once open.
T_WALL = 0
T_FLOOR = 1
T_DOOR = 2        # plain door: opens when the hero walks into it
T_LOCKED = 3      # needs the floor's key
T_STAIRS = 4      # descend to the next floor

# --- rendering ---------------------------------------------------------------
FOV = math.radians(64)
NUM_RAYS = WIDTH
MAX_DEPTH = 20.0
WALL_SCALE = 1.05          # wall height = WALL_SCALE * HEIGHT / distance
TEX_SIZE = 16              # square procedural textures
SHADE_BANDS = 8            # pre-shaded darkness levels per texture
SIDE_DIM = 0.72            # E/W faces darker than N/S for a depth cue

# Fog closes in on deeper floors: full darkness at FOG_BASE - depth*FOG_STEP.
FOG_BASE = 11.0
FOG_STEP = 0.55
FOG_MIN = 6.0

# Torch flicker: global light multiplier wanders around 1.0.
FLICKER_DEPTH = 0.14
FLICKER_HZ = 9.0

CEILING = (26, 22, 30)
FLOOR_NEAR = (52, 44, 38)
FLOOR_FAR = (18, 15, 14)

# --- hero --------------------------------------------------------------------
HERO_MAX_HP = 6            # drawn as 3 hearts (2 hp each)
HERO_SPEED = 2.6           # cells / second
HERO_TURN = 3.4            # radians / second toward desired heading
ATTACK_RANGE = 1.25        # cells
ATTACK_ARC = math.radians(38)
ATTACK_COOLDOWN = 0.55
ATTACK_DAMAGE = 1
HURT_IFRAMES = 1.0
POTION_HEAL = 3
MAX_POTIONS = 2
LOW_HP = 2                 # retreat / drink threshold

# --- enemies -----------------------------------------------------------------
ENEMY_STATS = {
    # kind: (hp, speed cells/s, touch damage, aggro range, gold chance)
    "slime":    (2, 0.7, 1, 3.0, 0.5),
    "bat":      (1, 1.9, 1, 5.0, 0.3),
    "skeleton": (3, 1.25, 2, 6.5, 0.8),
}
TOUCH_RANGE = 0.55
ENEMY_BASE = 3             # enemies on floor 1
ENEMY_PER_FLOOR = 1.4      # + per floor (rounded)
ENEMY_CAP = 10

# --- phases ------------------------------------------------------------------
PHASE_PLAY = "play"
PHASE_DESCEND = "descend"  # fade out -> new floor -> fade in
PHASE_DEATH = "death"      # red fade + epitaph, then a fresh run
DESCEND_TIME = 1.6
DEATH_TIME = 3.2

GOLD_TOAST_TIME = 2.0      # seconds the gold counter stays up after a change
