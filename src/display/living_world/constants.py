"""All module-level constants, block types, color definitions, dimensions,
timing values, house templates, light masks, etc."""

import math

# --- Display and world dimensions ---
DISPLAY_WIDTH, DISPLAY_HEIGHT = 64, 64
WORLD_WIDTH = 192
WIDTH, HEIGHT = DISPLAY_WIDTH, DISPLAY_HEIGHT
FRAME_INTERVAL = 1.0 / 18
DAY_CYCLE_SECONDS = 900.0

# Season system
SEASON_CYCLE_DAYS = 4          # Full season cycle = 4 day/night cycles
SEASONS = ["spring", "summer", "autumn", "winter"]

# Season color palettes for grass
SEASON_GRASS_COLORS = {
    "spring": (45, 190, 45),    # Bright fresh green
    "summer": (30, 180, 30),    # Normal green (current)
    "autumn": (140, 130, 30),   # Yellow-brown
    "winter": (160, 170, 170),  # Frost grey-white
}

# Season color palettes for leaves
SEASON_LEAF_COLORS = {
    "spring": (30, 170, 40),    # Light green
    "summer": (15, 140, 20),    # Normal green (current)
    "autumn": (180, 100, 20),   # Orange-brown
    "winter": (100, 80, 50),    # Dark brown (bare)
}

# Season modifiers
SEASON_TREE_GROWTH = {
    "spring": 1.5,    # Faster growth in spring
    "summer": 1.0,    # Normal
    "autumn": 0.5,    # Slower in autumn
    "winter": 0.0,    # No growth in winter
}

SEASON_FLOWER_CHANCE = {
    "spring": 0.8,    # Lots of flowers in spring
    "summer": 0.5,    # Normal (current base)
    "autumn": 0.2,    # Few flowers
    "winter": 0.0,    # No flowers in winter
}

SEASON_WEATHER_BIAS = {
    "spring": {"rain_weight": 1.5},    # More rain in spring
    "summer": {"rain_weight": 0.8},    # Less rain
    "autumn": {"rain_weight": 1.2},    # Moderate rain
    "winter": {"rain_weight": 0.5},    # Less rain, could add snow later
}

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
BIRD_PERCH_FRAME = [(0,0),(-1,0),(1,0)]  # folded wings: just the body row
BIRD_COLOR = (60, 40, 30)
BIRD_PERCH_CHANCE = 0.15          # probability per eligible tree check when bird passes over
BIRD_PERCH_DURATION = (60, 180)   # ticks to stay perched on a tree

# Shooting star constants
SHOOTING_STAR_CHANCE = 0.008      # per-tick chance during nighttime
SHOOTING_STAR_SPEED = 2.0         # pixels per tick (diagonal)
SHOOTING_STAR_LENGTH = 4          # trail length in pixels
SHOOTING_STAR_COLOR = (255, 255, 240)  # bright white-yellow
SHOOTING_STAR_TAIL_COLOR = (180, 180, 120)  # dimmer tail

# Eclipse system
SOLAR_ECLIPSE_PERIOD = 12         # every 12 day/night cycles
SOLAR_ECLIPSE_DURATION = 60       # ticks of darkness mid-day
LUNAR_ECLIPSE_PERIOD = 16         # every 16 day/night cycles
LUNAR_ECLIPSE_DURATION = 90       # ticks of red moon at night
ECLIPSE_AMBIENT_MIN = 0.08        # darkest ambient during solar eclipse

# Moon phase system -- 8 phases cycling over MOON_CYCLE_DAYS day/night periods
MOON_CYCLE_DAYS = 8              # full lunar cycle = 8 day/night periods
MOON_PHASES = [
    "new",              # 0 -- invisible
    "waxing_crescent",  # 1
    "first_quarter",    # 2
    "waxing_gibbous",   # 3
    "full",             # 4
    "waning_gibbous",   # 5
    "third_quarter",    # 6
    "waning_crescent",  # 7
]
# 3x3 moon masks: 1 = lit, 0 = dark.  Rows are top-to-bottom.
MOON_PHASE_MASKS = {
    "new":              [[0,0,0],[0,0,0],[0,0,0]],
    "waxing_crescent":  [[0,0,0],[0,0,1],[0,0,0]],
    "first_quarter":    [[0,1,1],[0,1,1],[0,1,1]],
    "waxing_gibbous":   [[1,1,1],[0,1,1],[1,1,1]],
    "full":             [[1,1,1],[1,1,1],[1,1,1]],
    "waning_gibbous":   [[1,1,1],[1,1,0],[1,1,1]],
    "third_quarter":    [[1,1,0],[1,1,0],[1,1,0]],
    "waning_crescent":  [[0,0,0],[1,0,0],[0,0,0]],
}
MOON_DARK_COLOR = (40, 40, 55)   # shadow side of the moon

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
VILLAGER_CHOP_THRESHOLD = 4       # villager only chops when lumber < this (was 6, lowered to diversify behavior)
VILLAGER_EXPLORE_CHANCE = 0.35    # chance to wander instead of chop when not desperate for lumber
VILLAGER_PLANT_CHANCE = 0.5       # chance to plant a tree when lumber >= 1 and area is sparse (was 0.3)
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

