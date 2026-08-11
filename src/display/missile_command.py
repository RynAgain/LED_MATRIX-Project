"""
Missile Command -- defend six cities from ICBM rain on a 64x64 LED matrix.

Features:
- Six cities plus a central missile battery on the ground
- Enemy ICBMs fall from the sky trailing red lines toward cities/battery
- MIRV warheads that split into multiple heads mid-flight (wave 3+)
- Player crosshair; interceptors fly from the battery and detonate at
  the crosshair as expanding fireballs that vaporize warheads in radius
- Chain reactions: destroyed warheads pop their own small explosion
- Waves with escalating count and speed, end-of-wave ammo/city bonus
- Bonus city rebuilt every 2500 points
- Demo AI that leads targets and defends on its own

Control scheme (INTERACTIVE mode)
---------------------------------
- **D-pad** move crosshair (8-way)
- **A** fire interceptor at the crosshair
- **Start + Select** quit to menu
"""

import random
import logging
import time
import math
from PIL import Image, ImageDraw
from src.display._shared import should_stop, interruptible_sleep, show_banner, safe_rumble, read_direction
from src.display._utils import _draw_number, _scale_color

logger = logging.getLogger(__name__)

# --- Constants ---
SIZE = 64
FPS = 30
FRAME_DUR = 1.0 / FPS

GROUND_Y = 58            # first ground row
CITY_Y = GROUND_Y - 1    # baseline the cities sit on
BATTERY_X = 32
BATTERY_TIP_Y = GROUND_Y - 5

CITY_XS = [7, 16, 25, 39, 48, 57]   # city center x positions
NUM_CITIES = len(CITY_XS)

# Colors
SKY_TOP = (2, 2, 10)
SKY_BOTTOM = (8, 4, 18)
GROUND_COLOR = (120, 90, 30)
GROUND_DARK = (90, 65, 20)
CITY_COLOR = (60, 200, 255)
CITY_DARK = (30, 100, 140)
RUBBLE_COLOR = (80, 30, 20)
BATTERY_COLOR = (255, 200, 60)
ENEMY_TRAIL = (110, 20, 20)
ENEMY_HEAD = (255, 240, 120)
INTERCEPTOR_TRAIL = (40, 90, 220)
INTERCEPTOR_HEAD = (180, 220, 255)
CROSSHAIR_COLOR = (255, 255, 255)
HUD_COLOR = (140, 150, 200)
EXPLOSION_COLORS = [(255, 255, 255), (255, 230, 100), (255, 140, 40), (200, 60, 200)]

# Gameplay tuning
MAX_INTERCEPTORS = 3          # in flight at once
INTERCEPTOR_SPEED = 2.3
EXPLOSION_MAX_RADIUS = 7.0
EXPLOSION_GROW = 0.55
EXPLOSION_HOLD = 8            # frames at max radius
EXPLOSION_SHRINK = 0.45
GROUND_EXPLOSION_RADIUS = 5.0
CURSOR_SPEED = 2.5
CURSOR_MIN_Y = 6
CURSOR_MAX_Y = GROUND_Y - 8
MIRV_WAVE = 3                 # MIRVs appear from this wave on
SCORE_PER_MISSILE = 25
BONUS_PER_AMMO = 5
BONUS_PER_CITY = 25
BONUS_CITY_SCORE = 2500       # rebuild a city every N points


class EnemyMissile:
    """An ICBM falling from the sky toward a ground target."""

    def __init__(self, start_x, start_y, target_x, target_y, speed, can_split=False):
        self.start_x = float(start_x)
        self.start_y = float(start_y)
        self.x = float(start_x)
        self.y = float(start_y)
        self.target_x = float(target_x)
        self.target_y = float(target_y)
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        dist = math.hypot(dx, dy) or 1.0
        self.vx = dx / dist * speed
        self.vy = dy / dist * speed
        self.speed = speed
        self.can_split = can_split
        self.split_y = random.uniform(14, 30) if can_split else -1.0
        self.dead = False

    def update(self):
        """Advance. Returns True when the warhead reaches its target."""
        self.x += self.vx
        self.y += self.vy
        return self.y >= self.target_y


