# Living World -- Feature Tracker

> Auto-generated inventory of every implemented feature in the
> `src/display/living_world/` package.  Each entry references the source
> module where the logic lives.

---

## Module Structure

```
src/display/living_world/
  __init__.py        -- Package entry point; re-exports run()
  constants.py       -- All tunable numbers, block types, color palettes, templates, light masks
  utils.py           -- Pure helpers: clamp, lerp_color, cosine_interp, apply_ambient
  entities.py        -- Data classes for every entity (Cloud, Bird, Tree, Villager, Structure, ...)
  terrain.py         -- Procedural world generation and terrain modification
  day_night.py       -- Day/night cycle phase & sky color computation
  weather.py         -- Weather state machine, rain, lightning, water-level changes
  structures.py      -- Build-site search, bridge logic, foundation leveling, ownership
  villager_ai.py     -- Full villager behavior FSM, spawning, reproduction, aging
  world_updates.py   -- Non-villager entity ticks: trees, clouds, birds, ambient life, torches
  rendering.py       -- All pixel-writing draw functions (sky, terrain, entities, effects)
  lighting.py        -- Post-processing light passes (campfire, lantern, watchtower, torch)
  simulation.py      -- Frame loop orchestration, camera system, PIL image management
```

### main.py integration

Line 348 of [`src/main.py`](../src/main.py:348):

```python
"living_world": "src.display.living_world",
```

`importlib.import_module("src.display.living_world")` resolves to
[`__init__.py`](../src/display/living_world/__init__.py:1) which exports
[`run`](../src/display/living_world/simulation.py:81).  **No changes to
main.py are required.**

---

## Feature Categories

### 1. Terrain & World Generation

- [x] Multi-octave sinusoidal height profile -- 3-octave Perlin-style height map with configurable amplitudes/frequencies (`terrain.py`)
- [x] Layered block filling -- grass surface, dirt sub-layer (4 deep), stone below (`terrain.py`)
- [x] Valley flood-fill -- automatic water placement in terrain valleys (`terrain.py`)
- [x] Guaranteed pond -- if no water exists after flooding, a pond is carved at the lowest point (`terrain.py`)
- [x] Water settling simulation -- iterative gravity + lateral spread for realistic water (`terrain.py`)
- [x] Sand placement -- sand blocks placed adjacent to water bodies (`terrain.py`)
- [x] Tree placement -- 9-18 trees placed with minimum spacing, avoiding water columns (`terrain.py`)
- [x] Star field generation -- 15-25 random stars in the upper sky region (`terrain.py`)
- [x] Terrain flattening -- villagers smooth steep terrain near build sites and homes (`terrain.py`)
- [x] Extreme terrain correction -- villagers fix steep drops/rises near their houses (`terrain.py`)
- [x] Path wear system -- grass worn into dirt paths by villager foot traffic (`villager_ai.py`, `rendering.py`)
- [x] 192-column scrollable world -- world is 3x display width for camera panning (`constants.py`)
- [x] House area flattening -- terrain within 5 pixels of completed houses is gradually leveled to house ground height (`terrain.py`, `world_updates.py`, `simulation.py`)

### 2. Day/Night Cycle

- [x] Continuous day phase -- elapsed time mapped to 0.0-1.0 phase over configurable cycle (`day_night.py`)
- [x] Four named phases -- dawn / day / dusk / night with distinct boundaries (`day_night.py`)
- [x] Cosine-interpolated ambient brightness -- smooth 0.15 (night) to 1.0 (day) transitions (`day_night.py`)
- [x] Six-zone sky gradient -- night -> dawn_early -> dawn_late -> day -> dusk_early -> dusk_late with cosine blending (`day_night.py`)
- [x] Sun arc -- 3x3 sun pixel block following a sine arc during daytime (`rendering.py`)
- [x] Moon arc -- 3x3 moon pixel block following a sine arc during nighttime with phase mask (`rendering.py`, `day_night.py`, `constants.py`)
- [x] Moon phases -- 8-phase lunar cycle (new/crescent/quarter/gibbous/full) over 8 day/night periods; phase-dependent 3x3 mask with lit/dark pixels (`day_night.py`, `rendering.py`, `constants.py`)
- [x] Star rendering with twinkle -- brightness fades with ambient; random per-frame jitter (`rendering.py`)
- [x] Seasonal color offset -- dawn/dusk tint grass and leaves with warm/cool shifts (`day_night.py`)
- [x] Ambient-scaled block colors -- all rendered blocks darkened by ambient factor (`rendering.py`)

### 3. Weather System

- [x] Four weather states -- clear / cloudy / rain / storm with configurable durations (`weather.py`, `constants.py`)
- [x] State machine transitions -- clear->cloudy, cloudy->clear|rain, rain->cloudy|storm, storm->rain (`weather.py`)
- [x] Smooth storm factor -- ambient darkening interpolates toward target per weather state (`weather.py`)
- [x] Weather transition frames -- 60-frame blending window between states (`weather.py`)
- [x] Rain drops with splash -- drops fall with gravity + wind drift; splash animation on landing (`weather.py`)
- [x] Variable rain intensity -- storm produces 25-40 drops vs rain's 15-25 (`constants.py`)
- [x] Wind-driven tree sway -- leaf canopies offset by weather-dependent wind (`weather.py`, `rendering.py`)
- [x] Lightning flash -- full-screen brightness boost for 3 frames during storms (`weather.py`, `rendering.py`)
- [x] Lightning bolt rendering -- jagged vertical bolt drawn for 2 frames (`rendering.py`)
- [x] Lightning sets trees on fire -- 20% chance to ignite a nearby tree on strike (`weather.py`)
- [x] Lightning sets grass on fire -- 5% chance to ignite grass at strike column (`weather.py`)
- [x] Grass fire system -- timed burn effect rendered at ground level (`weather.py`, `rendering.py`)
- [x] Dynamic water levels -- rain/storm slowly raises water; clear weather recedes it (`weather.py`)
- [x] Cloud count per weather -- min/max cloud targets change with weather state (`constants.py`)
- [x] Sky darkening in storms -- sky gradient blended toward grey proportional to storm factor (`rendering.py`)
- [x] Storm cloud dimensions -- larger clouds (12-20 wide, 3-5 tall) during storms vs normal (6-12 wide, 2-3 tall) (`constants.py`, `world_updates.py`)
- [x] Storm cloud opacity -- 85% opacity for storm clouds vs 70% for normal clouds (`constants.py`, `entities.py`, `rendering.py`)
- [x] Increased storm cloud count -- 8-12 clouds during storms (up from 6-8) (`constants.py`)
- [x] Per-cloud alpha blending -- each cloud carries its own opacity value for rendering (`entities.py`, `rendering.py`)