# Castle constants
CASTLE_COST_LUMBER = 10
CASTLE_COST_STONE = 5
CASTLE_BUILD_FRAMES = 300
CASTLE_WIDTH = 7
CASTLE_HEIGHT = 8
CASTLE_POPULATION_THRESHOLD = 8
MAX_CASTLES = 1
# Castle pixel art template (7 wide x 8 tall)
# T = tower top, B = battlements, W = wall, D = door, N = window, G = gate, A = air
CASTLE_TEMPLATE = [
    'TAAAABT',
    'BWWWWWB',
    'WWWNWWW',
    'WWWWWWW',
    'WWNWNWW',
    'WWWWWWW',
    'WWWGWWW',
    'WWWDWWW',
]
CASTLE_PAL = {
    'wall': (130, 130, 140),
    'tower': (100, 100, 115),
    'battlement': (110, 110, 125),
    'door': (70, 45, 20),
    'window_day': (180, 200, 220),
    'window_night': (220, 180, 60),
    'gate': (80, 55, 25),
}

# Artificial light cap -- prevents pixel blowout from overlapping light sources
MAX_LIGHT_LEVEL = 220

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
    "farming": (180, 140, 40),
    "eating": (50, 200, 100),
    "hunting": (180, 50, 50),
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

# Animal mobs
MAX_DEER = 3
MAX_RABBITS = 4
ANIMAL_SPAWN_INTERVAL = 400       # Ticks between spawn checks
ANIMAL_FLEE_RADIUS = 8            # Pixels -- animals flee from nearby villagers
ANIMAL_FLEE_DURATION = 30         # Ticks to flee before calming
ANIMAL_IDLE_RANGE = (60, 180)     # Ticks to stay idle before walking
ANIMAL_WALK_RANGE = (30, 60)      # Ticks to walk before going idle

# Animal colors
DEER_COLOR = (140, 100, 50)       # Brown body
DEER_HEAD_COLOR = (160, 120, 60)  # Lighter head
RABBIT_COLOR = (180, 170, 150)    # Grey-white body
RABBIT_EAR_COLOR = (200, 190, 170) # Lighter ears

# Season animal spawn modifier (reuse flower chance as proxy)
SEASON_ANIMAL_CHANCE = {
    "spring": 1.0,
    "summer": 1.0,
    "autumn": 0.6,
    "winter": 0.2,
}

# --- Villager names and traits ---
VILLAGER_FIRST_NAMES = [
    "Ash", "Elm", "Oak", "Ivy", "Fern", "Reed", "Sage", "Clay", "Flint",
    "Brook", "Dale", "Glen", "Heath", "Moss", "Thorn", "Wren", "Lark",
    "Pike", "Slate", "Birch", "Hazel", "Briar", "Stone", "Wolf",
]
VILLAGER_TRAITS = ["builder", "farmer", "lumberjack", "explorer"]
TRAIT_GOAL_BONUS = 0.20  # +20% score for preferred activities

# Hunting constants
HUNTING_HUNGER_THRESHOLD = 60.0   # hunger level to trigger hunting
HUNTING_CHASE_SPEED = 0.8         # villager speed when chasing
HUNTING_CATCH_RADIUS = 2          # pixels to catch animal
HUNTING_KILL_FOOD = 2             # food gained from successful hunt
HUNTING_CHASE_FRAMES = 60         # max ticks to chase before giving up
BUBBLE_HUNTING_COLOR = (180, 50, 50)  # red-ish bubble for hunting

