"""Save / restore world state to JSON for persistence across restarts."""

import json
import os
import logging

logger = logging.getLogger(__name__)

_SAVE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "living_world_save.json")


def _entity_to_dict(obj):
    """Shallow-serialize an entity to a plain dict, skipping callables and internal refs."""
    d = {}
    for k, v in vars(obj).items():
        if k.startswith("_"):
            continue
        if callable(v):
            continue
        # Skip object references -- we re-link by index after load
        if k in ("home", "owner", "perch_tree", "firefight_target",
                  "target_tree", "refuel_target", "upgrade_target",
                  "mine_target", "building_target", "on_bridge", "farm"):
            continue
        # Nested lists like Cloud.shape
        if isinstance(v, list) and v and isinstance(v[0], list):
            d[k] = v
        elif isinstance(v, list):
            d[k] = v
        elif isinstance(v, (int, float, str, bool, type(None))):
            d[k] = v
        elif isinstance(v, tuple):
            d[k] = list(v)
    return d


def save_world(*, villagers, structures, trees, farms, heights, world,
               weather, clouds, birds, animals, shooting_stars,
               fireflies, smoke_particles, fish_jumps, flowers,
               rain_drops, grass_fires, path_wear, torch_posts,
               lumber_items, stars, camera_x, sim_tick, start_time,
               follow_target_idx=None):
    """Serialize all world state to a JSON file."""
    try:
        # Build villager -> index map for cross-references
        v_idx = {id(v): i for i, v in enumerate(villagers)}
        s_idx = {id(s): i for i, s in enumerate(structures)}
        f_idx = {id(f): i for i, f in enumerate(farms)}

        data = {
            "version": 1,
            "sim_tick": sim_tick,
            "camera_x": camera_x,
            "heights": heights,
            "world": world,
            "path_wear": path_wear,
            "stars": stars,
            "torch_posts": torch_posts,
        }

        # Villagers with cross-refs as indices
        v_list = []
        for v in villagers:
            vd = _entity_to_dict(v)
            vd["_home_idx"] = s_idx.get(id(v.home), -1) if v.home else -1
            vd["_farm_idx"] = f_idx.get(id(v.farm), -1) if v.farm else -1
            v_list.append(vd)
        data["villagers"] = v_list

        # Structures with cross-refs
        s_list = []
        for s in structures:
            sd = _entity_to_dict(s)
            sd["_owner_idx"] = v_idx.get(id(s.owner), -1) if s.owner else -1
            s_list.append(sd)
        data["structures"] = s_list

        # Farms with cross-refs
        f_list = []
        for f in farms:
            fd = _entity_to_dict(f)
            fd["_owner_idx"] = v_idx.get(id(f.owner), -1) if f.owner else -1
            f_list.append(fd)
        data["farms"] = f_list

        # Simple entity lists
        data["trees"] = [_entity_to_dict(t) for t in trees]
        data["animals"] = [_entity_to_dict(a) for a in animals]
        data["flowers"] = [_entity_to_dict(f) for f in flowers]
        data["lumber_items"] = [_entity_to_dict(li) for li in lumber_items]

        # Weather
        data["weather"] = _entity_to_dict(weather)

        path = os.path.abspath(_SAVE_PATH)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fp:
            json.dump(data, fp, separators=(",", ":"))
        logger.info("World state saved to %s", path)
        return True
    except Exception as e:
        logger.warning("Failed to save world state: %s", e)
        return False


def load_world():
    """Load world state from JSON.  Returns the data dict or None if not available."""
    path = os.path.abspath(_SAVE_PATH)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as fp:
            data = json.load(fp)
        if data.get("version") != 1:
            logger.warning("Incompatible save version, ignoring")
            return None
        logger.info("World state loaded from %s", path)
        return data
    except Exception as e:
        logger.warning("Failed to load world state: %s", e)
        return None


