"""All module-level constants, block types, color definitions, dimensions,
timing values, house templates, light masks, etc."""

import math

# --- Display and world dimensions ---
DISPLAY_WIDTH, DISPLAY_HEIGHT = 64, 64
WORLD_WIDTH = 192
WIDTH, HEIGHT = DISPLAY_WIDTH, DISPLAY_HEIGHT
FRAME_INTERVAL = 1.0 / 18
DAY_CYCLE_SECONDS = 900.0

AIR, GRASS, DIRT, STONE, WATER, WOOD, LEAF, SAND = 0, 1, 2, 3, 4, 5, 6, 7
LUMBER_BLOCK, HOUSE_BLOCK, CAMPFIRE_BLOCK, PATH_DIRT, MINE_BLOCK = 8, 9, 10, 15, 16

BLOCK_COLORS = {
    GRASS: (30,180,30), DIRT: (120,72,36), STONE: (90,90,100), WATER: (25,80,200),
    WOOD: (100,60,25), LEAF: (15,140,20), SAND: (210,190,100), LUMBER_BLOCK: (140,90,40),
    HOUSE_BLOCK: (130,85,45), CAMPFIRE_BLOCK: (200,100,20), PATH_DIRT: (100,65,30),
    MINE_BLOCK: (30,30,40),
}

WATER_SURFACE_COLOR = (40, 100, 220)
BASE_GROUND, TERRAIN_MIN, TERRAIN_MAX = 42, 30, 52
OCTAVES = [(5, 0.08), (2, 0.20), (1, 0.45)]

BIRD_FRAMES = [
    [(-1,-1),(1,-1),(-1,0),(0,0),(1,0)],
    [(-1,0),(0,0),(1,0),(-1,1),(1,1)],
]
BIRD_COLOR = (60, 40, 30)

SKY_NIGHT      = ((5,5,20),(10,10,35))
SKY_DAWN_EARLY = ((20,10,40),(180,80,40))
SKY_DAWN_LATE  = ((60,60,140),(220,140,80))
SKY_DAY        = ((30,100,220),(100,180,255))
SKY_DUSK_EARLY = ((60,60,140),(220,120,60))
SKY_DUSK_LATE  = ((20,10,40),(160,50,30))

SUN_COLOR, MOON_COLOR = (255,220,50), (200,200,220)
DYING_LEAF_COLORS = [(15,140,20),(80,140,20),(140,120,20),(100,80,20)]
CAMPFIRE_COLORS = [(255,140,0),(255,80,0),(255,200,50),(220,60,10),(255,180,30)]
CAMPFIRE_LOW_FUEL_COLORS = [(180,90,0),(160,50,0),(180,130,30),(140,40,5),(160,110,20)]
VILLAGER_SKIN_COLORS = [(200,160,120),(160,110,70),(120,80,50),(220,180,150)]
VILLAGER_CLOTHES_COLORS = [(180,40,40),(40,80,180),(40,160,60),(180,160,40),(140,60,160)]
FLOWER_COLORS = [(220,50,50),(255,220,50),(180,50,220),(240,240,240)]

MAX_VILLAGERS = 20
VILLAGERS_PER_HOUSE = 2
BASE_VILLAGERS = 2
TREE_BUILDING_MIN_SPACING = 2
VILLAGER_SPAWN_INTERVAL = 2700
CAMPFIRE_INITIAL_FUEL = 5400
CAMPFIRE_REFUEL_AMOUNT = 2700
CAMPFIRE_LOW_FUEL_THRESHOLD = 900
CAMPFIRE_MIN_SPACING = 10
VILLAGER_MIN_AGE, VILLAGER_MAX_AGE = 12000, 18000
CREMATION_FLASH_FRAMES = 10
REPRODUCTION_MIN_AGE, REPRODUCTION_MAX_AGE, REPRODUCTION_CHANCE, MAX_CHILDREN = 2000, 10000, 1800, 3
VILLAGER_MAX_CLIMB = 3        # maximum height difference a villager can climb in one step
VILLAGER_CLIMB_SPEED = 2      # extra ticks of pause when climbing 2-3 blocks
FLATTEN_DURATION, FLATTEN_STEEP_THRESHOLD, FLATTEN_EXTREME_THRESHOLD = 60, 2, 3
HOUSE_FLATTEN_RADIUS = 5       # pixels on each side of house to flatten
HOUSE_FLATTEN_INTERVAL = 500   # ticks between house-area flattening checks
HOUSE_FLATTEN_RATE = 1         # blocks per flattening tick a villager adjusts
MINE_MAX_DEPTH, MINE_DIG_FRAMES, MAX_MINES, MINE_POPULATION_THRESHOLD = 8, 45, 2, 3
MINE_COLOR = (30, 30, 40)
STONE_HOUSE_COLOR = (110, 95, 80)

