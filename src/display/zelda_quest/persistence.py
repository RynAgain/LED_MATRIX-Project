"""Validated JSON campaign saves; never deserialize executable objects."""

import copy
import json
import logging
import math
import os
from pathlib import Path
import tempfile

from .campaign import CampaignGame
from .game import MAX_HEARTS, STEP_TIME
from .world import BLOCKED
from .woodland import BROOK_ROOM, BROOK_ERRANDS, brook_open
from .journal import VillageJournal, VILLAGE_ERRANDS
from .puzzle import STONE_START, STONE_PLATE, walking_route
from .sluice import COURT_ROOM, WHEELS, LABELS, crossing_open
from .journey import JOURNEY, LOCAL_FIELDS, RETURN_ERRANDS, departed_rooms, first_visit
from .pulse import RootPulse, GUARDIAN_POSITION, GUARDIAN_HEALTH

logger = logging.getLogger(__name__)
SAVE_PATH = Path(__file__).resolve().parents[3] / "config" / "zelda_campaign_save.json"
SAVE_VERSION = 1
CONTENT_VERSION = "forest-brook-9"
MAX_SAVE_BYTES = 65536
PHASES = {"interact", "explore", "key", "boots", "rune", "lost", "roar",
          "enter", "victory", "defeat", "complete"}


def _number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Invalid numeric save value")


def _position(value, area, allow_wall=False):
    if not isinstance(value, (list, tuple)) or len(value) != 2 or any(type(v) is not int for v in value):
        raise ValueError("Invalid tile position")
    x, y = value
    if not (0 <= x < len(area.tiles[0]) and 0 <= y < len(area.tiles)):
        raise ValueError("Position outside map")
    if not allow_wall and area.tiles[y][x] in BLOCKED:
        raise ValueError("Position inside obstacle")


def _actor(data, area, hero=False):
    fields = {"x", "y", "kind", "hp", "facing", "motion", "flash", "cooldown", "previous"}
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError("Invalid actor fields")
    kinds = {"hero"} if hero else {"slime", "guard", "guardian", "treant", "sapling"}
    if data["kind"] not in kinds:
        raise ValueError("Unknown actor kind")
    _position([data["x"], data["y"]], area)
    _position(data["previous"], area)
    if sum(abs(a - b) for a, b in zip(data["previous"], (data["x"], data["y"]))) > 1:
        raise ValueError("Invalid actor motion")
    if list(data["facing"]) not in ([0, -1], [0, 1], [-1, 0], [1, 0]):
        raise ValueError("Invalid facing")
    _number(data["hp"], 0 if hero else 1, MAX_HEARTS if hero else 8)
    for key, maximum in (("motion", STEP_TIME), ("flash", 0.65), ("cooldown", 1.05)):
        _number(data[key], 0, maximum)