class Interceptor:
    """A defensive missile flying from the battery to a chosen point."""

    def __init__(self, target_x, target_y):
        self.x = float(BATTERY_X)
        self.y = float(BATTERY_TIP_Y)
        self.target_x = float(target_x)
        self.target_y = float(target_y)
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        dist = math.hypot(dx, dy) or 1.0
        self.vx = dx / dist * INTERCEPTOR_SPEED
        self.vy = dy / dist * INTERCEPTOR_SPEED

    def update(self):
        """Advance. Returns True on arrival at the detonation point."""
        self.x += self.vx
        self.y += self.vy
        remaining = math.hypot(self.target_x - self.x, self.target_y - self.y)
        return remaining <= INTERCEPTOR_SPEED


class Explosion:
    """An expanding/contracting fireball that vaporizes warheads."""

    def __init__(self, x, y, max_radius=EXPLOSION_MAX_RADIUS):
        self.x = float(x)
        self.y = float(y)
        self.radius = 1.0
        self.max_radius = float(max_radius)
        self.phase = "grow"       # grow -> hold -> shrink
        self.hold_frames = 0
        self.age = 0

    def update(self):
        """Animate. Returns False when finished."""
        self.age += 1
        if self.phase == "grow":
            self.radius += EXPLOSION_GROW
            if self.radius >= self.max_radius:
                self.radius = self.max_radius
                self.phase = "hold"
        elif self.phase == "hold":
            self.hold_frames += 1
            if self.hold_frames >= EXPLOSION_HOLD:
                self.phase = "shrink"
        else:
            self.radius -= EXPLOSION_SHRINK
            if self.radius <= 0:
                return False
        return True

    def contains(self, x, y):
        return math.hypot(x - self.x, y - self.y) <= self.radius