# Bridge constants
MAX_BRIDGES = 3
BRIDGE_BUILD_FRAMES = 90
BRIDGE_COLOR = (100, 60, 20)
BRIDGE_RAILING_COLOR = (70, 40, 12)
BRIDGE_MAX_GAP = 12

# Community building constants
WATCHTOWER_COST_LUMBER = 4
WATCHTOWER_COST_STONE = 2
WATCHTOWER_BUILD_FRAMES = 150
WATCHTOWER_WIDTH = 2
WATCHTOWER_HEIGHT = 7
WATCHTOWER_POPULATION_THRESHOLD = 5
GRANARY_COST_LUMBER = 5
GRANARY_BUILD_FRAMES = 120
GRANARY_WIDTH = 3
GRANARY_HEIGHT = 4
GRANARY_POPULATION_THRESHOLD = 4

# Torch post constants
MAX_TORCH_POSTS = 5
TORCH_POST_PATH_THRESHOLD = 30
TORCH_POST_CHECK_INTERVAL = 300

# Speech bubble constants
BUBBLE_DURATION = 15
BUBBLE_COLORS = {
    "chopping": (220, 50, 50),
    "building": (220, 200, 50),
    "planting": (50, 200, 50),
    "trading": (50, 100, 220),
    "mining": (150, 150, 150),
    "firefighting": (255, 120, 0),
}

CAMERA_FOLLOW_RE_EVAL = 300
CAMERA_SMOOTH_SPEED = 3

WEATHER_CLEAR, WEATHER_CLOUDY, WEATHER_RAIN, WEATHER_STORM = "clear", "cloudy", "rain", "storm"
WEATHER_DURATION = {"clear":(2000,5000),"cloudy":(500,1000),"rain":(1000,3000),"storm":(500,1500)}
STORM_FACTOR = {"clear":1.0,"cloudy":0.8,"rain":0.6,"storm":0.45}
WEATHER_CLOUD_PARAMS = {
    "clear":(2,4,(240,240,250),False), "cloudy":(4,6,(180,180,190),False),
    "rain":(5,7,(120,120,130),True), "storm":(8,12,(80,80,90),True),
}
CLOUD_WIDTH_RANGE = (6, 12)
CLOUD_HEIGHT_RANGE = (2, 3)
STORM_CLOUD_WIDTH_RANGE = (12, 20)
STORM_CLOUD_HEIGHT_RANGE = (3, 5)
CLOUD_ALPHA = 0.7
STORM_CLOUD_ALPHA = 0.85
RAIN_COLOR_BASE = (150,170,220)
RAIN_COUNT_RAIN, RAIN_COUNT_STORM = (15,25), (25,40)
LIGHTNING_CHANCE = 90
LIGHTNING_FLASH_FRAMES, LIGHTNING_BOLT_FRAMES = 3, 2
LIGHTNING_BOLT_COLOR = (255,255,220)
LIGHTNING_TREE_FIRE_CHANCE, LIGHTNING_GRASS_FIRE_CHANCE = 0.20, 0.05
TREE_FIRE_DURATION = 30
FIREFIGHT_DETECT_RADIUS = 20
FIREFIGHT_EXTINGUISH_TICKS = 10

# Rain growth multipliers
RAIN_GROWTH_MULTIPLIER = 2.0       # Trees grow 2x faster in rain
STORM_GROWTH_MULTIPLIER = 3.0      # Trees grow 3x faster in storms
RAIN_FLOWER_SPAWN_BOOST = 0.75     # Flower spawn chance in rain (vs 0.5 base)
STORM_FLOWER_SPAWN_BOOST = 0.90    # Flower spawn chance in storm (vs 0.5 base)
WATER_RISE_RAIN_INTERVAL, WATER_RISE_STORM_INTERVAL, WATER_RECEDE_INTERVAL = 30, 20, 60
WEATHER_TRANSITION_FRAMES, WIND_SWAY_INTERVAL = 60, 30