# Bow hunting constants
BOW_COST_LUMBER = 1               # lumber to craft a bow
BOW_RANGE = 10                    # pixels -- ranged kill distance
BOW_SHOOT_FRAMES = 15             # ticks to aim and shoot
BOW_HUNTING_FOOD = 2              # food from ranged kill (same as melee)

# Snow weather constants
SNOW_ACCUMULATION_MAX = 1         # max snow depth in pixels on terrain
SNOW_MELT_RATE = 0.01             # chance per column per tick to melt in spring
SNOW_FALL_COUNT = (10, 20)        # snowflakes per frame during winter storm
SNOW_COLOR = (230, 235, 245)      # off-white snowflake color
SNOW_GROUND_COLOR = (220, 225, 235)  # snow-covered ground

# --- Farming constants ---
FARM_WIDTH = 4                    # crop slots per farm plot
FARM_COST_LUMBER = 2              # lumber to build a farm
FARM_BUILD_FRAMES = 60            # ticks to till/prepare the farm
FARM_POPULATION_THRESHOLD = 3     # min population before farming starts
MAX_FARMS_PER_HOUSE = 1           # farms per house owner
CROP_GROWTH_RATE = 0.002          # base growth per tick (same cadence as trees)
CROP_HARVEST_YIELD = 1            # food per harvested mature crop
FARM_PLANT_FRAMES = 20            # ticks to plant all slots
FARM_HARVEST_FRAMES = 20          # ticks to harvest
FARM_GROWTH_CHECK_INTERVAL = 10   # ticks between crop growth updates

# Season crop growth modifiers
SEASON_CROP_GROWTH = {
    "spring": 1.5,
    "summer": 1.0,
    "autumn": 0.5,
    "winter": 0.0,
}

# --- Goal system constants ---
GOAL_EVAL_INTERVAL = 60           # ticks between full goal re-evaluation
FOOD_SHARE_THRESHOLD = 3          # villager shares food when they have > this
GOAL_PRIORITY = {
    "build_campfire":    85,      # survival: no light at night
    "get_food":          80,      # survival: critically hungry, no food
    "build_house":       70,      # major progression milestone
    "farm_harvest":      65,      # free food, quick payoff
    "refuel_campfire":   55,      # maintenance
    "share_food":        53,      # food sharing with hungry neighbors
    "gather_lumber":     50,      # core resource (dynamic: +5 per missing lumber below threshold)
    "have_baby":         48,      # reproduction as goal
    "build_farm":        45,      # food infrastructure
    "farm_plant":        40,      # food production pipeline
    "build_granary":     35,      # community infrastructure
    "upgrade_house":     30,      # progression
    "gather_stone":      28,      # prereq for upgrades/watchtower
    "build_watchtower":  25,      # community infrastructure
    "build_mine":        22,      # resource infrastructure
    "build_bridge":      20,      # connectivity
    "plant_tree":        15,      # sustainability
    "build_castle":      16,      # late-game mega-structure
    "build_well":        18,      # fire prevention infrastructure
    "build_storage":     32,      # community storage building
    "build_bank":        14,      # gold bank building
    "deposit_storage":   12,      # deposit excess items in storage
    "withdraw_storage":  52,      # withdraw needed items from storage (high priority)
    "flatten_terrain":   10,      # cleanup
    "explore":            5,      # default
}
# Resource prerequisites for each goal: {resource: amount_needed}
GOAL_PREREQS = {
    "build_house":       {"lumber": 4},
    "upgrade_house":     {"lumber": 6, "stone": 2},
    "build_campfire":    {"lumber": 2},
    "build_farm":        {"lumber": 2},
    "build_granary":     {"lumber": 5},
    "build_watchtower":  {"lumber": 4, "stone": 2},
    "build_mine":        {"lumber": 2},
    "build_bridge":      {"lumber": 2},
    "build_well":        {"lumber": 1, "stone": 2},
    "build_castle":      {"lumber": 10, "stone": 5},
    "build_storage":     {"lumber": 4, "stone": 1},
    "build_bank":        {"lumber": 5, "stone": 3},
    "refuel_campfire":   {"lumber": 1},
    "plant_tree":        {"lumber": 1},
}

# --- Well constants ---
MAX_WELLS = 3
WELL_COST_LUMBER = 1
WELL_COST_STONE = 2
WELL_BUILD_FRAMES = 90
WELL_FIRE_PREVENTION_RADIUS = 15       # no fires can start within this radius
WELL_MIN_SPACING = 25                   # wells cannot be within this distance of each other
WELL_POPULATION_THRESHOLD = 4           # min population to build a well
WELL_WIDTH = 1
WELL_HEIGHT = 2

