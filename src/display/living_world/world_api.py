"""API helpers for reading living world state from the web interface.

Provides snapshot data from live simulation state or the save file
for the web UI minimap, villager inspector, and event log viewer.
"""

import json
import os
import logging
import time
import threading

logger = logging.getLogger(__name__)

_SAVE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "living_world_save.json"
)

# --- Live state sharing ---
# The simulation writes a snapshot here periodically; the web UI reads it.
_LIVE_SNAPSHOT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "logs", "living_world_snapshot.json"
)
_SNAPSHOT_INTERVAL = 3.0  # seconds between live snapshots
_last_snapshot_time = 0.0


def write_live_snapshot(*, villagers, structures, trees, farms, animals,
                        heights, weather, camera_x, sim_tick):
    """Write a simplified live snapshot for the web UI. Called from the sim loop."""
    global _last_snapshot_time
    now = time.time()
    if now - _last_snapshot_time < _SNAPSHOT_INTERVAL:
        return
    _last_snapshot_time = now
    try:
        v_list = []
        for v in villagers:
            v_list.append({
                "name": getattr(v, "name", "?"),
                "trait": getattr(v, "trait", "?"),
                "x": int(v.x), "y": int(v.y),
                "state": v.state,
                "lumber": v.lumber, "stone": v.stone,
                "food": v.food,
                "hunger": round(v.hunger, 1),
                "age": v.age, "max_age": v.max_age,
                "has_bow": getattr(v, "has_bow", False),
                "current_goal": v.current_goal,
                "has_home": v.home is not None,
                "has_farm": v.farm is not None,
            })
        s_list = []
        for s in structures:
            s_list.append({
                "type": s.type, "x": s.x, "y": s.y,
                "width": s.width, "height": s.height,
                "level": s.level,
                "under_construction": s.under_construction,
            })
        t_list = [{"x": t.x, "base_y": t.base_y, "growth": round(t.growth, 2), "on_fire": t.on_fire}
                  for t in trees if t.alive]
        a_list = [{"type": a.animal_type, "x": round(a.x, 1), "y": a.y, "state": a.state}
                  for a in animals if a.alive]

        snapshot = {
            "sim_tick": sim_tick,
            "camera_x": camera_x,
            "world_width": len(heights),
            "display_width": 64,
            "display_height": 64,
            "heights": heights,
            "villagers": v_list,
            "structures": s_list,
            "trees": t_list,
            "animals": a_list,
            "weather": {"state": weather.state, "storm_factor": round(weather.storm_factor, 2)},
            "population": len(villagers),
            "timestamp": now,
        }
        path = os.path.abspath(_LIVE_SNAPSHOT_PATH)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fp:
            json.dump(snapshot, fp, separators=(",", ":"))
    except Exception as e:
        logger.debug("Failed to write live snapshot: %s", e)


def get_world_snapshot():
    """Return world state for the web UI.

    Reads the live snapshot first (updated every 3s during simulation),
    then falls back to the persistence save file.
    """
    # Try live snapshot first
    live_path = os.path.abspath(_LIVE_SNAPSHOT_PATH)
    if os.path.exists(live_path):
        try:
            mtime = os.path.getmtime(live_path)
            if time.time() - mtime < 30:  # fresh enough
                with open(live_path, "r") as fp:
                    return json.load(fp)
        except Exception:
            pass

    # Fallback to persistence save
    path = os.path.abspath(_SAVE_PATH)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as fp:
            data = json.load(fp)
        if data.get("version") != 1:
            return None

        # Extract simplified villager data
        villagers = []
        for vd in data.get("villagers", []):
            villagers.append({
                "name": vd.get("name", "?"),
                "trait": vd.get("trait", "?"),
                "x": vd.get("x", 0),
                "y": vd.get("y", 0),
                "state": vd.get("state", "idle"),
                "lumber": vd.get("lumber", 0),
                "stone": vd.get("stone", 0),
                "food": vd.get("food", 0),
                "hunger": round(vd.get("hunger", 0.0), 1),
                "age": vd.get("age", 0),
                "max_age": vd.get("max_age", 0),
                "has_bow": vd.get("has_bow", False),
                "current_goal": vd.get("current_goal"),
                "has_home": vd.get("_home_idx", -1) >= 0,
                "has_farm": vd.get("_farm_idx", -1) >= 0,
            })

        # Extract structure data
        structures = []
        for sd in data.get("structures", []):
            structures.append({
                "type": sd.get("type", "?"),
                "x": sd.get("x", 0),
                "y": sd.get("y", 0),
                "width": sd.get("width", 1),
                "height": sd.get("height", 1),
                "level": sd.get("level", 1),
                "under_construction": sd.get("under_construction", False),
            })

        # Extract tree positions
        trees = []
        for td in data.get("trees", []):
            if td.get("alive", False):
                trees.append({
                    "x": td.get("x", 0),
                    "base_y": td.get("base_y", 0),
                    "growth": round(td.get("growth", 0.0), 2),
                    "on_fire": td.get("on_fire", False),
                })

        # Extract animal positions
        animals = []
        for ad in data.get("animals", []):
            if ad.get("alive", True):
                animals.append({
                    "type": ad.get("animal_type", "?"),
                    "x": round(ad.get("x", 0), 1),
                    "y": ad.get("y", 0),
                    "state": ad.get("state", "idle"),
                })

        # Heights for minimap terrain
        heights = data.get("heights", [])

        # Weather
        wd = data.get("weather", {})
        weather = {
            "state": wd.get("state", "clear"),
            "storm_factor": round(wd.get("storm_factor", 1.0), 2),
        }

        return {
            "sim_tick": data.get("sim_tick", 0),
            "camera_x": data.get("camera_x", 0),
            "world_width": len(heights),
            "display_width": 64,
            "display_height": 64,
            "heights": heights,
            "villagers": villagers,
            "structures": structures,
            "trees": trees,
            "animals": animals,
            "weather": weather,
            "population": len(villagers),
        }
    except Exception as e:
        logger.warning("Failed to read world snapshot: %s", e)
        return None


def get_event_log_snapshot(count=100, category=None):
    """Return recent events from the event log ring buffer."""
    try:
        from .event_log import get_events
        return get_events(count=count, category=category)
    except Exception as e:
        logger.warning("Failed to read event log: %s", e)
        return []