HOUSE_TEMPLATES = {
    1: {'width':3,'height':4,'grid':['ARA','RRR','WNW','WDW']},
    2: {'width':4,'height':6,'grid':['ACAA','ARRA','RRRR','WWNW','WNWW','WDDW']},
    3: {'width':5,'height':6,'grid':['AACAA','ARRRA','RRRRR','WNWNW','WWWWW','WWDWW']},
}
HOUSE_COLORS = {
    1: [
        {'wall':(100,60,20),'roof':(120,50,30),'door':(50,30,15),'window_day':(180,200,220),'window_night':(200,180,80),'chimney':None},
        {'wall':(115,70,25),'roof':(125,55,35),'door':(55,35,18),'window_day':(180,200,220),'window_night':(200,180,80),'chimney':None},
        {'wall':(85,55,25),'roof':(115,45,25),'door':(45,28,12),'window_day':(180,200,220),'window_night':(200,180,80),'chimney':None},
    ],
    2: [
        {'wall':(120,75,30),'roof':(140,45,35),'door':(60,35,15),'window_day':(180,200,220),'window_night':(200,180,80),'chimney':(100,100,110)},
        {'wall':(120,75,30),'roof':(40,80,45),'door':(60,35,15),'window_day':(180,200,220),'window_night':(200,180,80),'chimney':(100,100,110)},
        {'wall':(130,80,35),'roof':(140,45,35),'door':(55,30,15),'window_day':(180,200,220),'window_night':(200,180,80),'chimney':(105,105,115)},
    ],
    3: [
        {'wall':(130,125,115),'roof':(80,80,90),'door':(60,35,15),'window_day':(180,200,220),'window_night':(200,170,70),'chimney':(90,85,80)},
        {'wall':(100,95,90),'roof':(80,80,90),'door':(60,35,15),'window_day':(180,200,220),'window_night':(200,170,70),'chimney':(90,85,80)},
        {'wall':(130,125,115),'roof':(75,75,85),'door':(55,30,12),'window_day':(180,200,220),'window_night':(200,170,70),'chimney':(85,80,75)},
    ],
}
HOUSE_DIMENSIONS = {1:(3,4), 2:(4,6), 3:(5,6)}

# Granary pixel art template (3 wide x 4 tall)
GRANARY_TEMPLATE = ['ARA','RRR','WWW','WDW']
GRANARY_PAL = {'wall':(110,70,25),'roof':(130,55,30),'door':(60,35,15)}

# Watchtower colors
WT_STONE = (120, 120, 130)
WT_POLE = (90, 50, 15)
WT_PLATFORM = (100, 60, 20)
WT_TORCH = (255, 180, 50)

LIGHT_MASK = []
for _dy in range(-7,8):
    for _dx in range(-7,8):
        _d = math.sqrt(_dx*_dx+_dy*_dy)
        if _d <= 7.0:
            LIGHT_MASK.append((_dx,_dy,int(255*max(0.0,1.0-_d/7.0))))
LANTERN_MASK = []
for _dy in range(-3,4):
    for _dx in range(-3,4):
        _d = math.sqrt(_dx*_dx+_dy*_dy)
        if _d <= 3.0:
            LANTERN_MASK.append((_dx,_dy,int(255*max(0.0,1.0-_d/3.0))))
WATCHTOWER_LIGHT_MASK = []
for _dy in range(-5,6):
    for _dx in range(-5,6):
        _d = math.sqrt(_dx*_dx+_dy*_dy)
        if _d <= 5.0:
            WATCHTOWER_LIGHT_MASK.append((_dx,_dy,int(255*max(0.0,1.0-_d/5.0))))
TORCH_POST_LIGHT_MASK = []
for _dy in range(-2,3):
    for _dx in range(-2,3):
        _d = math.sqrt(_dx*_dx+_dy*_dy)
        if _d <= 2.0:
            TORCH_POST_LIGHT_MASK.append((_dx,_dy,int(255*max(0.0,1.0-_d/2.0))))