# Well rendering colors
WELL_STONE_COLOR = (100, 100, 115)
WELL_WATER_COLOR = (50, 100, 210)
WELL_ROOF_COLOR = (90, 50, 15)

# --- Boat travel constants ---
BOAT_COST_LUMBER = 2              # lumber to craft a boat
BOAT_SPEED = 0.5                  # pixels per tick on water
BOAT_COLOR = (120, 75, 25)        # brown boat hull
BOAT_DECK_COLOR = (100, 60, 20)   # darker deck
BOAT_WIDTH = 3                    # rendered width in pixels

# --- Trade caravan constants ---
CARAVAN_SPAWN_INTERVAL = 5000     # ticks between caravan arrivals
CARAVAN_TRADE_DURATION = 120      # ticks caravan stays to trade
CARAVAN_SPEED = 0.4               # pixels per tick walking speed
CARAVAN_COLOR = (160, 120, 60)    # brown cloak
CARAVAN_PACK_COLOR = (130, 90, 40)  # darker pack
CARAVAN_TRADE_RADIUS = 3          # pixels -- villager must be within to trade

# --- Community storage constants ---
STORAGE_COST_LUMBER = 4
STORAGE_COST_STONE = 1
STORAGE_BUILD_FRAMES = 100
STORAGE_WIDTH = 3
STORAGE_HEIGHT = 3
STORAGE_POPULATION_THRESHOLD = 3
MAX_STORAGES = 2
STORAGE_TEMPLATE = ['RRR', 'WSW', 'WDW']
STORAGE_PAL = {
    'wall': (100, 65, 25),
    'roof': (110, 50, 25),
    'door': (55, 35, 15),
    'shelf': (130, 100, 50),
}
STORAGE_MAX_LUMBER = 30
STORAGE_MAX_STONE = 15
STORAGE_MAX_FOOD = 20
STORAGE_DEPOSIT_THRESHOLD_LUMBER = 5   # deposit excess above this
STORAGE_DEPOSIT_THRESHOLD_STONE = 3
STORAGE_DEPOSIT_THRESHOLD_FOOD = 4

# --- Gold and Bank constants ---
GOLD_MINE_CHANCE = 0.25           # chance to find gold when mining (per 2 depths)
GOLD_COLOR = (220, 200, 50)       # gold nugget color
MAX_BANKS = 1
BANK_COST_LUMBER = 5
BANK_COST_STONE = 3
BANK_BUILD_FRAMES = 150
BANK_WIDTH = 4
BANK_HEIGHT = 4
BANK_POPULATION_THRESHOLD = 6
BANK_TEMPLATE = ['ARRA', 'RRRR', 'WWNW', 'WDDW']
BANK_PAL = {
    'wall': (140, 130, 100),
    'roof': (90, 85, 75),
    'door': (70, 50, 20),
    'window_day': (180, 200, 220),
    'window_night': (220, 200, 80),
    'gold_accent': (200, 180, 50),
}

# --- Hunger system constants ---
HUNGER_MAX = 100.0                # maximum hunger level (starving)
HUNGER_RATE = 0.015               # hunger increase per AI tick (every 3 sim ticks)
HUNGER_THRESHOLD = 50.0           # hunger level at which villager prioritizes food
HUNGER_CRITICAL = 80.0            # hunger level for desperate food-seeking
HUNGER_SPEED_PENALTY = 0.5        # movement speed multiplier when critically hungry
FOOD_SATIATION = 40.0             # hunger points reduced per food item eaten
EATING_FRAMES = 25                # ticks spent in "eating" state
HUNGER_EAT_THRESHOLD = 30.0      # minimum hunger before villager bothers eating (won't eat when nearly full)

# Rain crop growth multipliers
RAIN_CROP_GROWTH_MULTIPLIER = 1.5
STORM_CROP_GROWTH_MULTIPLIER = 2.0

# Farm rendering colors
TILLED_SOIL_COLOR = (90, 55, 25)
CROP_COLORS = {
    "seeded":    (90, 55, 25),
    "sprouting": (50, 140, 30),
    "growing":   (30, 180, 40),
    "mature":    (200, 180, 50),
}