### 4. Trees & Vegetation

- [x] Two canopy styles -- round (circular mask) and conical (diamond/triangle) (`rendering.py`)
- [x] Growth animation -- trees grow from sapling (0.0) to mature (1.0) at +0.003/tick (`world_updates.py`)
- [x] Dying cycle -- mature trees eventually enter dying state with progressive leaf color change (`world_updates.py`)
- [x] Dying leaf palette -- 4-stage color shift: green -> yellow-green -> brown-green -> brown (`constants.py`)
- [x] Tree fire -- burning trees render with campfire flame colors on trunk and canopy (`rendering.py`)
- [x] Fire timer -- burning trees die after 30 ticks (`weather.py`, `world_updates.py`)
- [x] Dead tree respawn -- dead trees replaced at new random positions after cooldown (`world_updates.py`)
- [x] Max tree cap -- respawning only triggers when alive count < 24 (`world_updates.py`)
- [x] Tree planting by villagers -- villagers plant saplings in sparse areas, costs 1 lumber (`villager_ai.py`)
- [x] Flowers -- up to 12 flowers spawn on grass; 4 color variants; trampled by villagers (`entities.py`, `world_updates.py`)
- [x] Flower rendering -- single-pixel ambient-lit color at ground level (`rendering.py`)
- [x] Rain-accelerated growth -- trees grow 2x faster in rain, 3x in storms; flowers spawn more frequently (`world_updates.py`, `constants.py`)
- [x] Tree-building spacing -- trees cannot grow/spawn within 2 pixels of any structure; saplings near new buildings are removed (`terrain.py`, `world_updates.py`, `villager_ai.py`)

### 5. Water System

- [x] Gravity-driven water flow -- water falls into air below, spreads laterally (`terrain.py`)
- [x] Surface vs deep water colors -- top water row uses brighter surface color (`rendering.py`)
- [x] Water shimmer -- sinusoidal blue channel offset animated per tick (`rendering.py`)
- [x] Moonlight sparkle -- random bright flecks on water at night (ambient < 0.3) (`rendering.py`)
- [x] Rain-driven water rise -- slow probabilistic rise during rain, faster during storms (`weather.py`)
- [x] Water recession -- slow evaporation when weather is clear (`weather.py`)
- [x] Valley column detection -- utility to find all columns near water for avoidance logic (`terrain.py`)

### 6. Villager AI & Civilization

- [x] Finite state machine -- states: idle, walking, chopping, planting, building, upgrading, refueling, trading, collecting, resting, flattening, mining, entering, farming_plant, farming_harvest, eating (`villager_ai.py`)
- [x] Night behavior -- villagers return home to rest; homeless seek campfires (`villager_ai.py`)
- [x] Bad weather shelter -- villagers go home during rain/storm (`villager_ai.py`)
- [x] Campfire building -- costs 2 lumber; finds valid site with min spacing (`villager_ai.py`)
- [x] House building (small) -- costs 4 lumber; template-based 3x4 pixel art; foundation leveling (`villager_ai.py`)
- [x] House upgrading (level 1->2->3) -- costs 6 lumber + 2 stone; expands dimensions/template (`villager_ai.py`)
- [x] Stone house variant -- houses built with stone >= 2 use stone wall color (`villager_ai.py`)
- [x] Bridge building -- detects water gaps, costs 2-3 lumber depending on width, max 3 bridges (`villager_ai.py`)
- [x] Bridge-aware pathfinding -- villagers walk across bridges over water (`villager_ai.py`)
- [x] Mine construction -- costs 2 lumber; digs up to 8 blocks deep; yields stone every 2 depths (`villager_ai.py`)
- [x] Watchtower building -- requires 5+ population, costs 4 lumber + 2 stone (`villager_ai.py`)
- [x] Granary building -- requires 4+ population, costs 5 lumber; stores/distributes lumber (`villager_ai.py`)
- [x] Granary economy -- villagers deposit excess lumber (>6), withdraw when empty (`villager_ai.py`)
- [x] Tree chopping -- villagers harvest mature trees for 2-3 lumber items (`villager_ai.py`)
- [x] Lumber collection -- villagers pick up dropped lumber items (`villager_ai.py`)
- [x] Campfire refueling -- villagers feed lumber to low-fuel campfires (`villager_ai.py`)
- [x] Terrain flattening -- villagers smooth steep terrain to enable building (`villager_ai.py`)
- [x] Trading -- adjacent villagers exchange lumber when one has excess and other has none (`villager_ai.py`)
- [x] Speech bubbles -- colored 1-pixel indicators above head for active tasks (`villager_ai.py`, `rendering.py`)
- [x] Villager spawning -- new villager every 2700 ticks, up to max 10 (`villager_ai.py`)
- [x] Reproduction -- home-owning villagers of breeding age produce offspring (`villager_ai.py`)
- [x] Aging and death -- villagers age continuously; die between tick 12000-18000 (`villager_ai.py`)
- [x] Cremation flash -- nearest campfire flashes for 10 frames when a villager dies (`villager_ai.py`)
- [x] House ownership transfer -- on death, house passes to nearest homeless villager (`structures.py`)
- [x] Respawn if extinct -- if all villagers die, 2 new ones spawn near center (`villager_ai.py`)
- [x] Foundation leveling -- terrain under buildings averaged and flattened before construction (`structures.py`)
- [x] Randomized appearance -- each villager gets random skin color and clothes color (`entities.py`)
- [x] Direction tracking -- villagers face left/right based on movement (`entities.py`)
- [x] Housing-based population cap -- population limit driven by house count (2 per house + 2 base), hard max 20 (`villager_ai.py`, `constants.py`)
- [x] Post-construction area leveling -- idle house owners periodically flatten terrain around their homes for farms and future buildings (`world_updates.py`)
- [x] Terrain climbing -- villagers can traverse height differences up to 3 blocks; 2-3 block steps incur a brief climbing pause (`villager_ai.py`, `entities.py`, `constants.py`)
- [x] Fire fighting -- villagers detect and extinguish burning trees and grass fires within 20px radius; high priority interrupts idle/walking (`villager_ai.py`, `entities.py`, `constants.py`)
- [x] Farm construction -- homeowners with lumber build 4-slot crop farms on flat terrain near houses; costs 2 lumber (`villager_ai.py`, `entities.py`, `constants.py`)
- [x] Crop planting -- villagers plant seeds in empty farm slots; takes 20 ticks (`villager_ai.py`)
- [x] Crop harvesting -- villagers harvest mature crops for food; takes 20 ticks; yields 1 food per crop (`villager_ai.py`)
- [x] Farm site selection -- finds FARM_WIDTH contiguous flat grass columns near home, avoiding water/structures/trees (`villager_ai.py`)
- [x] Food resource -- villagers accumulate food from harvested crops (`entities.py`)