class MissileCommandGame:
    """One full game: waves of ICBMs vs. six cities and one battery."""

    def __init__(self):
        self.score = 0
        self.wave = 1
        self.cities = [{"x": x, "alive": True} for x in CITY_XS]
        self.battery_alive = True
        self.game_over = False
        self._frame_count = 0
        self._bonus_cities_awarded = 0

        # Crosshair
        self.cursor_x = float(SIZE // 2)
        self.cursor_y = float(SIZE // 3)

        # Entities
        self.enemies = []
        self.interceptors = []
        self.explosions = []

        # AI state
        self._ai_fire_cooldown = 0

        self._start_wave()

    # ------------------------------------------------------------------
    # Wave management
    # ------------------------------------------------------------------

    def _start_wave(self):
        self.ammo = 10 + min(self.wave * 2, 10)     # 12 .. 20
        self.battery_alive = True
        self._to_spawn = min(5 + self.wave * 2, 22)
        self._spawn_timer = FPS  # first missile after ~1s
        self.enemy_speed = min(0.16 + self.wave * 0.035, 0.55)

    def next_wave(self):
        """Advance to the next wave (call after 'wave_clear')."""
        self.wave += 1
        self.enemies = []
        self.interceptors = []
        self.explosions = []
        self._start_wave()

    def _wave_bonus(self):
        bonus = self.ammo * BONUS_PER_AMMO
        bonus += sum(BONUS_PER_CITY for c in self.cities if c["alive"])
        self.score += bonus
        self._maybe_award_bonus_city()
        return bonus

    def _maybe_award_bonus_city(self):
        """Rebuild one dead city per BONUS_CITY_SCORE points earned."""
        while (self.score // BONUS_CITY_SCORE) > self._bonus_cities_awarded:
            self._bonus_cities_awarded += 1
            dead = [c for c in self.cities if not c["alive"]]
            if dead:
                random.choice(dead)["alive"] = True

    # ------------------------------------------------------------------
    # Player actions
    # ------------------------------------------------------------------

    def move_cursor(self, dx, dy):
        self.cursor_x = max(2.0, min(float(SIZE - 3), self.cursor_x + dx))
        self.cursor_y = max(float(CURSOR_MIN_Y),
                            min(float(CURSOR_MAX_Y), self.cursor_y + dy))

    def fire(self):
        """Launch an interceptor at the crosshair. Returns True if fired."""
        if (self.ammo <= 0 or not self.battery_alive or
                len(self.interceptors) >= MAX_INTERCEPTORS):
            return False
        self.ammo -= 1
        self.interceptors.append(Interceptor(self.cursor_x, self.cursor_y))
        return True

    # ------------------------------------------------------------------
    # Spawning
    # ------------------------------------------------------------------

    def _ground_targets(self):
        targets = [(c["x"], CITY_Y) for c in self.cities if c["alive"]]
        if self.battery_alive:
            targets.append((BATTERY_X, CITY_Y))
        return targets

    def _spawn_enemy(self):
        targets = self._ground_targets()
        if not targets:
            return
        tx, ty = random.choice(targets)
        sx = random.uniform(4, SIZE - 4)
        can_split = self.wave >= MIRV_WAVE and random.random() < 0.25
        self.enemies.append(EnemyMissile(sx, 0, tx, ty, self.enemy_speed,
                                         can_split=can_split))

    def _split_mirv(self, missile):
        """Split a MIRV into 2 extra heads aimed at other targets."""
        targets = self._ground_targets()
        random.shuffle(targets)
        for tx, ty in targets[:2]:
            child = EnemyMissile(missile.x, missile.y, tx, ty, missile.speed)
            self.enemies.append(child)

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def step(self, ai_mode=False):
        """Advance one frame. Returns a state string."""
        self._frame_count += 1

        if ai_mode:
            self._ai_defend()

        # Spawn pending enemies with random gaps
        if self._to_spawn > 0:
            self._spawn_timer -= 1
            if self._spawn_timer <= 0:
                self._spawn_enemy()
                self._to_spawn -= 1
                gap = max(10, int(FPS * 1.6 - self.wave * 4))
                self._spawn_timer = random.randint(10, gap + 10)

        # Interceptors
        arrived = []
        for it in self.interceptors:
            if it.update():
                arrived.append(it)
        for it in arrived:
            self.interceptors.remove(it)
            self.explosions.append(Explosion(it.target_x, it.target_y))

        # Explosions
        self.explosions = [e for e in self.explosions if e.update()]

        # Enemies: blast kills, MIRV splits, ground impacts
        impacted = []
        for enemy in self.enemies:
            if enemy.dead:
                continue
            # Vaporized by any explosion?
            if any(e.contains(enemy.x, enemy.y) for e in self.explosions):
                enemy.dead = True
                self.score += SCORE_PER_MISSILE * self.wave
                # Chain pop
                self.explosions.append(
                    Explosion(enemy.x, enemy.y, max_radius=4.0))
                continue
            if enemy.can_split and enemy.y >= enemy.split_y:
                enemy.can_split = False
                self._split_mirv(enemy)
            if enemy.update():
                enemy.dead = True
                impacted.append(enemy)
        self.enemies = [e for e in self.enemies if not e.dead]

        for enemy in impacted:
            self._ground_impact(enemy.target_x)

        self._maybe_award_bonus_city()

        # End states
        if not any(c["alive"] for c in self.cities):
            if not self.enemies and not self.explosions:
                self.game_over = True
                return "game_over"
            return "playing"

        if (self._to_spawn <= 0 and not self.enemies and
                not self.explosions and not self.interceptors):
            self._wave_bonus()
            return "wave_clear"

        return "playing"

    def _ground_impact(self, x):
        """A warhead reached the ground: blast + destroy what it hit."""
        self.explosions.append(
            Explosion(x, CITY_Y, max_radius=GROUND_EXPLOSION_RADIUS))
        for city in self.cities:
            if city["alive"] and abs(city["x"] - x) <= 3:
                city["alive"] = False
        if abs(BATTERY_X - x) <= 3 and self.battery_alive:
            self.battery_alive = False
            self.ammo = 0

    # ------------------------------------------------------------------
    # Demo AI
    # ------------------------------------------------------------------

    def _ai_covered(self, enemy):
        """Is this warhead already dealt with by a round in the air?

        A second interceptor spent on a covered warhead is a wasted round,
        and wasted rounds are what lose the late waves (20 rounds vs up to
        22 warheads).
        """
        for it in self.interceptors:
            eta = math.hypot(it.target_x - it.x,
                             it.target_y - it.y) / INTERCEPTOR_SPEED
            ex = enemy.x + enemy.vx * eta
            ey = enemy.y + enemy.vy * eta
            if math.hypot(ex - it.target_x,
                          ey - it.target_y) <= EXPLOSION_MAX_RADIUS - 1.5:
                return True
        # About to fall through a live fireball anyway.
        for e in self.explosions:
            if e.phase != "shrink" and e.contains(enemy.x + enemy.vx * 2,
                                                  enemy.y + enemy.vy * 2):
                return True
        return False

    def _ai_threatens_structure(self, enemy):
        """Will this warhead actually destroy something that is alive?"""
        tx = enemy.target_x
        if self.battery_alive and abs(BATTERY_X - tx) <= 3:
            return True
        return any(c["alive"] and abs(c["x"] - tx) <= 3 for c in self.cities)

    def _ai_intercept_point(self, enemy):
        """(aim_x, aim_y, eta, t_pass): where and when to detonate.

        eta counts both the crosshair travel and the interceptor flight;
        t_pass is when the warhead reaches the aim point. The shot only
        works if the fireball is up by then (eta <= t_pass, plus the hold
        the explosion lingers for).
        """
        aim_x, aim_y = enemy.x, enemy.y
        eta = 0.0
        for _ in range(3):
            move = math.hypot(aim_x - self.cursor_x,
                              aim_y - self.cursor_y) / CURSOR_SPEED
            fly = math.hypot(aim_x - BATTERY_X,
                             aim_y - BATTERY_TIP_Y) / INTERCEPTOR_SPEED
            eta = move + fly
            aim_x = enemy.x + enemy.vx * eta
            aim_y = enemy.y + enemy.vy * eta
        aim_x = max(2.0, min(float(SIZE - 3), aim_x))
        aim_y = max(float(CURSOR_MIN_Y), min(float(CURSOR_MAX_Y), aim_y))
        if enemy.vy > 0.001:
            t_pass = (aim_y - enemy.y) / enemy.vy
        else:
            t_pass = eta
        return aim_x, aim_y, eta, t_pass

    def _ai_pick_target(self):
        """The most urgent warhead worth a round, or None.

        Priorities, in order: not already covered; can actually be reached
        in time; threatens a live structure (or is a MIRV bus, which is
        cheapest to kill before it splits); least time left to impact.
        Duds falling on dead ground are only engaged for points when there
        is ammo to spare.
        """
        best = None
        best_key = None
        for enemy in self.enemies:
            if enemy.dead or enemy.y < 4:
                continue
            if self._ai_covered(enemy):
                continue
            vital = self._ai_threatens_structure(enemy) or enemy.can_split
            if not vital and self.ammo <= len(self.enemies) + self._to_spawn + 2:
                continue        # keep the magazine for real threats
            aim_x, aim_y, eta, t_pass = self._ai_intercept_point(enemy)
            if eta > t_pass + EXPLOSION_HOLD * 0.5:
                continue        # cannot get a fireball there in time
            frames_left = (enemy.target_y - enemy.y) / max(0.01, enemy.vy)
            if t_pass > frames_left:
                continue        # it lands before it reaches the aim point
            key = (0 if vital else 1, frames_left)
            if best_key is None or key < best_key:
                best_key = key
                best = (aim_x, aim_y)
        return best

    def _ai_defend(self):
        """Pick the most urgent uncovered warhead, lead it, fire once."""
        if self._ai_fire_cooldown > 0:
            self._ai_fire_cooldown -= 1

        pick = self._ai_pick_target()
        if pick is None:
            return
        aim_x, aim_y = pick

        # Slide the crosshair toward the aim point
        dx = aim_x - self.cursor_x
        dy = aim_y - self.cursor_y
        dist = math.hypot(dx, dy)
        if dist > CURSOR_SPEED:
            self.cursor_x += dx / dist * CURSOR_SPEED
            self.cursor_y += dy / dist * CURSOR_SPEED
        else:
            self.cursor_x, self.cursor_y = aim_x, aim_y
            if self._ai_fire_cooldown <= 0 and self.fire():
                self._ai_fire_cooldown = int(FPS * 0.25)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self):
        image = Image.new("RGB", (SIZE, SIZE), SKY_TOP)
        draw = ImageDraw.Draw(image)

        # Sky gradient (coarse bands, cheap)
        for band in range(4):
            t = band / 4.0
            color = tuple(int(a + (b - a) * t) for a, b in zip(SKY_TOP, SKY_BOTTOM))
            draw.rectangle([(0, int(GROUND_Y * t)), (SIZE - 1, int(GROUND_Y * (t + 0.25)))],
                           fill=color)

        # Ground
        for y in range(GROUND_Y, SIZE):
            color = GROUND_COLOR if y == GROUND_Y else GROUND_DARK
            draw.line([(0, y), (SIZE - 1, y)], fill=color)

        self._draw_cities(draw)
        self._draw_battery(draw)

        # Enemy trails + warheads
        for enemy in self.enemies:
            draw.line([(int(enemy.start_x), int(enemy.start_y)),
                       (int(enemy.x), int(enemy.y))], fill=ENEMY_TRAIL)
        for enemy in self.enemies:
            flicker = 1.0 if (self._frame_count // 2) % 2 == 0 else 0.6
            draw.point((int(enemy.x), int(enemy.y)),
                       fill=_scale_color(ENEMY_HEAD, flicker))

        # Interceptor trails + heads
        for it in self.interceptors:
            draw.line([(BATTERY_X, BATTERY_TIP_Y), (int(it.x), int(it.y))],
                      fill=INTERCEPTOR_TRAIL)
            draw.point((int(it.x), int(it.y)), fill=INTERCEPTOR_HEAD)

        # Explosions
        for e in self.explosions:
            color = EXPLOSION_COLORS[(e.age // 2) % len(EXPLOSION_COLORS)]
            r = e.radius
            draw.ellipse([(e.x - r, e.y - r), (e.x + r, e.y + r)], fill=color)

        # Crosshair (blinks)
        if (self._frame_count // 4) % 2 == 0:
            cx, cy = int(self.cursor_x), int(self.cursor_y)
            for dx, dy in ((-2, 0), (-1, 0), (1, 0), (2, 0),
                           (0, -2), (0, -1), (0, 1), (0, 2)):
                px, py = cx + dx, cy + dy
                if 0 <= px < SIZE and 0 <= py < SIZE:
                    draw.point((px, py), fill=CROSSHAIR_COLOR)

        # HUD: score left, wave right
        _draw_number(image, self.score, 1, 1, HUD_COLOR, SIZE)
        wave_str = str(self.wave)
        _draw_number(image, self.wave, SIZE - 1 - len(wave_str) * 4, 1,
                     (200, 120, 255), SIZE)

        return image

    def _draw_cities(self, draw):
        for city in self.cities:
            x = city["x"]
            if city["alive"]:
                # Tiny skyline: 5 wide, varying heights
                heights = [2, 3, 4, 3, 2]
                for i, h in enumerate(heights):
                    px = x - 2 + i
                    color = CITY_COLOR if i % 2 == 0 else CITY_DARK
                    draw.line([(px, CITY_Y), (px, CITY_Y - h + 1)], fill=color)
            else:
                # Rubble
                for i in range(-2, 3):
                    if (x + i) % 2 == 0:
                        draw.point((x + i, CITY_Y), fill=RUBBLE_COLOR)

    def _draw_battery(self, draw):
        # Mound
        for i, w in enumerate((4, 3, 2)):
            y = GROUND_Y - 1 - i
            draw.line([(BATTERY_X - w, y), (BATTERY_X + w, y)],
                      fill=GROUND_DARK if self.battery_alive else RUBBLE_COLOR)
        if self.battery_alive:
            # Cannon tip
            draw.line([(BATTERY_X, GROUND_Y - 4), (BATTERY_X, BATTERY_TIP_Y)],
                      fill=BATTERY_COLOR)
            # Ammo pips (one per 2 rounds) along the mound base
            pips = min(10, (self.ammo + 1) // 2)
            for i in range(pips):
                px = BATTERY_X - 5 + i
                draw.point((px, SIZE - 2), fill=BATTERY_COLOR)


# ---------------------------------------------------------------------------
# Demo mode (AI plays)
# ---------------------------------------------------------------------------

def _run_demo(matrix, duration, start_time):
    """AI-controlled missile command demo."""
    game = MissileCommandGame()

    while time.time() - start_time < duration:
        if should_stop():
            return
        frame_start = time.time()

        result = game.step(ai_mode=True)
        matrix.SetImage(game.draw())

        if result == "wave_clear":
            if not interruptible_sleep(1.2):
                return
            game.next_wave()
        elif result == "game_over":
            if not interruptible_sleep(1.5):
                return
            game = MissileCommandGame()

        elapsed = time.time() - frame_start
        sleep_time = FRAME_DUR - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Interactive mode (player controls)
# ---------------------------------------------------------------------------

def _run_interactive(matrix, controller, start_time):
    """Player-controlled missile command."""
    from src.input.controller import wants_quit, Button, EventType

    game = MissileCommandGame()
    show_banner(matrix, ["MISSILE CMD", "AIM:DPAD A:FIRE"],
                color=BATTERY_COLOR, hold=1.5)

    _MAX_SECONDS = 86400

    while time.time() - start_time < _MAX_SECONDS:
        if should_stop():
            return
        frame_start = time.time()

        events = controller.poll_events()
        if wants_quit(controller):
            return

        d = read_direction(controller, cardinal_only=False)
        if d:
            game.move_cursor(d[0] * CURSOR_SPEED, d[1] * CURSOR_SPEED)

        for ev in events:
            if ev.type is EventType.PRESSED and ev.button is Button.A:
                if game.fire():
                    safe_rumble(controller, 0.2, 60)

        result = game.step(ai_mode=False)
        matrix.SetImage(game.draw())

        if result == "wave_clear":
            safe_rumble(controller, 0.5, 250)
            show_banner(matrix, [f"WAVE {game.wave} CLEAR",
                                 f"SCORE:{game.score}"],
                        color=(80, 255, 180), hold=1.8)
            game.next_wave()

        elif result == "game_over":
            safe_rumble(controller, 1.0, 500)
            show_banner(matrix, ["THE END", f"SCORE:{game.score}"],
                        color=(255, 80, 80), hold=2.5)
            return

        elapsed = time.time() - frame_start
        sleep_time = FRAME_DUR - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(matrix, duration=60, controller=None):
    """Run Missile Command.

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
        logger.error("Error in missile_command: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
