"""
Death Ball -- Wizard soccer platformer on 64x64 LED matrix.

Inspired by the DeathBall arcade game. Two wizards platform around a small
arena, kicking a magical ball into each other's goals. Features double-jump,
magic blast (redirects ball), ball trail effects, and sudden death.

Features:
- 2D platforming physics (gravity, double-jump, air control)
- Ball with bouncy physics and speed-based glow
- Magic blast (AoE push on ball, costs mana)
- 4 floating platforms for vertical play
- Goal zones on left/right walls
- Ball trail effect, kick sparks, blast particles
- Sudden death mode (ball speeds up, arena pulses red)
- AI vs AI (DEMO) or player vs AI (INTERACTIVE)

Control scheme (INTERACTIVE mode)
---------------------------------
- **LEFT / RIGHT** move wizard
- **UP / A** jump (press again for double-jump)
- **DOWN** fast-fall
- **B** magic blast (pushes ball away, costs mana)
- **Start + Select** quit to menu
"""

import random
import logging
import time
import math
from PIL import Image, ImageDraw
from src.display._shared import (
    should_stop,
    interruptible_sleep,
    safe_rumble,
    show_banner,
)
from src.display._fonts import _draw_text, _text_width
from src.display._utils import _draw_digit, _draw_number, _scale_color

logger = logging.getLogger(__name__)

# --- Constants ---
SIZE = 64
FPS = 20
FRAME_DUR = 1.0 / FPS

# Physics (tuned for 2x feel -- bigger jumps, more airtime)
GRAVITY = 0.35
BALL_GRAVITY = 0.22
WALK_SPEED = 1.8
JUMP_VEL = -4.2
DOUBLE_JUMP_VEL = -3.8
AIR_CONTROL = 0.8
BALL_BOUNCE = 0.7
BALL_FRICTION = 0.98
BALL_MAX_SPEED = 5.5
KICK_POWER = 4.0
BLAST_POWER = 4.5
FAST_FALL = 2.5

# Mana
MAX_MANA = 100
BLAST_COST = 50
MANA_REGEN = 2

# Arena -- maximally open, razor-thin walls, huge play area
FLOOR_Y = 63
CEILING_Y = 0
WALL_LEFT = 0
WALL_RIGHT = 63
GOAL_TOP = 22
GOAL_BOTTOM = 42
GOAL_DEPTH = 2

# Defensive walls: vertical walls 10px in front of each goal
# Ball/wizards must go around these to score
DEFENSE_WALL_LEFT_X = 10   # 10px from left wall
DEFENSE_WALL_RIGHT_X = 53  # 10px from right wall
DEFENSE_WALL_TOP = 18      # Wall starts slightly above goal
DEFENSE_WALL_BOTTOM = 46   # Wall ends slightly below goal

# Scoring
WIN_SCORE = 3
ROUND_TIME = 60 * FPS  # 60 seconds in frames

# Colors
BG_COLOR = (0, 0, 0)
WALL_COLOR = (30, 30, 50)
FLOOR_COLOR = (40, 40, 60)
PLATFORM_COLOR = (60, 50, 90)
P1_COLOR = (80, 150, 255)
P2_COLOR = (255, 80, 150)
BALL_COLOR = (255, 220, 50)
BALL_TRAIL_COLORS = [(200, 170, 30), (150, 120, 20), (100, 80, 10), (50, 40, 5)]
GOAL_P1_COLOR = (20, 40, 80)
GOAL_P2_COLOR = (80, 20, 40)
BLAST_COLOR = (200, 100, 255)
SUDDEN_DEATH_COLOR = (255, 40, 40)
MANA_COLOR = (100, 200, 255)
MANA_EMPTY = (40, 60, 80)
SCORE_COLOR = (255, 255, 255)

# Platforms: NONE -- fully open arena for maximum space feeling
PLATFORMS = []


# ---------------------------------------------------------------------------
# Game entities
# ---------------------------------------------------------------------------