### 7. Structures & Buildings

- [x] Campfire -- 1x1 animated flame; burns fuel over time; can be refueled (`entities.py`, `rendering.py`)
- [x] Low fuel campfire variant -- dimmer flame palette when fuel < 900 (`rendering.py`, `constants.py`)
- [x] House level 1 (small) -- 3x4 template: roof, walls, window, door (`constants.py`)
- [x] House level 2 (medium) -- 4x6 template: adds chimney, second window (`constants.py`)
- [x] House level 3 (large) -- 5x6 template: larger footprint, centered door (`constants.py`)
- [x] 3 color palettes per house level -- wall, roof, door, window_day/night, chimney colors (`constants.py`)
- [x] Construction animation -- houses/towers render bottom-up as build_progress increases (`rendering.py`)
- [x] Window day/night swap -- windows change color based on time of day (`rendering.py`)
- [x] Mine -- vertical shaft rendered with darkening depth gradient (`rendering.py`)
- [x] Bridge -- horizontal plank with railings every 4 pixels (`rendering.py`)
- [x] Watchtower -- 7-tall structure: stone base, pole, platform, torch top (`rendering.py`)
- [x] Watchtower night torch -- flickering flame color at top during nighttime (`rendering.py`)
- [x] Granary -- 3x4 template: roof, walls, door; stores lumber communally (`rendering.py`, `constants.py`)
- [x] Campfire fuel depletion -- fuel decrements every tick; campfire removed at 0 (`structures.py`)

### 8. Lighting System

- [x] Campfire glow -- radial warm light (radius 7) scales with night factor; boosts R/G channels (`lighting.py`)
- [x] House lantern glow -- door-mounted flickering light (radius 3) at deep night (`lighting.py`)
- [x] Watchtower beacon -- radial light (radius 5) from tower top at night (`lighting.py`)
- [x] Torch post glow -- small radial light (radius 2) from path-side torches at night (`lighting.py`)
- [x] Pre-computed light masks -- distance-based intensity falloff baked into lookup tables (`constants.py`)
- [x] Night factor gating -- lights only activate below ambient thresholds (0.6 / 0.3) (`lighting.py`)
- [x] Warm color bias -- light boosts red channel most, green partially, blue least (`lighting.py`)
- [x] Max artificial light level -- all light passes capped at MAX_LIGHT_LEVEL (220) to prevent oversaturation from overlapping sources (`constants.py`, `lighting.py`)

### 9. Ambient Life

- [x] Birds -- multi-pixel sprite with 2 wing animation frames; fly across screen (`entities.py`, `rendering.py`)
- [x] Bird spawning -- spawn at screen edges during daytime; suppressed in storms (`world_updates.py`)
- [x] Bird sine-wave flight -- vertical bob via sin(tick) for natural movement (`entities.py`)
- [x] Bird perching -- birds land on mature tree canopies for 60-180 ticks; folded-wing sprite while perched (`entities.py`, `world_updates.py`, `rendering.py`, `constants.py`)
- [x] Clouds -- procedural shape with hollow corners; variable width/height (`entities.py`)
- [x] Cloud movement -- speed multiplied by weather state (1x / 1.5x / 2x) (`world_updates.py`)
- [x] Cloud alpha blending -- 70/30 mix with background sky for translucency (`rendering.py`)
- [x] Fireflies -- spawn near trees at dusk/night; drift randomly; pulsing glow (`world_updates.py`, `rendering.py`)
- [x] Firefly lifecycle -- 200-600 tick lifetime; max 10 on screen (`entities.py`, `world_updates.py`)
- [x] Smoke particles -- rise from campfires and level 2+ house chimneys; fade with age (`world_updates.py`, `rendering.py`)
- [x] Fish jumps -- occasional arc animation above water surface during daytime (`world_updates.py`, `rendering.py`)
- [x] Torch posts -- auto-placed on well-worn paths; max 5; check every 300 ticks (`world_updates.py`)
- [x] Deer -- ground-based 3x2 pixel animal; idle/walk/flee behavior; max 3 on map (`entities.py`, `world_updates.py`, `rendering.py`)
- [x] Rabbits -- ground-based 2x1 pixel animal; faster than deer; max 4 on map (`entities.py`, `world_updates.py`, `rendering.py`)
- [x] Animal fleeing -- animals flee from nearby villagers (8px radius) at double speed (`world_updates.py`)
- [x] Animal spawning -- periodic spawning on grass away from villagers; season-modulated (`world_updates.py`, `constants.py`)
- [x] Animal water avoidance -- animals reverse direction at water columns (`world_updates.py`)
- [x] Shooting stars -- rare diagonal streaks across night sky; bright head with fading tail; max 1 at a time (`entities.py`, `world_updates.py`, `rendering.py`, `constants.py`)