def _state(state, game, cached=False):
    if not isinstance(state, dict) or set(state) != set(game.capture()):
        raise ValueError("Invalid state fields")
    room = state["room"]
    if type(room) is not int or not 0 <= room < len(game.areas):
        raise ValueError("Unknown area")
    area = game.areas[room]
    visit = state["visit_index"]
    if type(visit) is not int or not 0 <= visit < len(JOURNEY):
        raise ValueError("Invalid journey visit")
    if not cached and JOURNEY[visit].room != room:
        raise ValueError("Journey room mismatch")
    shrine_visit = first_visit(2)
    court_visit = first_visit(COURT_ROOM)
    pulse_data = state["root_pulse"]
    if not isinstance(pulse_data, dict) or set(pulse_data) != {"mode", "ticks", "cycle"}:
        raise ValueError("Invalid root pulse fields")
    pulse = RootPulse(**pulse_data)
    if (visit < shrine_visit and pulse.mode != "dormant") or (visit > shrine_visit and pulse.mode != "cleared"):
        raise ValueError("Root guardian progression skipped")
    if (pulse.mode == "dormant") == state["has_boots"]:
        raise ValueError("Root guardian activation disagrees with boots")
    brook_stage = state["brook_stage"]
    if type(brook_stage) is not int or not 0 <= brook_stage <= len(BROOK_ERRANDS):
        raise ValueError("Invalid brook stage")
    brook_visit = first_visit(BROOK_ROOM)
    if ((visit < brook_visit and brook_stage != 0)
            or (visit > brook_visit and brook_stage != len(BROOK_ERRANDS))):
        raise ValueError("Brook progression skipped")
    stage = state["sluice_stage"]
    if type(stage) is not int or not 0 <= stage <= len(WHEELS):
        raise ValueError("Invalid sluice stage")
    if (visit < court_visit and stage != 0) or (visit > court_visit and stage != len(WHEELS)):
        raise ValueError("Sluice progression skipped")
    _position(state["stone"], game.areas[2])
    if visit < shrine_visit and tuple(state["stone"]) != STONE_START:
        raise ValueError("Stone moved before shrine")
    if state["has_boots"] and tuple(state["stone"]) != STONE_PLATE:
        raise ValueError("Boots obtained before solving stone")
    if not isinstance(state["journal"], list):
        raise ValueError("Invalid journal")
    VillageJournal(state["journal"])
    labels = {""} | set(LABELS) | {errand.label for errand in VILLAGE_ERRANDS + RETURN_ERRANDS + BROOK_ERRANDS}
    if state["interaction_label"] not in labels:
        raise ValueError("Unknown interaction")
    if state["phase"] not in PHASES:
        raise ValueError("Unknown phase")
    for key in ("has_key", "chest_open", "gate_open", "has_boots", "boss_reinforced"):
        if type(state[key]) is not bool:
            raise ValueError("Invalid objective flag")
    if state["has_key"] and (not state["chest_open"] or state["gate_open"]):
        raise ValueError("Inconsistent key state")
    if state["chest_open"] and not area.chest:
        raise ValueError("Opened a chest the area does not have")
    lit = state["sigils_lit"]
    if type(lit) is not int or not 0 <= lit <= len(area.sigils):
        raise ValueError("Invalid sigil progress")
    unlocked = state["chest_open"] or (bool(area.sigils) and lit == len(area.sigils))
    if state["gate_open"] and not unlocked:
        raise ValueError("Opened gate without a key or the sigil order")
    if state["boss_reinforced"] and not area.boss:
        raise ValueError("Reinforcement outside a boss lair")
    if not state["has_boots"] and visit > shrine_visit:
        raise ValueError("Skipped the boots needed to pass the vines")
    if type(state["enemy_turns"]) is not int or not 0 <= state["enemy_turns"] <= 10 ** 9:
        raise ValueError("Invalid enemy turn count")
    for key, low, high in (("elapsed", 0, 1e12), ("wins", 0, 1000000), ("runs", 1, 1000000),
                           ("rupees", 0, 1000000),
                           ("phase_time", -0.1, 2.5), ("swing", 0, 0.2),
                           ("hero_clock", -0.1, STEP_TIME), ("enemy_clock", -0.1, 0.75)):
        _number(state[key], low, high)
    _number(state["content_seconds"], 0, 1e12)
    _actor(state["hero"], area, hero=True)
    hero_tile = area.tiles[state["hero"]["y"]][state["hero"]["x"]]
    if hero_tile == "V" and not state["has_boots"]:
        raise ValueError("Hero stranded in the vines without boots")
    if not isinstance(state["enemies"], list) or len(state["enemies"]) > len(area.spawns) + 1:
        raise ValueError("Invalid enemy list")
    positions = {(state["hero"]["x"], state["hero"]["y"])}
    for enemy in state["enemies"]:
        _actor(enemy, area)
        position = (enemy["x"], enemy["y"])
        if position in positions:
            raise ValueError("Overlapping actors")
        positions.add(position)
    if room == 2:
        guardians = [enemy for enemy in state["enemies"] if enemy["kind"] == "guardian"]
        active = pulse.mode in ("warning", "exposed")
        if len(guardians) != int(active):
            raise ValueError("Root guardian missing or duplicated")
        if active and (tuple((guardians[0]["x"], guardians[0]["y"])) != GUARDIAN_POSITION
                       or guardians[0]["hp"] != GUARDIAN_HEALTH - pulse.cycle):
            raise ValueError("Root guardian position or health inconsistent")
    if room == BROOK_ROOM:
        def brook_passable(cell):
            x, y = cell
            return (0 <= y < len(area.tiles) and 0 <= x < len(area.tiles[0])
                    and area.tiles[y][x] not in BLOCKED and brook_open(cell, brook_stage))

        hero = state["hero"]
        if walking_route(area.start, (hero["x"], hero["y"]), None, brook_passable) is None:
            raise ValueError("Hero stranded beyond brook bridge")
        if any(not brook_open(position, brook_stage) for position in positions):
            raise ValueError("Actor inside lowered brook bridge")
        if state["chest_open"] and brook_stage != len(BROOK_ERRANDS):
            raise ValueError("Brook treasury opened before bridge")
    if room == COURT_ROOM:
        def canal_passable(cell):
            x, y = cell
            return (0 <= y < len(area.tiles) and 0 <= x < len(area.tiles[0])
                    and area.tiles[y][x] not in BLOCKED and crossing_open(cell, stage))

        hero = state["hero"]
        if walking_route(area.start, (hero["x"], hero["y"]), None, canal_passable) is None:
            raise ValueError("Hero stranded beyond an undrained canal")
        if any(not crossing_open(position, stage) for position in positions):
            raise ValueError("Actor inside flooded crossing")
        if state["chest_open"] and stage != len(WHEELS):
            raise ValueError("Treasury opened before draining canal")
    if not isinstance(state["pickups"], list) or len(state["pickups"]) > len(area.spawns) + 1:
        raise ValueError("Invalid pickup list")
    for pickup in state["pickups"]:
        if not isinstance(pickup, list) or len(pickup) != 3 or pickup[2] not in ("heart", "rupee"):
            raise ValueError("Invalid pickup")
        _position(pickup[:2], area)
        if room == BROOK_ROOM and not brook_open(tuple(pickup[:2]), brook_stage):
            raise ValueError("Pickup inside lowered brook bridge")
        if room == COURT_ROOM and not crossing_open(tuple(pickup[:2]), stage):
            raise ValueError("Pickup inside flooded crossing")
    if not cached:
        _journey_state(state, game)