class Wizard:
    """A wizard player with platforming physics."""

    def __init__(self, x, y, facing, player_id):
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.facing = facing  # 1 = right, -1 = left
        self.player_id = player_id
        self.on_ground = False
        self.jumps_left = 2
        self.mana = MAX_MANA
        self.blast_cooldown = 0

    def apply_gravity(self):
        self.vy += GRAVITY
        if self.vy > 8:
            self.vy = 8

    def move(self, dx):
        speed = WALK_SPEED if self.on_ground else WALK_SPEED * AIR_CONTROL
        self.vx = dx * speed
        if dx != 0:
            self.facing = 1 if dx > 0 else -1

    def jump(self):
        if self.jumps_left > 0:
            vel = JUMP_VEL if self.jumps_left == 2 else DOUBLE_JUMP_VEL
            self.vy = vel
            self.jumps_left -= 1
            self.on_ground = False
            return True
        return False

    def fast_fall(self):
        if not self.on_ground:
            self.vy += FAST_FALL

    def update_physics(self):
        self.apply_gravity()
        self.x += self.vx
        self.y += self.vy
        self.vx *= 0.8  # ground friction when not actively moving

        # Regen mana
        if self.mana < MAX_MANA:
            self.mana = min(MAX_MANA, self.mana + MANA_REGEN)
        if self.blast_cooldown > 0:
            self.blast_cooldown -= 1

        # Arena bounds (but not goal zones)
        # Left wall
        if self.x < WALL_LEFT + GOAL_DEPTH + 1:
            if self.y < GOAL_TOP or self.y > GOAL_BOTTOM:
                self.x = WALL_LEFT + GOAL_DEPTH + 1
                self.vx = 0
            elif self.x < WALL_LEFT:
                self.x = WALL_LEFT
                self.vx = 0
        # Right wall
        if self.x > WALL_RIGHT - GOAL_DEPTH - 1:
            if self.y < GOAL_TOP or self.y > GOAL_BOTTOM:
                self.x = WALL_RIGHT - GOAL_DEPTH - 1
                self.vx = 0
            elif self.x > WALL_RIGHT:
                self.x = WALL_RIGHT
                self.vx = 0

        # Defensive wall collisions (vertical walls in front of goals)
        # Left defensive wall
        if (DEFENSE_WALL_TOP <= self.y <= DEFENSE_WALL_BOTTOM):
            if self.vx < 0 and abs(self.x - DEFENSE_WALL_LEFT_X) < 2:
                self.x = DEFENSE_WALL_LEFT_X + 2
                self.vx = 0
            elif self.vx > 0 and abs(self.x - DEFENSE_WALL_LEFT_X) < 2:
                self.x = DEFENSE_WALL_LEFT_X - 1
                self.vx = 0
        # Right defensive wall
        if (DEFENSE_WALL_TOP <= self.y <= DEFENSE_WALL_BOTTOM):
            if self.vx > 0 and abs(self.x - DEFENSE_WALL_RIGHT_X) < 2:
                self.x = DEFENSE_WALL_RIGHT_X - 1
                self.vx = 0
            elif self.vx < 0 and abs(self.x - DEFENSE_WALL_RIGHT_X) < 2:
                self.x = DEFENSE_WALL_RIGHT_X + 2
                self.vx = 0

        # Floor (wizard is 1px tall now -- tiny zoomed-out feel)
        if self.y >= FLOOR_Y - 1:
            self.y = FLOOR_Y - 1
            self.vy = 0
            self.on_ground = True
            self.jumps_left = 2

        # Ceiling
        if self.y < CEILING_Y:
            self.y = CEILING_Y
            self.vy = 0

        # Platform collisions (one-way: land on top only)
        if self.vy > 0:  # only when falling
            for px_start, px_end, py in PLATFORMS:
                if (self.x >= px_start - 1 and self.x <= px_end + 1 and
                        self.y >= py - 1 and self.y <= py + 1):
                    self.y = py - 1
                    self.vy = 0
                    self.on_ground = True
                    self.jumps_left = 2
                    break

    def can_blast(self):
        return self.mana >= BLAST_COST and self.blast_cooldown <= 0