### 10. Camera & Viewport

- [x] Follow-target selection -- camera tracks the highest-level / richest villager (`simulation.py`)
- [x] Re-evaluation interval -- follow target reconsidered every 300 ticks (`simulation.py`)
- [x] Smooth scrolling -- camera moves 1 pixel every 3 ticks toward target (`simulation.py`)
- [x] Edge clamping -- camera clamped to [0, WORLD_WIDTH - DISPLAY_WIDTH] (`simulation.py`)
- [x] World-to-screen coordinate transform -- all renderers subtract camera_x from world positions (`rendering.py`)

### 11. Rendering Pipeline

Full render order as executed in [`simulation.py`](../src/display/living_world/simulation.py:168) each frame:

| Order | Layer                | Function                    | Module         |
|------:|----------------------|-----------------------------|----------------|
|     1 | Sky gradient         | `_render_sky`               | rendering.py   |
|     2 | Sun / Moon           | `_render_sun_moon`          | rendering.py   |
|     3 | Stars                | `_render_stars`             | rendering.py   |
|     4 | Clouds               | `_render_clouds`            | rendering.py   |
|     5 | Terrain blocks       | `_render_terrain`           | rendering.py   |
|     6 | Water                | `_render_water`             | rendering.py   |
|     7 | Flowers              | `_render_flowers`           | rendering.py   |
|     8 | Bridges              | `_render_bridges`           | rendering.py   |
|     9 | Structures           | `_render_structures`        | rendering.py   |
|    10 | Trees                | `_render_trees`             | rendering.py   |
|    11 | Lumber items         | `_render_lumber_items`      | rendering.py   |
|  11.5 | Farms                | `_render_farms`             | rendering.py   |
|    12 | Villagers            | `_render_villagers`         | rendering.py   |
|    13 | Birds                | `_render_birds`             | rendering.py   |
|    14 | Fish jumps           | `_render_fish_jumps`        | rendering.py   |
|    15 | Smoke                | `_render_smoke`             | rendering.py   |
|    16 | Fireflies            | `_render_fireflies`         | rendering.py   |
|    17 | Rain                 | `_render_rain`              | rendering.py   |
|    18 | Grass fires          | `_render_grass_fires`       | rendering.py   |
|    19 | Torch posts          | `_render_torch_posts`       | rendering.py   |
|    20 | Lightning            | `_render_lightning`         | rendering.py   |
|    21 | Campfire light pass  | `_apply_campfire_light`     | lighting.py    |
|    22 | Lantern light pass   | `_apply_lantern_light`      | lighting.py    |
|    23 | Watchtower light pass| `_apply_watchtower_light`   | lighting.py    |
|    24 | Torch post light pass| `_apply_torch_post_light`   | lighting.py    |

### 12. Tick Schedule

Update frequencies as coded in the frame loop ([`simulation.py`](../src/display/living_world/simulation.py:128)):

| Frequency       | Systems                                                       |
|-----------------|---------------------------------------------------------------|
| Every tick      | Weather state, cloud movement, bird movement, fish jump anim, lumber aging, camera update, full render |
| Every 2 ticks   | Firefly update                                                |
| Every 3 ticks   | Villager AI update, smoke emit + update                       |
| Every 4 ticks   | Water simulation, bird wing animation                         |
| Every 10 ticks  | Tree growth / dying / respawn                                 |
| Every 10 ticks  | Crop growth on all farms                                      |
| Every 90 ticks  | Bird spawning, cloud spawning, reproduction check             |
| Every 200 ticks | Fish jump spawning                                            |
| Every 300 ticks | Camera follow-target re-evaluation, torch post placement      |
| Every 500 ticks | Flower growth                                                 |
| Every 500 ticks | House area flattening check                                   |
| Every 2700 ticks| Villager immigration spawn                                    |

Frame rate target: **18 FPS** (`FRAME_INTERVAL = 1.0 / 18`)

### 13. Season System

- [x] Four seasons -- spring, summer, autumn, winter cycling over 4 day/night periods (`day_night.py`, `constants.py`)
- [x] Season computation -- deterministic season from elapsed time; each season = 1 day cycle (900s) (`day_night.py`)
- [x] Smooth season transitions -- last 10% of each season blends colors toward next season (`day_night.py`)
- [x] Seasonal grass colors -- bright green (spring), normal (summer), yellow-brown (autumn), frost grey (winter) (`constants.py`, `rendering.py`)
- [x] Seasonal leaf colors -- light green (spring), normal (summer), orange-brown (autumn), dark brown (winter) (`constants.py`, `rendering.py`)
- [x] Seasonal tree growth -- 1.5x spring, 1.0x summer, 0.5x autumn, 0.0x winter (`constants.py`, `world_updates.py`)
- [x] Seasonal flower spawning -- 0.8 spring, 0.5 summer, 0.2 autumn, 0.0 winter (`constants.py`, `world_updates.py`)
- [x] Winter flower death -- existing flowers gradually die during winter (`world_updates.py`)
- [x] Season weather bias -- per-season rain weight modifiers for future use (`constants.py`)


### 14. Farming

