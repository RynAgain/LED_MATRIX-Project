"""All entity/data classes."""

import random
import math

from .constants import (
    VILLAGER_CLOTHES_COLORS, VILLAGER_SKIN_COLORS,
    VILLAGER_MIN_AGE, VILLAGER_MAX_AGE,
    CAMPFIRE_INITIAL_FUEL, MINE_MAX_DEPTH,
    WEATHER_CLEAR, WEATHER_DURATION, STORM_FACTOR,
    WEATHER_RAIN, WEATHER_STORM,
    RAIN_COLOR_BASE,
)
from .utils import _clamp


class Cloud:
    def __init__(self, x, y, width, height, speed, direction, alpha=None):
        self.x, self.y, self.width, self.height = float(x), y, width, height
        self.speed, self.direction = speed, direction
        self.alpha = alpha
        self.shape = self._generate_shape()
    def _generate_shape(self):
        shape = [[True]*self.width for _ in range(self.height)]
        for ri in (0, self.height-1):
            if self.height < 2: break
            for c in range(min(random.randint(1,3), self.width)): shape[ri][c] = False
            for c in range(min(random.randint(1,3), self.width)): shape[ri][self.width-1-c] = False
        mid = self.height // 2
        for c in range(self.width): shape[mid][c] = True
        return shape

class Bird:
    def __init__(self, x, base_y, direction, speed, phase):
        self.x, self.base_y, self.y = float(x), float(base_y), float(base_y)
        self.direction, self.speed, self.wing_frame, self.phase = direction, speed, 0, phase
    def screen_y(self, tick):
        return self.base_y + math.sin(tick * 0.12 + self.phase) * 1.5

class Tree:
    def __init__(self, x, base_y, growth, max_height, canopy_radius, style):
        self.x, self.base_y, self.growth = x, base_y, growth
        self.max_height, self.canopy_radius = max_height, canopy_radius
        self.trunk_height = max_height - canopy_radius
        self.style, self.alive, self.dying = style, True, False
        self.dying_progress, self.dead_timer, self.mature_timer = 0.0, 0, 0
        self.on_fire, self.fire_timer = False, 0

class Villager:
    def __init__(self, x, y):
        self.x, self.y, self.state, self.target_x = x, y, "idle", x
        self.task_timer, self.lumber, self.stone = 0, 0, 0
        self.head_color = random.choice(VILLAGER_CLOTHES_COLORS)
        self.body_color = random.choice(VILLAGER_SKIN_COLORS)
        self.direction = random.choice([-1, 1])
        self.home, self.build_type, self.target_tree, self.idle_timer = None, None, None, 0
        self.age, self.max_age = 0, random.randint(VILLAGER_MIN_AGE, VILLAGER_MAX_AGE)
        self.upgrade_target, self.refuel_target = None, None
        self.children_born, self.flatten_target, self.mine_target = 0, None, None
        self.entering, self.building_target, self.build_total_time = False, None, 0
        self.bubble_timer, self.bubble_color = 0, None
        self.on_bridge = None
        self._bridge_gap = None
        self.climb_timer = 0
        self.firefight_target = None

class Structure:
    def __init__(self, stype, x, y, width, height):
        self.type, self.x, self.y, self.width, self.height = stype, x, y, width, height
        self.flame_frame, self.owner, self.door_x, self.level = 0, None, x, 1
        self.style = random.randint(0, 2)
        self.fuel = CAMPFIRE_INITIAL_FUEL if stype == "campfire" else 0
        self.cremation_flash, self.depth, self.max_depth = 0, 0, MINE_MAX_DEPTH
        self.stone_built, self.under_construction, self.build_progress = False, False, 1.0
        self.stored_lumber = 0

class LumberItem:
    def __init__(self, x, y): self.x, self.y, self.age = x, y, 0

class Firefly:
    def __init__(self, x, y, phase):
        self.x, self.y, self.phase = float(x), float(y), phase
        self.lifetime, self.age = random.randint(200, 600), 0

class Smoke:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.dx, self.age, self.max_age = random.uniform(-0.1, 0.1), 0, random.randint(40, 80)

class FishJump:
    def __init__(self, x, base_y, max_height):
        self.x, self.base_y, self.progress, self.max_height = x, base_y, 0, max_height

class Flower:
    def __init__(self, x, y, color): self.x, self.y, self.color = x, y, color

class RainDrop:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.speed = random.randint(2, 3)
        self.color = (_clamp(RAIN_COLOR_BASE[0]+random.randint(-10,10),0,255),
                      _clamp(RAIN_COLOR_BASE[1]+random.randint(-10,10),0,255),
                      _clamp(RAIN_COLOR_BASE[2]+random.randint(-10,10),0,255))
        self.splash, self.splash_x, self.splash_y = False, 0, 0

class GrassFire:
    def __init__(self, x, y, dur): self.x, self.y, self.timer = x, y, dur

class Weather:
    def __init__(self):
        self.state = WEATHER_CLEAR
        self.timer = random.randint(*WEATHER_DURATION[WEATHER_CLEAR])
        self.prev_state, self.transition_frames, self.storm_factor = WEATHER_CLEAR, 0, 1.0
        self.lightning_flash, self.lightning_bolt, self.lightning_bolt_timer = 0, None, 0
        self.wind_dir = random.choice([-1, 1])
        self.tree_sway_offset, self.sway_timer = 0, 0
    def target_storm_factor(self):
        return STORM_FACTOR[self.state]
    def is_raining(self):
        return self.state in (WEATHER_RAIN, WEATHER_STORM)
    def is_storming(self):
        return self.state == WEATHER_STORM
