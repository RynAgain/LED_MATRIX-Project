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
- [x] Moon arc -- 2x2 moon pixel block following a sine arc during nighttime (`rendering.py`)
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

- [x] Finite state machine -- states: idle, walking, chopping, planting, building, upgrading, refueling, trading, collecting, resting, flattening, mining, entering (`villager_ai.py`)
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

### 9. Ambient Life

- [x] Birds -- multi-pixel sprite with 2 wing animation frames; fly across screen (`entities.py`, `rendering.py`)
- [x] Bird spawning -- spawn at screen edges during daytime; suppressed in storms (`world_updates.py`)
- [x] Bird sine-wave flight -- vertical bob via sin(tick) for natural movement (`entities.py`)
- [x] Clouds -- procedural shape with hollow corners; variable width/height (`entities.py`)
- [x] Cloud movement -- speed multiplied by weather state (1x / 1.5x / 2x) (`world_updates.py`)
- [x] Cloud alpha blending -- 70/30 mix with background sky for translucency (`rendering.py`)
- [x] Fireflies -- spawn near trees at dusk/night; drift randomly; pulsing glow (`world_updates.py`, `rendering.py`)
- [x] Firefly lifecycle -- 200-600 tick lifetime; max 10 on screen (`entities.py`, `world_updates.py`)
- [x] Smoke particles -- rise from campfires and level 2+ house chimneys; fade with age (`world_updates.py`, `rendering.py`)
- [x] Fish jumps -- occasional arc animation above water surface during daytime (`world_updates.py`, `rendering.py`)
- [x] Torch posts -- auto-placed on well-worn paths; max 5; check every 300 ticks (`world_updates.py`)

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
| Every 90 ticks  | Bird spawning, cloud spawning, reproduction check             |
| Every 200 ticks | Fish jump spawning                                            |
| Every 300 ticks | Camera follow-target re-evaluation, torch post placement      |
| Every 500 ticks | Flower growth                                                 |
| Every 500 ticks | House area flattening check                                   |
| Every 2700 ticks| Villager immigration spawn                                    |

Frame rate target: **18 FPS** (`FRAME_INTERVAL = 1.0 / 18`)

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

---

## Future Ideas

<!-- Add planned or proposed features below -->

- [ ] Seasons -- cycle terrain palette and tree behavior over multiple day cycles
- [ ]max artificail light level
- [ ] Animal mobs -- deer, rabbits roaming the world
- [ ] Farming -- villagers till soil and grow crops
- [ ] Boat travel -- villagers use boats to cross large water bodies
- [ ] Villager names / traits -- personality affecting task priority
- [ ] Trade caravans -- external villager groups arriving from off-screen
- [ ] villager hunger (no starvation just motivation for food meat, farming)
- [x] villagers should flatten area around house to hosue level for farms other building
- [x] villagers should be able to climb

- [ ] Minimap overlay -- small overview of the full 192-wide world
- [ ] Save / restore world state -- persist simulation across restarts

- [x] should not grow within 2 pixels of a house or building.  Housing controls population cap with a max of 20 population.  we might need bigger houses

- [ ] system should run as long as we please
- [ ] system should save and restore between runs
- [ ] what is the end goal here a question to ask?
- [x] fire fighting role?
- [x] better cloud cover during storms
- [ ] birds land on trees
- [ ] shooting stars
- [ ] castle building
- [ ] eclipse 
- [ ] moon phases, bigger moon
- [ ] ideas to improve current exisitng systems
- [ ] check for brain flaws in villager behavior, priiorites