- [x] Farm entity -- data class with crop slots, growth stages, owner reference (`entities.py`)
- [x] Crop growth stages -- empty -> seeded -> sprouting -> growing -> mature; float 0.0-1.0 per slot (`entities.py`)
- [x] Crop growth system -- periodic growth ticks advance all planted crops toward maturity (`world_updates.py`)
- [x] Rain-accelerated crop growth -- 1.5x rain, 2.0x storm multipliers (`world_updates.py`, `constants.py`)
- [x] Seasonal crop growth -- 1.5x spring, 1.0x summer, 0.5x autumn, 0.0x winter (`world_updates.py`, `constants.py`)
- [x] Farm rendering -- tilled soil row at ground level; crop pixel above with stage-dependent color (`rendering.py`)
- [x] Farm building AI -- homeowners with lumber >= 2 and pop >= 3 build farms; max 1 per house (`villager_ai.py`)
- [x] Crop planting AI -- villagers plant all empty slots when visiting their farm (`villager_ai.py`)
- [x] Crop harvesting AI -- villagers harvest all mature crops, gaining food resource (`villager_ai.py`)
- [x] Farming speech bubble -- golden-brown indicator above head during farm tasks (`constants.py`, `villager_ai.py`)

### 15. Hunger System

- [x] Hunger field -- villagers accumulate hunger 0.0 (full) to 100.0 (starving) over time (`entities.py`, `constants.py`)
- [x] Hunger increment -- hunger increases by HUNGER_RATE (0.015) each AI tick (`villager_ai.py`)
- [x] Hunger capped at max -- hunger cannot exceed HUNGER_MAX (100.0) (`villager_ai.py`)
- [x] Eating state -- new "eating" FSM state: villager consumes 1 food over EATING_FRAMES (25) ticks (`villager_ai.py`)
- [x] Hunger-triggered eating -- villagers with food auto-eat when hunger >= HUNGER_EAT_THRESHOLD (30.0); interrupts idle/walking (`villager_ai.py`)
- [x] Food satiation -- eating 1 food reduces hunger by FOOD_SATIATION (40.0), clamped at 0 (`villager_ai.py`)
- [x] No starvation -- hunger is purely motivational; villagers never die from hunger (`villager_ai.py`)
- [x] Hunger food priority -- critically hungry (>= 80.0) villagers without food rush to harvest mature crops or plant empty farm slots (`villager_ai.py`)
- [x] Hunger speed penalty -- critically hungry villagers move at half speed (skip odd ticks) (`villager_ai.py`)
- [x] Eating speech bubble -- green indicator above head during eating (`constants.py`, `villager_ai.py`)
- [x] Eating body flash -- green-tinted body color flashes during eating animation (`rendering.py`)

### 16. Goal-Based Decision Tree

- [x] Goal evaluation engine -- `_evaluate_goals()` scores all applicable goals dynamically based on villager state, resources, and world context (`villager_ai.py`)
- [x] 17 goal types -- build_campfire, get_food, build_house, farm_harvest, refuel_campfire, gather_lumber, build_farm, farm_plant, build_granary, upgrade_house, gather_stone, build_watchtower, build_mine, build_bridge, plant_tree, flatten_terrain, explore (`constants.py`)
- [x] Priority scoring -- each goal has a base priority; dynamic bonuses adjust scores based on need (e.g. lumber shortfall boosts gather_lumber, hunger boosts farm_harvest) (`villager_ai.py`, `constants.py`)
- [x] Resource prerequisite system -- `GOAL_PREREQS` defines lumber/stone costs per goal; `_has_prereqs()` and `_missing_prereqs()` check fulfillment (`villager_ai.py`, `constants.py`)
- [x] Prerequisite chaining -- `_resolve_prereq_action()` redirects to sub-goals when resources are insufficient: build_house(needs 4 lumber) -> gather_lumber, upgrade_house(needs stone) -> gather_stone (`villager_ai.py`)
- [x] Largest-shortfall resolution -- when multiple resources are missing, the sub-goal targets the one with the largest deficit first (`villager_ai.py`)
- [x] Goal persistence -- `current_goal` field on Villager persists intent across ticks; prevents random goal flipping (`entities.py`, `villager_ai.py`)
- [x] Goal re-evaluation interval -- goals are re-scored every `GOAL_EVAL_INTERVAL` (60) ticks or when current goal is None (`villager_ai.py`, `constants.py`)
- [x] Goal reset on completion -- goals auto-clear when their action is successfully initiated, allowing fresh evaluation next idle tick (`villager_ai.py`)
- [x] Gather lumber intelligence -- prefers free dropped lumber items over tree chopping; explore chance still provides behavior variety (`villager_ai.py`)
- [x] Fallback to explore -- if no goal can be executed (missing sites, no trees, etc.), villager walks randomly (`villager_ai.py`)

---

## Configuration

Key constants defined in [`constants.py`](../src/display/living_world/constants.py:1):