def delete_save():
    """Remove the save file after a successful load."""
    path = os.path.abspath(_SAVE_PATH)
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def restore_entities(data):
    """Reconstruct entity objects from loaded save data.

    Returns a dict with all reconstructed entities ready to drop into the
    simulation loop, or None on failure.
    """
    from .entities import (
        Villager, Tree, Structure, Farm, LumberItem, Flower, Animal, Weather,
    )

    try:
        # --- Rebuild simple helpers ---
        def _apply(obj, d, skip=()):
            for k, v in d.items():
                if k.startswith("_") or k in skip:
                    continue
                if hasattr(obj, k):
                    current = getattr(obj, k)
                    if isinstance(current, tuple) and isinstance(v, list):
                        setattr(obj, k, tuple(v))
                    else:
                        setattr(obj, k, v)

        # --- Rebuild trees ---
        trees = []
        for td in data.get("trees", []):
            t = Tree(td["x"], td["base_y"], td["growth"],
                     td["max_height"], td["canopy_radius"], td["style"])
            _apply(t, td, skip=("x", "base_y", "growth", "max_height",
                                "canopy_radius", "style"))
            trees.append(t)

        # --- Rebuild structures ---
        structures = []
        for sd in data.get("structures", []):
            s = Structure(sd["type"], sd["x"], sd["y"], sd["width"], sd["height"])
            _apply(s, sd, skip=("type", "x", "y", "width", "height"))
            structures.append(s)

        # --- Rebuild farms ---
        farms = []
        for fd in data.get("farms", []):
            f = Farm(fd["x"], fd["y"], fd.get("width", 4))
            _apply(f, fd, skip=("x", "y", "width"))
            farms.append(f)

        # --- Rebuild villagers ---
        villagers = []
        for vd in data.get("villagers", []):
            v = Villager(vd["x"], vd["y"])
            _apply(v, vd, skip=("x", "y"))
            # Re-link cross-references
            home_idx = vd.get("_home_idx", -1)
            if home_idx >= 0 and home_idx < len(structures):
                v.home = structures[home_idx]
            farm_idx = vd.get("_farm_idx", -1)
            if farm_idx >= 0 and farm_idx < len(farms):
                v.farm = farms[farm_idx]
            villagers.append(v)

        # --- Re-link structure owners ---
        for i, sd in enumerate(data.get("structures", [])):
            owner_idx = sd.get("_owner_idx", -1)
            if owner_idx >= 0 and owner_idx < len(villagers):
                structures[i].owner = villagers[owner_idx]

        # --- Re-link farm owners ---
        for i, fd in enumerate(data.get("farms", [])):
            owner_idx = fd.get("_owner_idx", -1)
            if owner_idx >= 0 and owner_idx < len(villagers):
                farms[i].owner = villagers[owner_idx]

        # --- Rebuild animals ---
        animals = []
        for ad in data.get("animals", []):
            a = Animal(ad["x"], ad["y"], ad["animal_type"], ad["direction"])
            _apply(a, ad, skip=("x", "y", "animal_type", "direction"))
            animals.append(a)

        # --- Rebuild flowers ---
        flowers = []
        for fd in data.get("flowers", []):
            color = tuple(fd["color"]) if isinstance(fd.get("color"), list) else fd.get("color", (220, 50, 50))
            f = Flower(fd["x"], fd["y"], color)
            flowers.append(f)

        # --- Rebuild lumber items ---
        lumber_items = []
        for ld in data.get("lumber_items", []):
            li = LumberItem(ld["x"], ld["y"])
            li.age = ld.get("age", 0)
            lumber_items.append(li)

        # --- Rebuild weather ---
        weather = Weather()
        wd = data.get("weather", {})
        _apply(weather, wd)

        result = {
            "villagers": villagers,
            "structures": structures,
            "trees": trees,
            "farms": farms,
            "animals": animals,
            "flowers": flowers,
            "lumber_items": lumber_items,
            "weather": weather,
            "heights": data["heights"],
            "world": data["world"],
            "path_wear": data.get("path_wear", [0] * len(data["heights"])),
            "stars": [tuple(s) for s in data.get("stars", [])],
            "torch_posts": [tuple(tp) for tp in data.get("torch_posts", [])],
            "camera_x": data.get("camera_x", 64),
            "sim_tick": data.get("sim_tick", 0),
        }
        return result
    except Exception as e:
        logger.warning("Failed to restore entities: %s", e)
        return None