class Ball:
    """The magical ball with physics and trail."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.x = SIZE / 2.0
        self.y = 8.0  # Start near top
        self.vx = 0.0  # Drop straight down
        self.vy = 0.0
        self.trail = []
        self.speed_mult = 1.0

    def update_physics(self):
        self.vy += BALL_GRAVITY * self.speed_mult
        self.x += self.vx
        self.y += self.vy

        # Clamp speed
        speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
        max_spd = BALL_MAX_SPEED * self.speed_mult
        if speed > max_spd:
            scale = max_spd / speed
            self.vx *= scale
            self.vy *= scale

        # Friction
        self.vx *= BALL_FRICTION
        self.vy *= BALL_FRICTION

        # Trail
        self.trail.append((int(self.x), int(self.y)))
        if len(self.trail) > 4:
            self.trail.pop(0)

        # Bounce off floor
        if self.y >= FLOOR_Y - 2:
            self.y = FLOOR_Y - 2
            self.vy = -abs(self.vy) * BALL_BOUNCE

        # Bounce off ceiling
        if self.y <= CEILING_Y + 1:
            self.y = CEILING_Y + 1
            self.vy = abs(self.vy) * BALL_BOUNCE

        # Bounce off walls (but pass through goal zones)
        # Left wall
        if self.x <= WALL_LEFT + GOAL_DEPTH:
            if self.y < GOAL_TOP or self.y > GOAL_BOTTOM:
                self.x = WALL_LEFT + GOAL_DEPTH
                self.vx = abs(self.vx) * BALL_BOUNCE
        # Right wall
        if self.x >= WALL_RIGHT - GOAL_DEPTH:
            if self.y < GOAL_TOP or self.y > GOAL_BOTTOM:
                self.x = WALL_RIGHT - GOAL_DEPTH
                self.vx = -abs(self.vx) * BALL_BOUNCE

        # Defensive wall bounces (ball bounces off the vertical walls in front of goals)
        if DEFENSE_WALL_TOP <= self.y <= DEFENSE_WALL_BOTTOM:
            # Left defensive wall
            if self.vx < 0 and abs(self.x - DEFENSE_WALL_LEFT_X) < 1.5:
                self.x = DEFENSE_WALL_LEFT_X + 1.5
                self.vx = abs(self.vx) * BALL_BOUNCE
            # Right defensive wall
            if self.vx > 0 and abs(self.x - DEFENSE_WALL_RIGHT_X) < 1.5:
                self.x = DEFENSE_WALL_RIGHT_X - 1.5
                self.vx = -abs(self.vx) * BALL_BOUNCE

        # Platform bounces
        if self.vy > 0:
            for px_start, px_end, py in PLATFORMS:
                if (self.x >= px_start - 1 and self.x <= px_end + 1 and
                        self.y >= py - 2 and self.y <= py + 1):
                    self.y = py - 2
                    self.vy = -abs(self.vy) * BALL_BOUNCE
                    break

    def check_goal(self):
        """Check if ball entered a goal zone. Returns 0 (P1 scored), 1 (P2 scored), or -1."""
        # Ball in left goal = P2 scores
        if self.x <= WALL_LEFT and GOAL_TOP <= self.y <= GOAL_BOTTOM:
            return 1  # P2 scored on P1's goal
        # Ball in right goal = P1 scores
        if self.x >= WALL_RIGHT and GOAL_TOP <= self.y <= GOAL_BOTTOM:
            return 0  # P1 scored on P2's goal
        return -1

    def get_speed(self):
        return math.sqrt(self.vx * self.vx + self.vy * self.vy)


class Particle:
    """Brief visual particle effect."""

    def __init__(self, x, y, vx, vy, color, life=8):
        self.x = float(x)
        self.y = float(y)
        self.vx = vx
        self.vy = vy
        self.color = color
        self.life = life

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.life -= 1
        return self.life > 0


# ---------------------------------------------------------------------------
# Main game class
# ---------------------------------------------------------------------------

class DeathBallGame:
    """Full Death Ball game state."""

    def __init__(self):
        self.wizard1 = Wizard(16, FLOOR_Y - 1, 1, 0)
        self.wizard2 = Wizard(48, FLOOR_Y - 1, -1, 1)
        self.ball = Ball()
        self.scores = [0, 0]
        self.timer = ROUND_TIME
        self.sudden_death = False
        self.particles = []
        self.goal_flash = 0
        self.round_pause = 0
        self.tick = 0

    def reset_round(self):
        """Reset positions after a goal."""
        self.wizard1.x = 16
        self.wizard1.y = FLOOR_Y - 1
        self.wizard1.vx = 0
        self.wizard1.vy = 0
        self.wizard2.x = 48
        self.wizard2.y = FLOOR_Y - 1
        self.wizard2.vx = 0
        self.wizard2.vy = 0
        self.ball.reset()
        self.round_pause = 20

    def kick_ball(self, wizard):
        """Wizard kicks the ball if close enough."""
        dx = self.ball.x - wizard.x
        dy = self.ball.y - wizard.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 6:
            # Kick in facing direction with upward angle
            angle = -0.3 if wizard.facing > 0 else math.pi + 0.3
            self.ball.vx = KICK_POWER * math.cos(angle) * self.ball.speed_mult
            self.ball.vy = -KICK_POWER * 0.7 * self.ball.speed_mult
            # Add wizard momentum
            self.ball.vx += wizard.vx * 0.3
            # Sparks
            for _ in range(4):
                self.particles.append(Particle(
                    self.ball.x, self.ball.y,
                    random.uniform(-1, 1), random.uniform(-2, 0),
                    BALL_COLOR, life=6
                ))
            return True
        return False

    def magic_blast(self, wizard):
        """Wizard uses magic blast to push ball and opponent away.

        The blast pushes:
        - The ball (away from caster)
        - The opponent wizard (away from caster, but NOT the caster themselves)
        """
        if not wizard.can_blast():
            return False
        wizard.mana -= BLAST_COST
        wizard.blast_cooldown = 10

        # Push ball away from wizard
        dx = self.ball.x - wizard.x
        dy = self.ball.y - wizard.y
        dist = max(1, math.sqrt(dx * dx + dy * dy))
        push_x = (dx / dist) * BLAST_POWER * self.ball.speed_mult
        push_y = (dy / dist) * BLAST_POWER * self.ball.speed_mult
        self.ball.vx += push_x
        self.ball.vy += push_y

        # Push opponent wizard away (not the caster)
        opponent = self.wizard2 if wizard.player_id == 0 else self.wizard1
        opp_dx = opponent.x - wizard.x
        opp_dy = opponent.y - wizard.y
        opp_dist = math.sqrt(opp_dx * opp_dx + opp_dy * opp_dy)
        if opp_dist < 20:  # Only affects opponent within blast radius
            if opp_dist < 1:
                opp_dist = 1
            # Push force decreases with distance
            push_strength = BLAST_POWER * 0.8 * (1.0 - opp_dist / 20.0)
            opponent.vx += (opp_dx / opp_dist) * push_strength
            opponent.vy += (opp_dy / opp_dist) * push_strength - 1.5  # Slight upward launch

        # Blast particles (expanding ring)
        for i in range(8):
            angle = i * math.pi / 4
            self.particles.append(Particle(
                wizard.x, wizard.y,
                math.cos(angle) * 2, math.sin(angle) * 2,
                BLAST_COLOR, life=8
            ))
        return True

    def update(self):
        """Update one frame of game logic."""
        self.tick += 1

        if self.round_pause > 0:
            self.round_pause -= 1
            return

        # Timer
        if not self.sudden_death:
            self.timer -= 1
            if self.timer <= 0 and self.scores[0] == self.scores[1]:
                self.sudden_death = True
                self.ball.speed_mult = 2.0

        # Physics
        self.wizard1.update_physics()
        self.wizard2.update_physics()
        self.ball.update_physics()

        # Auto-kick: if wizard overlaps ball, they kick it
        for wiz in [self.wizard1, self.wizard2]:
            dx = abs(self.ball.x - wiz.x)
            dy = abs(self.ball.y - wiz.y)
            if dx < 4 and dy < 5:
                self.kick_ball(wiz)

        # Check goal
        scorer = self.ball.check_goal()
        if scorer >= 0:
            self.scores[scorer] += 1
            self.goal_flash = 15
            self.reset_round()

        # Update particles
        self.particles = [p for p in self.particles if p.update()]

    def check_winner(self):
        """Check if someone won."""
        if self.scores[0] >= WIN_SCORE:
            return 0
        if self.scores[1] >= WIN_SCORE:
            return 1
        if self.sudden_death and self.scores[0] != self.scores[1]:
            return 0 if self.scores[0] > self.scores[1] else 1
        return -1

    # --- Rendering ---

    def draw(self):
        """Render full game frame."""
        image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        draw = ImageDraw.Draw(image)
        tick = self.tick

        # Goal zone glow
        g1_pulse = int(20 + 10 * math.sin(tick * 0.1))
        g2_pulse = int(20 + 10 * math.sin(tick * 0.1 + 1))
        draw.rectangle([0, GOAL_TOP, GOAL_DEPTH - 1, GOAL_BOTTOM],
                       fill=(g1_pulse, g1_pulse * 2, g1_pulse * 4))
        draw.rectangle([SIZE - GOAL_DEPTH, GOAL_TOP, SIZE - 1, GOAL_BOTTOM],
                       fill=(g2_pulse * 4, g2_pulse, g2_pulse * 2))

        # Arena walls -- single pixel lines only for maximum openness
        # Floor (1px line)
        draw.line([(0, FLOOR_Y), (SIZE - 1, FLOOR_Y)], fill=FLOOR_COLOR)
        # Left wall (1px, except goal opening)
        draw.line([(0, 0), (0, GOAL_TOP - 1)], fill=WALL_COLOR)
        draw.line([(0, GOAL_BOTTOM + 1), (0, FLOOR_Y)], fill=WALL_COLOR)
        # Right wall (1px, except goal opening)
        draw.line([(SIZE - 1, 0), (SIZE - 1, GOAL_TOP - 1)], fill=WALL_COLOR)
        draw.line([(SIZE - 1, GOAL_BOTTOM + 1), (SIZE - 1, FLOOR_Y)], fill=WALL_COLOR)

        # Platforms (if any)
        for px_start, px_end, py in PLATFORMS:
            draw.line([(px_start, py), (px_end, py)], fill=PLATFORM_COLOR)

        # Defensive walls (vertical lines in front of goals)
        draw.line([(DEFENSE_WALL_LEFT_X, DEFENSE_WALL_TOP),
                   (DEFENSE_WALL_LEFT_X, DEFENSE_WALL_BOTTOM)], fill=WALL_COLOR)
        draw.line([(DEFENSE_WALL_RIGHT_X, DEFENSE_WALL_TOP),
                   (DEFENSE_WALL_RIGHT_X, DEFENSE_WALL_BOTTOM)], fill=WALL_COLOR)

        # Sudden death pulsing walls
        if self.sudden_death:
            pulse = int(40 + 30 * math.sin(tick * 0.3))
            sd_color = (pulse, 0, 0)
            draw.rectangle([0, 0, SIZE - 1, 0], fill=sd_color)
            draw.rectangle([0, SIZE - 1, SIZE - 1, SIZE - 1], fill=sd_color)

        # Ball trail
        for i, (tx, ty) in enumerate(self.ball.trail):
            if 0 <= tx < SIZE and 0 <= ty < SIZE:
                color = BALL_TRAIL_COLORS[min(i, len(BALL_TRAIL_COLORS) - 1)]
                draw.point((tx, ty), fill=color)

        # Ball (single bright pixel -- zoomed out feel)
        bx, by = int(self.ball.x), int(self.ball.y)
        speed = self.ball.get_speed()
        bright = min(255, int(200 + speed * 10))
        ball_c = (bright, int(bright * 0.86), int(bright * 0.2))
        if 0 <= bx < SIZE and 0 <= by < SIZE:
            draw.point((bx, by), fill=ball_c)

        # Wizards
        self._draw_wizard(draw, self.wizard1, P1_COLOR, tick)
        self._draw_wizard(draw, self.wizard2, P2_COLOR, tick)

        # Particles
        for p in self.particles:
            px, py = int(p.x), int(p.y)
            if 0 <= px < SIZE and 0 <= py < SIZE:
                alpha = p.life / 8.0
                c = tuple(int(v * alpha) for v in p.color)
                draw.point((px, py), fill=c)

        # Goal flash
        if self.goal_flash > 0:
            self.goal_flash -= 1
            if self.goal_flash % 3 == 0:
                flash_alpha = int(100 * (self.goal_flash / 15.0))
                for x in range(SIZE):
                    draw.point((x, 0), fill=(flash_alpha, flash_alpha, flash_alpha))
                    draw.point((x, SIZE - 1), fill=(flash_alpha, flash_alpha, flash_alpha))

        # Score display
        _draw_digit(image, str(self.scores[0]), 2, 1, P1_COLOR, SIZE)
        _draw_digit(image, str(self.scores[1]), SIZE - 5, 1, P2_COLOR, SIZE)

        # Timer (center top) - show seconds remaining
        if not self.sudden_death and self.timer > 0:
            secs = max(0, self.timer // FPS)
            if secs < 10:
                _draw_digit(image, str(secs), SIZE // 2 - 1, 1, SCORE_COLOR, SIZE)

        # Sudden death indicator
        if self.sudden_death:
            if tick % 20 < 12:
                _draw_text(draw, "SD", SIZE // 2 - 5, 1, SUDDEN_DEATH_COLOR,
                           scale=1, spacing=0)

        # Mana bars (tiny, below wizards)
        self._draw_mana(draw, self.wizard1)
        self._draw_mana(draw, self.wizard2)

        return image

    def _draw_wizard(self, draw, wizard, color, tick):
        """Draw a wizard sprite as 2 wide x 1 tall pixel (tiny, zoomed-out feel)."""
        wx, wy = int(wizard.x), int(wizard.y)
        # Blink briefly after blast
        if wizard.blast_cooldown > 5 and tick % 4 < 2:
            color = BLAST_COLOR

        # Tiny 2x1 body -- gives the arena a massive feel
        if 0 <= wx < SIZE - 1 and 0 <= wy < SIZE:
            draw.point((wx, wy), fill=color)
            draw.point((wx + 1, wy), fill=color)
            # Facing dot (shows direction)
            eye_x = wx + wizard.facing
            if 0 <= eye_x < SIZE and 0 <= wy - 1 < SIZE:
                draw.point((eye_x, wy - 1), fill=(255, 255, 255))

    def _draw_mana(self, draw, wizard):
        """Draw tiny mana bar below wizard (1px below the 1px wizard)."""
        wx = int(wizard.x)
        wy = int(wizard.y) + 2  # Just below tiny wizard
        if wy >= SIZE:
            return
        mana_pct = wizard.mana / MAX_MANA
        bar_len = 5
        filled = int(bar_len * mana_pct)
        for i in range(bar_len):
            px = wx - 2 + i
            if 0 <= px < SIZE and 0 <= wy < SIZE:
                c = MANA_COLOR if i < filled else MANA_EMPTY
                draw.point((px, wy), fill=c)


# ---------------------------------------------------------------------------
# AI Logic
# ---------------------------------------------------------------------------

def _ai_control(game, wizard, opponent):
    """AI controls a wizard. Returns (move_dx, jump, blast, fast_fall).

    Enhanced AI that actively uses double-jump to reach platforms and the ball.
    """
    ball = game.ball
    move_dx = 0
    do_jump = False
    do_blast = False
    do_fast_fall = False

    # Determine ball direction
    ball_heading_to_me = (
        (wizard.player_id == 0 and ball.vx < -0.5) or
        (wizard.player_id == 1 and ball.vx > 0.5)
    )

    # My goal x position
    my_goal_x = GOAL_DEPTH if wizard.player_id == 0 else SIZE - GOAL_DEPTH

    # Distance to ball
    dx_ball = ball.x - wizard.x
    dy_ball = ball.y - wizard.y
    dist_ball = math.sqrt(dx_ball * dx_ball + dy_ball * dy_ball)

    # Check if ball is on/near a platform (AI should jump up to it)
    ball_on_platform = False
    target_platform = None
    for px_start, px_end, py in PLATFORMS:
        if px_start - 3 <= ball.x <= px_end + 3 and abs(ball.y - py) < 8:
            ball_on_platform = True
            target_platform = (px_start, px_end, py)
            break

    # --- Priority 1: Defend if ball heading toward my goal ---
    if ball_heading_to_me and abs(ball.x - my_goal_x) < 25:
        # Move between ball and goal
        target_x = ball.x + (4 if wizard.player_id == 0 else -4)
        if wizard.x < target_x - 2:
            move_dx = 1
        elif wizard.x > target_x + 2:
            move_dx = -1
        # Jump if ball is above -- use double jump aggressively
        if ball.y < wizard.y - 6 and wizard.jumps_left > 0:
            do_jump = True
        # Double-jump in air to reach higher
        if not wizard.on_ground and ball.y < wizard.y - 4 and wizard.jumps_left > 0:
            do_jump = True
        # Blast if ball is close and fast
        if dist_ball < 12 and ball.get_speed() > 1.5 and wizard.can_blast():
            do_blast = True

    # --- Priority 2: Ball is on a platform - jump up to reach it ---
    elif ball_on_platform and target_platform and ball.y < wizard.y - 5:
        px_start, px_end, py = target_platform
        # Move toward platform center
        plat_cx = (px_start + px_end) / 2
        if wizard.x < plat_cx - 3:
            move_dx = 1
        elif wizard.x > plat_cx + 3:
            move_dx = -1
        # Jump! Use double-jump to reach the platform
        if wizard.jumps_left > 0:
            # First jump from ground
            if wizard.on_ground:
                do_jump = True
            # Double-jump when in the air and still below the platform
            elif wizard.y > py - 2 and wizard.vy >= -1:
                do_jump = True

    # --- Priority 3: Go for the ball when it's neutral ---
    elif dist_ball > 8:
        if ball.x > wizard.x + 2:
            move_dx = 1
        elif ball.x < wizard.x - 2:
            move_dx = -1
        # Jump to reach ball -- double jump aggressively
        if ball.y < wizard.y - 8 and wizard.jumps_left > 0:
            do_jump = True
        # Double-jump mid-air to get height
        if not wizard.on_ground and ball.y < wizard.y - 4 and wizard.jumps_left > 0 and wizard.vy > 0:
            do_jump = True  # Double-jump when starting to fall

    # --- Priority 4: Attack - push ball toward opponent goal ---
    else:
        opp_goal_x = SIZE - GOAL_DEPTH if wizard.player_id == 0 else GOAL_DEPTH
        if ball.x < opp_goal_x:
            move_dx = 1 if wizard.player_id == 0 else -1
        # Blast to redirect ball toward goal
        if (dist_ball < 10 and wizard.can_blast() and
                abs(ball.y - (GOAL_TOP + GOAL_BOTTOM) / 2) < 18):
            # Only blast if it'll push ball toward opponent goal
            push_dir = ball.x - wizard.x
            if ((wizard.player_id == 0 and push_dir > 0) or
                    (wizard.player_id == 1 and push_dir < 0)):
                do_blast = True

    # Fast fall if above ball and ball is below (only if far above)
    if wizard.y < ball.y - 18 and not wizard.on_ground:
        do_fast_fall = True

    # Add slight randomness (reaction delay) -- less random for better play
    if random.random() < 0.03:
        move_dx = 0
    if random.random() < 0.05:
        do_jump = False

    return move_dx, do_jump, do_blast, do_fast_fall


# ---------------------------------------------------------------------------
# Demo mode
# ---------------------------------------------------------------------------

def _run_demo(matrix, duration, start_time):
    """AI vs AI demo."""
    game = DeathBallGame()

    while time.time() - start_time < duration:
        if should_stop():
            return

        # AI for both wizards
        dx1, j1, b1, ff1 = _ai_control(game, game.wizard1, game.wizard2)
        dx2, j2, b2, ff2 = _ai_control(game, game.wizard2, game.wizard1)

        game.wizard1.move(dx1)
        game.wizard2.move(dx2)
        if j1:
            game.wizard1.jump()
        if j2:
            game.wizard2.jump()
        if b1:
            game.magic_blast(game.wizard1)
        if b2:
            game.magic_blast(game.wizard2)
        if ff1:
            game.wizard1.fast_fall()
        if ff2:
            game.wizard2.fast_fall()

        game.update()

        # Check winner
        winner = game.check_winner()
        if winner >= 0:
            color = P1_COLOR if winner == 0 else P2_COLOR
            label = "P1 WINS" if winner == 0 else "P2 WINS"
            show_banner(matrix, [label, f"{game.scores[0]}-{game.scores[1]}"],
                        color=color, hold=1.5)
            game = DeathBallGame()
            continue

        image = game.draw()
        matrix.SetImage(image)
        time.sleep(FRAME_DUR)


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

def _run_interactive(matrix, controller, start_time):
    """Player (P1) vs AI (P2)."""
    from src.input.controller import wants_quit, Button, EventType

    _MAX_SECONDS = 600
    game = DeathBallGame()

    show_banner(matrix, ["DEATH BALL", "A:JUMP B:BLAST"],
                color=BALL_COLOR, hold=1.2)

    jump_pressed = False  # edge detection for jump

    while time.time() - start_time < _MAX_SECONDS:
        if should_stop():
            return
        controller.poll_events()
        if wants_quit(controller):
            return

        events = controller.poll_events()

        # Player input
        move_dx = 0
        d = controller.get_direction()
        if d:
            move_dx = d[0]
            if d[1] > 0:  # DOWN
                game.wizard1.fast_fall()

        for ev in events:
            if ev.type is EventType.PRESSED:
                if ev.button in (Button.UP, Button.A):
                    game.wizard1.jump()
                elif ev.button is Button.B:
                    game.magic_blast(game.wizard1)

        game.wizard1.move(move_dx)

        # AI for P2
        dx2, j2, b2, ff2 = _ai_control(game, game.wizard2, game.wizard1)
        game.wizard2.move(dx2)
        if j2:
            game.wizard2.jump()
        if b2:
            game.magic_blast(game.wizard2)
        if ff2:
            game.wizard2.fast_fall()

        game.update()

        winner = game.check_winner()
        if winner >= 0:
            player_won = winner == 0
            safe_rumble(controller, 1.0 if player_won else 0.6, 300)
            msg = "YOU WIN!" if player_won else "YOU LOSE"
            color = (80, 255, 120) if player_won else (255, 80, 80)
            show_banner(matrix, [msg, f"{game.scores[0]}-{game.scores[1]}"],
                        color=color, hold=2.0)
            return

        image = game.draw()
        matrix.SetImage(image)
        time.sleep(FRAME_DUR)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(matrix, duration=60, controller=None):
    """Run Death Ball.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds (DEMO mode).
        controller: optional Controller. None -> DEMO, not-None -> INTERACTIVE.
    """
    start_time = time.time()
    try:
        if controller is None:
            _run_demo(matrix, duration, start_time)
        else:
            _run_interactive(matrix, controller, start_time)
    except Exception as e:
        logger.error("Error in death_ball: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