| Constant                        | Value         | Purpose                                  |
|---------------------------------|---------------|------------------------------------------|
| `DISPLAY_WIDTH` / `HEIGHT`      | 64 / 64       | LED matrix dimensions                    |
| `WORLD_WIDTH`                   | 192           | Scrollable world width (3x display)      |
| `FRAME_INTERVAL`                | 1/18 s        | Target 18 FPS                            |
| `DAY_CYCLE_SECONDS`             | 900           | Full day/night cycle length              |
| `BASE_GROUND`                   | 42            | Average terrain height                   |
| `TERRAIN_MIN` / `MAX`           | 30 / 52       | Height profile clamp range               |
| `MAX_VILLAGERS`                 | 20            | Population cap                           |
| `VILLAGER_SPAWN_INTERVAL`       | 2700          | Ticks between immigration spawns         |
| `VILLAGER_MIN_AGE` / `MAX_AGE`  | 12000 / 18000 | Lifespan range in ticks                  |
| `CAMPFIRE_INITIAL_FUEL`         | 5400          | Starting fuel for new campfires          |
| `CAMPFIRE_REFUEL_AMOUNT`        | 2700          | Fuel added per lumber                    |
| `CAMPFIRE_LOW_FUEL_THRESHOLD`   | 900           | Triggers dim flame + refuel behavior     |
| `CAMPFIRE_MIN_SPACING`          | 10            | Minimum columns between campfires        |
| `MAX_BRIDGES`                   | 3             | Bridge construction cap                  |
| `BRIDGE_MAX_GAP`                | 12            | Maximum bridgeable water width           |
| `MAX_MINES`                     | 2             | Mine construction cap                    |
| `MINE_MAX_DEPTH`                | 8             | Maximum mine shaft depth                 |
| `MINE_POPULATION_THRESHOLD`     | 3             | Min villagers before mines allowed       |
| `WATCHTOWER_POPULATION_THRESHOLD` | 5           | Min villagers before watchtower          |
| `GRANARY_POPULATION_THRESHOLD`  | 4             | Min villagers before granary             |
| `MAX_TORCH_POSTS`               | 5             | Torch post placement cap                 |
| `TORCH_POST_PATH_THRESHOLD`     | 30            | Path wear needed to trigger torch        |
| `REPRODUCTION_CHANCE`           | 1/1800        | Per-check reproduction probability       |
| `MAX_CHILDREN`                  | 3             | Children per villager lifetime           |
| `LIGHTNING_CHANCE`              | 1/90          | Per-tick strike probability in storms    |
| `TREE_FIRE_DURATION`            | 30            | Ticks a tree burns before dying          |
| `RAIN_GROWTH_MULTIPLIER`        | 2.0           | Tree growth rate multiplier during rain  |
| `STORM_GROWTH_MULTIPLIER`       | 3.0           | Tree growth rate multiplier during storms|
| `RAIN_FLOWER_SPAWN_BOOST`       | 0.75          | Flower spawn chance during rain          |
| `STORM_FLOWER_SPAWN_BOOST`      | 0.90          | Flower spawn chance during storms        |
| `CAMERA_FOLLOW_RE_EVAL`         | 300           | Ticks between follow-target changes      |
| `CAMERA_SMOOTH_SPEED`           | 3             | Camera moves 1px every N ticks           |
| `WEATHER_DURATION` (clear)      | 2000-5000     | Clear weather tick range                 |
| `WEATHER_DURATION` (rain)       | 1000-3000     | Rain weather tick range                  |
| `WEATHER_DURATION` (storm)      | 500-1500      | Storm weather tick range                 |
| `CLOUD_WIDTH_RANGE`             | (6, 12)       | Normal cloud width range                 |
| `CLOUD_HEIGHT_RANGE`            | (2, 3)        | Normal cloud height range                |
| `STORM_CLOUD_WIDTH_RANGE`       | (12, 20)      | Storm cloud width range                  |
| `STORM_CLOUD_HEIGHT_RANGE`      | (3, 5)        | Storm cloud height range                 |
| `CLOUD_ALPHA`                   | 0.7           | Normal cloud opacity                     |
| `STORM_CLOUD_ALPHA`             | 0.85          | Storm cloud opacity (more opaque)        |
| `TREE_BUILDING_MIN_SPACING`     | 2             | Min pixel distance between trees and structures |
| `VILLAGERS_PER_HOUSE`           | 2             | Population supported per completed house |
| `BASE_VILLAGERS`                | 2             | Starting population cap before houses   |
| `HOUSE_FLATTEN_RADIUS`          | 5             | Pixels on each side of house to flatten  |
| `HOUSE_FLATTEN_INTERVAL`        | 500           | Ticks between flattening checks          |
| `HOUSE_FLATTEN_RATE`            | 1             | Blocks adjusted per tick per column       |
| `VILLAGER_MAX_CLIMB`            | 3             | Max height difference villagers can traverse |
| `VILLAGER_CLIMB_SPEED`          | 2             | Extra ticks of pause for steep climbs    |
| `FIREFIGHT_DETECT_RADIUS`       | 20            | Detection range for nearby fires         |
| `FIREFIGHT_EXTINGUISH_TICKS`    | 10            | Ticks to extinguish a fire once adjacent |
| `SEASON_CYCLE_DAYS`             | 4             | Full season cycle = 4 day/night periods  |
| `SEASON_TREE_GROWTH` (spring)   | 1.5           | Tree growth multiplier in spring         |
| `SEASON_TREE_GROWTH` (winter)   | 0.0           | No tree growth in winter                 |
| `SEASON_FLOWER_CHANCE` (spring) | 0.8           | Flower spawn chance in spring            |
| `SEASON_FLOWER_CHANCE` (winter) | 0.0           | No flowers spawn in winter               |
| `MAX_DEER`                      | 3             | Maximum deer on the map                  |
| `MAX_RABBITS`                   | 4             | Maximum rabbits on the map               |
| `ANIMAL_SPAWN_INTERVAL`         | 400           | Ticks between animal spawn checks        |
| `ANIMAL_FLEE_RADIUS`            | 8             | Pixels -- animals flee from villagers    |
| `ANIMAL_FLEE_DURATION`          | 30            | Ticks animals flee before calming        |
| `FARM_WIDTH`                    | 4             | Crop slots per farm plot                 |
| `FARM_COST_LUMBER`              | 2             | Lumber to build a farm                   |
| `FARM_BUILD_FRAMES`             | 60            | Ticks to till/prepare the farm           |
| `FARM_POPULATION_THRESHOLD`     | 3             | Min villagers before farming starts      |
| `MAX_FARMS_PER_HOUSE`           | 1             | Farms per house owner                    |
| `CROP_GROWTH_RATE`              | 0.002         | Base growth per tick                     |
| `CROP_HARVEST_YIELD`            | 1             | Food per harvested mature crop           |
| `FARM_GROWTH_CHECK_INTERVAL`    | 10            | Ticks between crop growth updates        |
| `RAIN_CROP_GROWTH_MULTIPLIER`   | 1.5           | Crop growth rate multiplier during rain  |
| `STORM_CROP_GROWTH_MULTIPLIER`  | 2.0           | Crop growth rate multiplier during storms|
| `HUNGER_MAX`                    | 100.0         | Maximum hunger level (starving)          |
| `HUNGER_RATE`                   | 0.015         | Hunger increase per AI tick              |
| `HUNGER_THRESHOLD`              | 50.0          | Hunger level for food prioritization     |
| `HUNGER_CRITICAL`               | 80.0          | Hunger level for desperate food-seeking  |
| `HUNGER_EAT_THRESHOLD`          | 30.0          | Min hunger before villager bothers eating|
| `FOOD_SATIATION`                | 40.0          | Hunger reduced per food item eaten       |
| `EATING_FRAMES`                 | 25            | Ticks spent in eating state              |
| `HUNGER_SPEED_PENALTY`          | 0.5           | Speed multiplier when critically hungry  |
| `GOAL_EVAL_INTERVAL`            | 60            | Ticks between full goal re-evaluation    |
| `GOAL_PRIORITY` (build_campfire)| 85            | Highest economic goal: survival          |
| `GOAL_PRIORITY` (build_house)   | 70            | Major progression milestone              |
| `GOAL_PRIORITY` (gather_lumber) | 50 + dynamic  | Base + 5 per missing lumber below thresh |
| `GOAL_PRIORITY` (explore)       | 5             | Lowest priority: random walking          |