def _journey_state(state, game):
    index = state["visit_index"]
    before = [errand.name for visit in JOURNEY[:index] for errand in visit.errands]
    available = before + [errand.name for errand in JOURNEY[index].errands]
    completed = state["return_errands"]
    if (not isinstance(completed, list) or len(completed) < len(before)
            or completed != available[:len(completed)]):
        raise ValueError("Invalid return errand order")
    rooms = state["area_states"]
    if not isinstance(rooms, list) or len(rooms) != len(game.areas):
        raise ValueError("Invalid area cache")
    visited = departed_rooms(index)
    for room, local in enumerate(rooms):
        if room not in visited:
            if local is not None:
                raise ValueError("Cached unvisited area")
            continue
        if not isinstance(local, dict) or set(local) != set(LOCAL_FIELDS):
            raise ValueError("Invalid cached area fields")
        snapshot = dict(state, room=room, **local)
        # The hero is global, not an occupant of the inactive room.
        snapshot["hero"] = dict(state["hero"], x=game.areas[room].start[0], y=game.areas[room].start[1],
                                previous=list(game.areas[room].start), motion=0.0)
        _state(snapshot, game, cached=True)


def encode(game):
    return {"version": SAVE_VERSION, "content": CONTENT_VERSION,
            "active_seconds": game.active_seconds, "deaths": game.deaths,
            "pending_seconds": game.pending_seconds,
            "completed_areas": list(game.completed_areas), "finished": game.finished,
            "current": game.capture(), "checkpoint": copy.deepcopy(game.checkpoint)}


def decode(data):
    game = CampaignGame()
    if not isinstance(data, dict) or set(data) != set(encode(game)):
        raise ValueError("Invalid campaign fields")
    if data["version"] != SAVE_VERSION or data["content"] != CONTENT_VERSION:
        raise ValueError("Incompatible campaign save")
    _number(data["active_seconds"], 0, 1e12)
    _number(data["pending_seconds"], 0, 1 / 60)
    _number(data["deaths"], 0, 1000000)
    if type(data["finished"]) is not bool:
        raise ValueError("Invalid completion flag")
    _state(data["current"], game)
    _state(data["checkpoint"], game)
    if data["current"]["content_seconds"] > data["active_seconds"] + 1e-6:
        raise ValueError("Content clock exceeds active play")
    room = data["current"]["room"]
    checkpoint = data["checkpoint"]
    if (checkpoint["visit_index"] != data["current"]["visit_index"]
            or checkpoint["room"] != room or checkpoint["phase"] != "explore"
            or checkpoint["hero"]["hp"] < 1):
        raise ValueError("Invalid checkpoint")
    expected = departed_rooms(data["current"]["visit_index"] + int(data["finished"]))
    if data["completed_areas"] != expected:
        raise ValueError("Invalid campaign progression")
    if data["finished"] != (data["current"]["phase"] == "complete"):
        raise ValueError("Invalid final phase")
    if data["finished"] and data["current"]["visit_index"] != len(JOURNEY) - 1:
        raise ValueError("Campaign completed early")
    game.restore(data["current"])
    for key in ("active_seconds", "pending_seconds", "deaths", "completed_areas", "finished", "checkpoint"):
        setattr(game, key, copy.deepcopy(data[key]))
    return game


class SaveStore:
    def __init__(self, path=SAVE_PATH):
        self.path = Path(path)
        self.writable = True

    def load(self):
        try:
            if self.path.stat().st_size > MAX_SAVE_BYTES:
                raise ValueError("Save exceeds size limit")
            return decode(json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return CampaignGame()
        except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
            self.writable = False
            logger.warning("Campaign save preserved, starting unsaved preview: %s", exc)
            return CampaignGame()

    def save(self, game):
        if not self.writable:
            return False
        temporary = None
        try:
            data = encode(game)
            decode(data)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=self.path.name + ".", suffix=".tmp", delete=False) as fp:
                temporary = Path(fp.name)
                json.dump(data, fp, allow_nan=False, separators=(",", ":"))
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(temporary, self.path)
            return True
        except (OSError, ValueError, TypeError, KeyError) as exc:
            logger.warning("Campaign save failed: %s", exc)
            return False
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
