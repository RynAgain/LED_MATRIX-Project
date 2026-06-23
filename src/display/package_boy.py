"""
Package Boy -- Amazon delivery van Paperboy-style game on 64x64 LED matrix.

An Amazon delivery van drives down a suburban street, tossing packages at
house porches. Score is tracked as a driver rating (★ 1.0 - 5.0). Features
Amazon-themed humor: star ratings per throw, porch pirates, Ring doorbells,
customer complaints, "DEACTIVATED" game over, and a Bezos rocket bonus.

Features:
- Top-down vertical scrolling suburban street
- Amazon van throws packages at subscriber house porches
- Obstacles: dogs, other cars, porch pirates, trash cans
- Star rating system (not points)
- Porch delivery = 5★, yard = 3★, bush = 2★, broken window = 1★
- Bezos rocket bonus (rare, flies across top for big bonus)
- "DEACTIVATED" game over screen
- AI vs AI demo or player-controlled interactive

Control scheme (INTERACTIVE mode)
---------------------------------
- **UP / DOWN** move the van vertically
- **A** throw package (arcs rightward toward houses)
- **B** speed boost ("SAME-DAY DELIVERY" mode)
- **Start + Select** quit to menu

DEMO mode: AI drives and delivers, occasionally misses for variety.
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
FPS = 15
FRAME_DUR = 1.0 / FPS

# Zone boundaries (x ranges)
ROAD_LEFT = 0
ROAD_RIGHT = 14
SIDEWALK_LEFT = 15
SIDEWALK_RIGHT = 34
HOUSE_LEFT = 36
HOUSE_RIGHT = 63

# Colors
BG_COLOR = (0, 0, 0)
ROAD_COLOR = (30, 30, 35)
ROAD_LINE = (180, 180, 0)
SIDEWALK_COLOR = (55, 55, 50)
GRASS_COLOR = (15, 50, 10)
VAN_BODY = (0, 100, 180)
VAN_STRIPE = (255, 160, 0)
PACKAGE_COLOR = (160, 120, 60)
PORCH_LIT = (255, 200, 50)
PORCH_DARK = (40, 30, 10)
HOUSE_COLORS = [
    (100, 70, 50),   # brown
    (70, 80, 100),   # blue-gray
    (90, 90, 60),    # olive
    (80, 50, 60),    # mauve
]
ROOF_COLOR = (120, 40, 40)
DOG_COLOR = (140, 80, 20)
CAR_COLORS = [(180, 30, 30), (30, 30, 180), (30, 150, 30), (150, 150, 150)]
TRASH_COLOR = (80, 80, 80)
PIRATE_COLOR = (40, 40, 40)  # dark hoodie
STAR_COLOR = (255, 220, 0)
ROCKET_COLOR = (200, 200, 220)
FLAME_COLOR = (255, 100, 0)
COMPLAINT_COLOR = (255, 60, 60)
RATING_GOOD = (80, 255, 80)
RATING_BAD = (255, 80, 80)


# ---------------------------------------------------------------------------
# Game entities
# ---------------------------------------------------------------------------

class House:
    """A house scrolling down the right side."""
    def __init__(self, y, subscriber=True):
        self.y = float(y)
        self.subscriber = subscriber
        self.delivered = False
        self.broken_window = False
        self.color = random.choice(HOUSE_COLORS)
        self.has_pirate = random.random() < 0.15  # 15% chance porch pirate
        self.pirate_timer = 0  # frames until pirate steals
        self.ring_flash = 0  # Ring doorbell animation timer
        self.rating_popup = 0  # show star rating briefly
        self.rating_value = 0  # 1-5 stars shown

    def get_porch_y(self):
        """Y position of the porch (delivery target)."""
        return self.y + 3


class Obstacle:
    """Moving or stationary obstacle."""
    def __init__(self, x, y, obs_type):
        self.x = float(x)
        self.y = float(y)
        self.obs_type = obs_type  # 'dog', 'car', 'trash', 'pirate'
        self.vx = 0.0
        self.vy = 0.0
        self.alive = True

        if obs_type == 'dog':
            self.vx = -random.uniform(0.3, 0.8)  # runs left toward road
            self.vy = random.uniform(-0.2, 0.2)
        elif obs_type == 'car':
            self.vy = -random.uniform(1.0, 2.0)  # drives up (toward player)
            self.x = random.uniform(ROAD_LEFT + 2, ROAD_RIGHT - 2)
        elif obs_type == 'pirate':
            self.vx = -random.uniform(0.5, 1.0)  # runs left after stealing


class Package:
    """Thrown package with arc physics."""
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.vx = 2.5  # rightward
        self.vy = random.uniform(-0.3, 0.3)  # slight vertical scatter
        self.gravity = 0.08
        self.active = True
        self.frames = 0

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += self.gravity
        self.frames += 1
        # Deactivate if off screen or past houses
        if self.x > SIZE or self.y > SIZE or self.y < 0:
            self.active = False


class Rocket:
    """Bezos rocket bonus — flies across the top of screen."""
    def __init__(self):
        self.x = -5.0
        self.y = random.uniform(2, 8)
        self.vx = 1.5
        self.active = True
        self.hit = False

    def update(self):
        self.x += self.vx
        if self.x > SIZE + 5:
            self.active = False


# ---------------------------------------------------------------------------
# Main game class
# ---------------------------------------------------------------------------

class PackageBoyGame:
    """Full game state for Package Boy."""

    def __init__(self):
        self.van_x = 6.0
        self.van_y = 32.0
        self.lives = 3
        self.scroll_y = 0.0
        self.scroll_speed = 0.5
        self.speed_boost = 0
        self.invincible = 0

        # Rating system (replaces score)
        self.deliveries = []  # list of star values (1-5)
        self.complaints = 0
        self.houses_passed = 0

        # Entities
        self.houses = []
        self.obstacles = []
        self.packages = []
        self.rocket = None

        # Timers
        self.house_spawn_timer = 0
        self.obstacle_spawn_timer = 0
        self.rocket_timer = random.randint(200, 400)
        self.van_bounce = 0  # animation counter

        # Feedback popups
        self.popup_text = ""
        self.popup_timer = 0
        self.popup_color = (255, 255, 255)

        # Spawn initial houses
        for i in range(4):
            self.houses.append(House(-10 + i * 18, random.random() < 0.6))

    def get_rating(self):
        """Calculate current driver rating (1.0-5.0)."""
        if not self.deliveries:
            return 5.0
        avg = sum(self.deliveries) / len(self.deliveries)
        # Complaints drag rating down
        penalty = self.complaints * 0.1
        return max(1.0, min(5.0, avg - penalty))

    def throw_package(self):
        """Throw a package from the van."""
        pkg = Package(self.van_x + 3, self.van_y + 1)
        self.packages.append(pkg)

    def update(self):
        """Update one frame of game logic."""
        self.van_bounce += 1
        speed = self.scroll_speed
        if self.speed_boost > 0:
            speed *= 1.8
            self.speed_boost -= 1
        if self.invincible > 0:
            self.invincible -= 1

        # Scroll everything
        self.scroll_y += speed
        for h in self.houses:
            h.y += speed
        for obs in self.obstacles:
            obs.y += speed

        # Update packages
        for pkg in self.packages[:]:
            pkg.update()
            if not pkg.active:
                self.packages.remove(pkg)
                continue
            # Check delivery collision
            for h in self.houses:
                if not h.delivered and h.subscriber:
                    porch_x = HOUSE_LEFT + 2
                    porch_y = h.get_porch_y()
                    dx = abs(pkg.x - porch_x)
                    dy = abs(pkg.y - porch_y)
                    if dx < 4 and dy < 3:
                        # Landed near porch
                        h.delivered = True
                        pkg.active = False
                        if dx < 2 and dy < 2:
                            stars = 5  # Perfect porch delivery
                            self._popup("5 STARS!", STAR_COLOR)
                        elif dx < 6:
                            stars = 3  # Yard delivery
                            self._popup("3 STARS", RATING_GOOD)
                        else:
                            stars = 2  # Bush
                            self._popup("BUSH...", RATING_BAD)
                        h.rating_value = stars
                        h.rating_popup = 20
                        self.deliveries.append(stars)
                        break
                # Check broken window (package hits house but not porch)
                elif not h.delivered:
                    house_x = HOUSE_LEFT
                    if (pkg.x >= house_x and pkg.x <= HOUSE_RIGHT and
                            abs(pkg.y - h.y) < 4 and pkg.frames > 5):
                        h.broken_window = True
                        h.delivered = True  # can't deliver anymore
                        pkg.active = False
                        self.deliveries.append(1)
                        self.complaints += 1
                        self._popup("1 STAR!", COMPLAINT_COLOR)
                        h.rating_value = 1
                        h.rating_popup = 25
                        break

        # Update obstacles
        for obs in self.obstacles[:]:
            obs.x += obs.vx
            obs.y += obs.vy
            # Remove if off screen
            if obs.y > SIZE + 10 or obs.y < -10 or obs.x < -10:
                self.obstacles.remove(obs)
                continue
            # Collision with van
            if self.invincible <= 0:
                if (abs(obs.x - self.van_x) < 4 and
                        abs(obs.y - self.van_y) < 3):
                    self.lives -= 1
                    self.invincible = 30  # brief invincibility
                    obs.alive = False
                    self.obstacles.remove(obs)
                    self.complaints += 1
                    if obs.obs_type == 'dog':
                        self._popup("DOG BITE!", COMPLAINT_COLOR)
                    elif obs.obs_type == 'car':
                        self._popup("CRASH!", COMPLAINT_COLOR)
                    else:
                        self._popup("OUCH!", COMPLAINT_COLOR)

        # Houses scrolling off bottom — check missed deliveries
        for h in self.houses[:]:
            if h.y > SIZE + 5:
                self.houses.remove(h)
                self.houses_passed += 1
                if h.subscriber and not h.delivered:
                    self.complaints += 1
                    self.deliveries.append(2)  # missed = low rating
                continue
            # Porch pirate logic
            if h.delivered and h.has_pirate and not h.broken_window:
                h.pirate_timer += 1
                if h.pirate_timer > 30:
                    h.has_pirate = False  # pirate stole it
                    self.complaints += 1

        # Spawn new houses
        self.house_spawn_timer += 1
        if self.house_spawn_timer > 24:
            self.house_spawn_timer = 0
            subscriber = random.random() < 0.6
            self.houses.append(House(-8, subscriber))

        # Spawn obstacles
        self.obstacle_spawn_timer += 1
        if self.obstacle_spawn_timer > random.randint(20, 50):
            self.obstacle_spawn_timer = 0
            obs_type = random.choices(
                ['dog', 'car', 'trash'],
                weights=[3, 2, 2], k=1)[0]
            if obs_type == 'dog':
                self.obstacles.append(
                    Obstacle(SIDEWALK_RIGHT, random.uniform(-5, 0), 'dog'))
            elif obs_type == 'car':
                self.obstacles.append(
                    Obstacle(random.uniform(3, 10), -8, 'car'))
            elif obs_type == 'trash':
                self.obstacles.append(
                    Obstacle(random.uniform(SIDEWALK_LEFT, SIDEWALK_RIGHT),
                             -5, 'trash'))

        # Bezos rocket bonus
        if self.rocket:
            self.rocket.update()
            if not self.rocket.active:
                self.rocket = None
            else:
                # Check if package hits rocket
                for pkg in self.packages[:]:
                    if (self.rocket and abs(pkg.x - self.rocket.x) < 3 and
                            abs(pkg.y - self.rocket.y) < 3):
                        self.rocket.hit = True
                        self.rocket.active = False
                        pkg.active = False
                        self.deliveries.extend([5, 5, 5])  # big bonus
                        self._popup("BEZOS!", STAR_COLOR)
                        self.rocket = None
                        break
        else:
            self.rocket_timer -= 1
            if self.rocket_timer <= 0:
                self.rocket = Rocket()
                self.rocket_timer = random.randint(300, 600)

        # Increase difficulty over time
        if self.houses_passed > 0 and self.houses_passed % 10 == 0:
            self.scroll_speed = min(1.5, self.scroll_speed + 0.02)

        # Update popup
        if self.popup_timer > 0:
            self.popup_timer -= 1

    def _popup(self, text, color):
        self.popup_text = text
        self.popup_timer = 15
        self.popup_color = color

    def is_game_over(self):
        return self.lives <= 0 or self.get_rating() < 1.5

    # --- Rendering ---

    def draw(self, tick=0):
        """Render the full game frame."""
        image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        draw = ImageDraw.Draw(image)

        # Draw road
        draw.rectangle([ROAD_LEFT, 0, ROAD_RIGHT, SIZE - 1], fill=ROAD_COLOR)
        # Dashed center line
        for y in range(0, SIZE, 8):
            line_y = int((y + tick * 2) % SIZE)
            if line_y < SIZE - 2:
                draw.rectangle([7, line_y, 8, line_y + 3], fill=ROAD_LINE)

        # Draw sidewalk
        draw.rectangle([SIDEWALK_LEFT, 0, SIDEWALK_RIGHT, SIZE - 1],
                       fill=SIDEWALK_COLOR)

        # Draw grass/yards
        draw.rectangle([HOUSE_LEFT - 2, 0, HOUSE_RIGHT, SIZE - 1],
                       fill=GRASS_COLOR)

        # Draw houses
        for h in self.houses:
            self._draw_house(draw, h, tick)

        # Draw obstacles
        for obs in self.obstacles:
            self._draw_obstacle(draw, obs)

        # Draw rocket
        if self.rocket and self.rocket.active:
            rx, ry = int(self.rocket.x), int(self.rocket.y)
            # Rocket body
            draw.rectangle([rx, ry, rx + 3, ry + 1], fill=ROCKET_COLOR)
            # Flame
            if tick % 4 < 2:
                draw.point((rx - 1, ry), fill=FLAME_COLOR)
                draw.point((rx - 1, ry + 1), fill=(255, 200, 0))

        # Draw packages in flight
        for pkg in self.packages:
            px, py = int(pkg.x), int(pkg.y)
            if 0 <= px < SIZE and 0 <= py < SIZE:
                draw.rectangle([px, py, px + 1, py + 1], fill=PACKAGE_COLOR)

        # Draw van
        self._draw_van(draw, tick)

        # Draw UI
        self._draw_ui(draw, image, tick)

        return image

    def _draw_van(self, draw, tick):
        """Draw the Amazon delivery van."""
        vx = int(self.van_x)
        vy = int(self.van_y) + (1 if tick % 8 < 4 else 0)  # bounce

        # Blink when invincible
        if self.invincible > 0 and tick % 4 < 2:
            return

        # Van body (5x3)
        draw.rectangle([vx - 2, vy - 1, vx + 2, vy + 1], fill=VAN_BODY)
        # Amazon stripe (orange)
        draw.line([(vx - 2, vy), (vx + 2, vy)], fill=VAN_STRIPE)
        # Wheels
        draw.point((vx - 2, vy - 1), fill=(40, 40, 40))
        draw.point((vx - 2, vy + 1), fill=(40, 40, 40))
        draw.point((vx + 2, vy - 1), fill=(40, 40, 40))
        draw.point((vx + 2, vy + 1), fill=(40, 40, 40))

    def _draw_house(self, draw, house, tick):
        """Draw a house with porch."""
        y = int(house.y)
        x = HOUSE_LEFT + 2
        if y < -8 or y > SIZE + 2:
            return

        # House body (8x6)
        color = house.color
        if house.broken_window:
            color = (80, 30, 30)  # reddish tint
        draw.rectangle([x, y, x + 7, y + 5], fill=color)
        # Roof
        draw.rectangle([x - 1, y - 1, x + 8, y], fill=ROOF_COLOR)
        # Door
        draw.rectangle([x + 3, y + 3, x + 4, y + 5], fill=(60, 40, 20))
        # Windows
        if not house.broken_window:
            draw.point((x + 1, y + 2), fill=(200, 200, 150))
            draw.point((x + 6, y + 2), fill=(200, 200, 150))
        else:
            draw.point((x + 1, y + 2), fill=(255, 50, 50))
            draw.point((x + 6, y + 2), fill=(255, 50, 50))

        # Porch (delivery target indicator)
        porch_y = int(house.get_porch_y())
        if house.subscriber and not house.delivered:
            # Lit porch — pulsing yellow
            pulse = int(180 + 75 * math.sin(tick * 0.2 + y))
            draw.point((x, porch_y), fill=(pulse, int(pulse * 0.83), 0))
        elif house.delivered and not house.broken_window:
            # Delivered — green check
            draw.point((x, porch_y), fill=(0, 200, 0))
            # Show package on porch
            draw.point((x + 1, porch_y), fill=PACKAGE_COLOR)

        # Star rating popup
        if house.rating_popup > 0:
            house.rating_popup -= 1
            star_color = STAR_COLOR if house.rating_value >= 4 else RATING_BAD
            _draw_digit(draw._image, str(house.rating_value),
                        x + 3, y - 4, star_color, SIZE)

        # Ring doorbell flash
        if house.delivered and house.ring_flash < 5:
            house.ring_flash += 1
            if house.ring_flash < 3:
                draw.point((x + 2, y + 3), fill=(255, 255, 255))

    def _draw_obstacle(self, draw, obs):
        """Draw an obstacle."""
        ox, oy = int(obs.x), int(obs.y)
        if oy < -5 or oy > SIZE + 5:
            return

        if obs.obs_type == 'dog':
            draw.rectangle([ox, oy, ox + 2, oy + 1], fill=DOG_COLOR)
            draw.point((ox + 2, oy - 1), fill=DOG_COLOR)  # head
        elif obs.obs_type == 'car':
            color = random.choice(CAR_COLORS) if not hasattr(obs, '_color') else obs._color
            if not hasattr(obs, '_color'):
                obs._color = random.choice(CAR_COLORS)
            color = obs._color
            draw.rectangle([ox - 1, oy - 2, ox + 1, oy + 2], fill=color)
            draw.point((ox, oy - 2), fill=(255, 255, 200))  # headlight
        elif obs.obs_type == 'trash':
            draw.rectangle([ox, oy, ox + 1, oy + 2], fill=TRASH_COLOR)

    def _draw_ui(self, draw, image, tick):
        """Draw UI overlay (rating, lives)."""
        # Rating display (top-left): ★ X.X
        rating = self.get_rating()
        rating_str = f"{rating:.1f}"
        # Star icon
        draw.point((1, 1), fill=STAR_COLOR)
        # Rating number
        color = RATING_GOOD if rating >= 4.0 else RATING_BAD if rating < 2.5 else (255, 255, 255)
        _draw_text(draw, rating_str, 4, 1, color, scale=1, spacing=0)

        # Lives (top-right): small van icons
        for i in range(self.lives):
            lx = SIZE - 4 - i * 4
            draw.rectangle([lx, 1, lx + 2, 2], fill=VAN_BODY)

        # Speed boost indicator
        if self.speed_boost > 0:
            _draw_text(draw, "FAST", 20, 1, VAN_STRIPE, scale=1, spacing=0)

        # Popup text (center of screen, brief)
        if self.popup_timer > 0:
            tw = _text_width(self.popup_text, scale=1, spacing=1)
            tx = max(0, (SIZE - tw) // 2)
            _draw_text(draw, self.popup_text, tx, 28, self.popup_color,
                       scale=1, spacing=1)


# ---------------------------------------------------------------------------
# AI Logic (Demo mode)
# ---------------------------------------------------------------------------

def _ai_update(game):
    """AI plays the game: dodges obstacles, throws at porches."""
    # Dodge obstacles
    nearest_threat = None
    nearest_dist = 999
    for obs in game.obstacles:
        if obs.obs_type == 'car' or obs.obs_type == 'dog':
            dy = abs(obs.y - game.van_y)
            dx = abs(obs.x - game.van_x)
            dist = dx + dy
            if dist < nearest_dist and obs.y > game.van_y - 15:
                nearest_dist = dist
                nearest_threat = obs

    # Dodge
    if nearest_threat and nearest_dist < 12:
        if nearest_threat.y > game.van_y:
            game.van_y = max(4, game.van_y - 1)
        else:
            game.van_y = min(SIZE - 4, game.van_y + 1)
    else:
        # Align with next subscriber house for delivery
        target_house = None
        for h in game.houses:
            if h.subscriber and not h.delivered and 0 < h.y < SIZE:
                target_house = h
                break

        if target_house:
            target_y = target_house.get_porch_y()
            if game.van_y < target_y - 1:
                game.van_y = min(SIZE - 4, game.van_y + 0.8)
            elif game.van_y > target_y + 1:
                game.van_y = max(4, game.van_y - 0.8)

            # Throw when aligned
            if abs(game.van_y - target_y) < 3 and len(game.packages) < 2:
                # Small random miss chance for realism
                if random.random() < 0.85:
                    game.throw_package()
        else:
            # Drift toward center
            if game.van_y < 30:
                game.van_y += 0.3
            elif game.van_y > 34:
                game.van_y -= 0.3

    # Try to hit rocket if visible
    if game.rocket and game.rocket.active:
        if abs(game.van_y - game.rocket.y) < 3 and game.rocket.x > game.van_x:
            game.throw_package()


# ---------------------------------------------------------------------------
# Demo mode
# ---------------------------------------------------------------------------

def _run_demo(matrix, duration, start_time):
    """AI-driven demo."""
    game = PackageBoyGame()
    tick = 0

    while time.time() - start_time < duration:
        if should_stop():
            return

        _ai_update(game)
        game.update()

        if game.is_game_over():
            rating = game.get_rating()
            if rating < 2.0:
                show_banner(matrix, ["DEACTIVATED", f"RATING:{rating:.1f}"],
                            color=COMPLAINT_COLOR, hold=1.5)
            else:
                show_banner(matrix, ["ROUTE DONE", f"RATING:{rating:.1f}"],
                            color=STAR_COLOR, hold=1.5)
            game = PackageBoyGame()
            tick = 0
            continue

        image = game.draw(tick)
        matrix.SetImage(image)
        tick += 1
        time.sleep(FRAME_DUR)


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

def _run_interactive(matrix, controller, start_time):
    """Player-controlled game."""
    from src.input.controller import wants_quit, Button, EventType

    _MAX_SECONDS = 600

    game = PackageBoyGame()
    tick = 0

    show_banner(matrix, ["PKG BOY", "A:THROW B:BOOST"],
                color=VAN_STRIPE, hold=1.2)

    while time.time() - start_time < _MAX_SECONDS:
        if should_stop():
            return
        controller.poll_events()
        if wants_quit(controller):
            return

        events = controller.poll_events()
        for ev in events:
            if ev.event_type in (EventType.PRESSED, EventType.REPEAT):
                if ev.button == Button.UP:
                    game.van_y = max(4, game.van_y - 2)
                elif ev.button == Button.DOWN:
                    game.van_y = min(SIZE - 4, game.van_y + 2)
                elif ev.button == Button.A:
                    if len(game.packages) < 3:
                        game.throw_package()
                elif ev.button == Button.B:
                    game.speed_boost = 20

        game.update()

        if game.is_game_over():
            rating = game.get_rating()
            safe_rumble(controller, 0.8, 400)
            if rating < 2.0:
                show_banner(matrix, ["DEACTIVATED", f"{rating:.1f} STARS"],
                            color=COMPLAINT_COLOR, hold=2.0)
            else:
                show_banner(matrix, ["ROUTE DONE!", f"{rating:.1f} STARS"],
                            color=STAR_COLOR, hold=2.0)
            return

        image = game.draw(tick)
        matrix.SetImage(image)
        tick += 1
        time.sleep(FRAME_DUR)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(matrix, duration=60, controller=None):
    """Run Package Boy.

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
        logger.error("Error in package_boy: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