---

## Actionable Tasks

> Organized by priority tier. Each task has a clear scope and affected modules.

### Tier 1 -- Bug Fixes & Stability

- [x] **Infinite run support** -- `simulation.py` `run()` accepts `duration=0` for indefinite operation; loop checks `should_stop()` first, then duration (`simulation.py`)
- [x] **Save / restore world state** -- serialize all entities to JSON on exit; reload on next `run()` call; cross-references preserved via index mapping (`simulation.py`, `persistence.py`)
- [x] **Farm orphan cleanup** -- when a villager dies, farm ownership transfers to nearest farmless villager or goes unowned (`villager_ai.py`)
- [x] **Duplicate `_too_close_to_structure` function** -- consolidated into `terrain.py`; `world_updates.py` and `villager_ai.py` now import from `terrain` (`terrain.py`, `world_updates.py`, `villager_ai.py`)
- [x] **Dead villager goal cleanup** -- when a villager dies mid-build, `building_target.under_construction` is set False and `build_progress` to 1.0 (`villager_ai.py`)

### Tier 2 -- System Improvements

- [x] **Rendering dedup in `_render_farms`** -- sprouting/growing/mature branches collapsed into single conditional; seeded/empty skipped uniformly (`rendering.py`)
- [x] **Water level update performance** -- `_get_water_surface_cols()` pre-scans for water surface once per call, replacing inner O(n*m) scans (`weather.py`)
- [x] **`_get_valley_cols` caching** -- module-level cache with generation-based invalidation; callers can pass `_cache_gen` for tick-based reuse (`terrain.py`)
- [x] **Goal system: reproduction as a goal** -- `have_baby` goal with prereqs (has_home, breeding_age, pop < cap); villager walks home to trigger reproduction check (`villager_ai.py`, `constants.py`)
- [x] **Goal system: food sharing** -- `share_food` goal; villagers with food > FOOD_SHARE_THRESHOLD give 1 food to nearest hungry neighbor (`villager_ai.py`, `constants.py`)
- [x] **Campfire cremation on death at home** -- cremation flash now considers home's lantern if closer than any campfire (`villager_ai.py`)

### Tier 3 -- New Features

- [x] **Eclipses** -- solar eclipse every 12 day cycles at mid-day; lunar eclipse every 16 cycles at mid-night; `_check_solar_eclipse` / `_check_lunar_eclipse` functions with intensity falloff; solar dims ambient to ECLIPSE_AMBIENT_MIN (`day_night.py`, `simulation.py`, `constants.py`)
- [x] **Castle building** -- late-game mega-structure requiring 10 lumber + 5 stone; 7x8 pixel art template with towers, battlements, windows, gate, and door; requires 8+ population; max 1 per world; construction animation bottom-up; foundation leveling; unique day/night window colors (`constants.py`, `villager_ai.py`, `rendering.py`, `structures.py`)
- [x] **Boat travel** -- villagers craft a boat (2 lumber) to cross water bodies wider than BRIDGE_MAX_GAP; Boat entity rendered as 3px on water surface; travels at 0.5 speed; auto-crafted when villager encounters water without a bridge; boat deactivates on land (`entities.py`, `villager_ai.py`, `rendering.py`, `constants.py`, `simulation.py`)
- [x] **Trade caravans** -- NPC Caravan groups arrive from off-screen every ~5000 ticks; walk to world center, trade stone/food/gold for lumber with nearby villagers during CARAVAN_TRADE_DURATION (120) ticks; 3 trade offer types; disappear after trading; event log integration (`entities.py`, `world_updates.py`, `rendering.py`, `constants.py`, `simulation.py`)
- [x] **Villager names / traits** -- each villager gets a procedural name from 24 nature-themed names; personality trait (builder/farmer/lumberjack/explorer) biases goal scoring by +20% for preferred activities (`entities.py`, `villager_ai.py`, `constants.py`)
- [x] **Hunting** -- hungry villagers (hunger > 60) with no farm chase nearby deer/rabbits; successful hunt yields 2 food; adds "hunting" state, bubble, and goal evaluation (`villager_ai.py`, `entities.py`, `constants.py`)
- [x] **Snow weather** -- winter season spawns snow particles (white, slower than rain, no splash); SnowFlake entity with drift; `_update_snow` and `_render_snow` functions (`world_updates.py`, `rendering.py`, `entities.py`, `constants.py`, `simulation.py`)
- [x] **Community storage building** -- villagers build storage (4 lumber + 1 stone) that stores up to 30 lumber, 15 stone, 20 food communally; villagers deposit excess items (above configurable thresholds) and withdraw when at 0; requires 3+ population; max 2 per world; `deposit_storage` and `withdraw_storage` goals with priority-based retrieval before gathering (`constants.py`, `structures.py`, `villager_ai.py`, `entities.py`)
- [x] **Gold resource + Bank building** -- mining has 25% chance to yield gold per 2 depths; gold field on Villager; Bank building (5 lumber + 3 stone, 4x4, requires 6+ pop, max 1) stores community gold; villagers auto-deposit gold to bank via storage goal; Caravan trades accept gold as currency (`constants.py`, `entities.py`, `villager_ai.py`, `structures.py`)
- [x] **Well building** -- villagers build wells (1 lumber + 2 stone) that prevent all lightning fires within WELL_FIRE_PREVENTION_RADIUS (15px); max 3 wells with WELL_MIN_SPACING (25px) enforced; requires 4+ population; `_is_protected_by_well()` / `_find_well_site()` helpers; 1x2 pixel rendering with stone/water/roof (`constants.py`, `structures.py`, `villager_ai.py`, `rendering.py`, `weather.py`)
- [x] **Event logging system** -- ring-buffer log of last 1000 simulation events (births, deaths, building, trading, weather, combat) with category filtering; `log_event()` / `get_events()` / `get_all_events()` API for web UI and debugging (`event_log.py`, `villager_ai.py`, `weather.py`)
- [x] **Bow hunting** -- villagers auto-craft a bow (1 lumber) before hunting; bow-equipped villagers shoot animals from BOW_RANGE (10px) after BOW_SHOOT_FRAMES (15) aiming ticks instead of chasing; `has_bow` field on Villager; event log integration (`constants.py`, `entities.py`, `villager_ai.py`)
- [x] **Dense cloud roll-in** -- when weather transitions from clear/cloudy to rain/storm, clouds aggressively spawn from wind direction at faster speed (0.06-0.14 vs 0.02-0.08) to create a rolling wall effect; 70% wind-direction bias during steady-state rain (`world_updates.py`)
- [x] rain should be a strong 'build a house' motivator if homeless
- [x] **Pond spawning fix** -- `_guarantee_pond` now correctly digs downward (increasing y) to create a basin at the lowest terrain point instead of placing water on a hilltop where it would drain away (`terrain.py`)

### Tier 4 -- Web UI & Tooling

- [x] **Web UI world viewer** -- real-time minimap on `/living-world` page showing 192-wide terrain, structures, trees, animals, and villager dots on HTML5 canvas; auto-refreshes every 5 seconds via `/api/living-world/state`; camera viewport rectangle overlay (`src/web/app.py`, `src/web/templates/living_world.html`, `src/display/living_world/world_api.py`)
- [x] **Web UI villager inspector** -- click a villager dot on minimap or list to see name, trait, state, current_goal, hunger, lumber, stone, food, age, home/farm/bow status in detail panel (`src/web/templates/living_world.html`)
- [x] **Web UI world controls** -- buttons to trigger weather (clear/rain/storm), spawn villagers, set time of day (day/night), toggle seasons; sends commands via `/api/living-world/command`; event log viewer with category filter dropdown (`src/web/app.py`, `src/web/templates/living_world.html`)
- [x] **World reset command** -- `reset_world` action via `/api/living-world/command` sets `_reset_requested` flag on Weather; deletes save file to force fresh world generation on next run (`simulation.py`, `persistence.py`)

### Completed Ideas (archived)

- [x] Seasons -- cycle terrain palette and tree behavior over multiple day cycles
- [x] Max artificial light level -- all lighting passes capped at MAX_LIGHT_LEVEL (220)
- [x] Animal mobs -- deer, rabbits roaming the world
- [x] Farming -- villagers till soil and grow crops
- [x] Villager hunger -- food motivation system (no starvation)
- [x] Villagers should flatten area around house for farms/buildings
- [x] Villagers should be able to climb
- [x] Trees should not grow within 2 pixels of buildings; housing controls pop cap
- [x] Fire fighting role
- [x] Better cloud cover during storms
- [x] Birds land on trees
- [x] Shooting stars
- [x] Moon phases, bigger moon
- [x] Check for brain flaws in villager behavior -- FIXED via chop threshold, explore chance
- [x] Intelligent action decision trees -- goal-based system with prerequisite chaining
- [x] Infinite run support -- duration=0 for indefinite operation
- [x] Save/restore world state -- JSON persistence across restarts
- [x] Farm orphan cleanup -- farms transfer on owner death
- [x] Consolidated _too_close_to_structure -- single canonical function in terrain.py
- [x] Dead villager goal cleanup -- in-progress structures completed on builder death
- [x] Rendering dedup in _render_farms -- identical branches collapsed
- [x] Water level update performance -- water-column index pre-scan
- [x] _get_valley_cols caching -- generation-based cache
- [x] Reproduction as a goal -- "have_baby" in goal system
- [x] Food sharing -- villagers share excess food with hungry neighbors
- [x] Campfire cremation lantern fallback -- home lantern used if closer
- [x] Eclipses -- solar and lunar eclipse events with ambient effects
- [x] Villager names and traits -- procedural names + personality-biased goals
- [x] Hunting -- hungry villagers chase animals for food
- [x] Snow weather -- winter snow particles with drift and rendering
- [x] AI audit: redundant eat-state check -- removed dead `v.state != "eating"` clause
- [x] AI audit: chopping gives no immediate reward -- auto-collect 1 lumber after chop
- [x] AI audit: planting never deducted lumber -- added `v.lumber -= 1` on plant
- [x] AI audit: duplicate firefighting state -- collapsed identical if/else branches
- [x] AI audit: bad weather dead branch -- homeless villagers now use goal tree in rain
- [x] AI audit: explore blocks zero-lumber chop -- villagers at 0 lumber always chop
- [x] AI audit: have_baby goal clears prematurely -- goal persists while walking home
- [x] Rain motivates house building -- +12 rain / +20 storm score bonus for homeless villagers
- [x] Pond spawning fix -- _guarantee_pond digs basin downward instead of placing water on hilltop
- [x] Boat travel -- villagers auto-craft boats to cross water without bridges
- [x] Trade caravans -- NPC traders arrive periodically to exchange resources
- [x] Community storage -- shared building for depositing/withdrawing lumber, stone, food
- [x] Gold resource + Bank -- mining yields gold; bank building stores community gold
- [x] World reset command -- web UI can request fresh world generation