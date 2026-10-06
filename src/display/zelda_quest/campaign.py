"""Persistent campaign progression, independent of carousel wall-clock time."""

import copy

from .game import MAX_HEARTS, QuestGame, Actor
from .world import FOREST_REGION
from .woodland import WOODLAND_AREAS, BROOK_ROOM, BROOK_ERRANDS, brook_open
from .woodland import SAWMILL_ROOM, SAWMILL_LOG, SAWMILL_PLATE, SAWMILL_SHUTTER
from .journal import VillageJournal
from .watchwood import WATCHWOOD_ROOM, CONTROLS, LABELS as WATCH_LABELS, watchwood_passable
from .puzzle import STONE_START, STONE_PLATE, next_stone_action
from .sluice import COURT_ROOM, WHEELS, LABELS, crossing_open
from .journey import JOURNEY, LOCAL_FIELDS, SPIRIT_TILES
from .pulse import RootPulse, GUARDIAN_POSITION, GUARDIAN_HEALTH


class CampaignGame(QuestGame):
    def __init__(self):
        self.brook_stage = 0
        self.watchwood_stage = 0
        self.sawmill_log = SAWMILL_LOG
        self.root_pulse = RootPulse()
        self.visit_index = 0
        self.area_states = [None] * len(FOREST_REGION + WOODLAND_AREAS)
        self.return_errands = []
        self.stone = STONE_START
        self.sluice_stage = 0
        self.journal = VillageJournal()
        self.interaction_label = ""
        super().__init__(areas=FOREST_REGION + WOODLAND_AREAS)
        self.active_seconds = 0.0
        self.content_seconds = 0.0
        self.pending_seconds = 0.0
        self.deaths = 0
        self.completed_areas = []
        self.finished = False
        self.checkpoint = self.capture()

    def capture(self):
        snapshot = copy.deepcopy({
            "visit_index": self.visit_index, "area_states": self.area_states,
            "return_errands": self.return_errands, "root_pulse": vars(self.root_pulse),
            "room": self.room, "elapsed": self.elapsed, "wins": self.wins, "runs": self.runs,
            "content_seconds": self.content_seconds,
            "journal": self.journal.completed, "interaction_label": self.interaction_label,
            "rupees": self.rupees, "has_key": self.has_key,
            "chest_open": self.chest_open, "gate_open": self.gate_open,
            "has_boots": self.has_boots, "sigils_lit": self.sigils_lit,
            "boss_reinforced": self.boss_reinforced, "stone": list(self.stone),
            "sluice_stage": self.sluice_stage, "brook_stage": self.brook_stage,
            "sawmill_log": list(self.sawmill_log), "watchwood_stage": self.watchwood_stage,
            "phase": self.phase, "phase_time": self.phase_time,
            "swing": self.swing, "hero_clock": self.hero_clock,
            "enemy_clock": self.enemy_clock, "enemy_turns": self.enemy_turns,
            "hero": vars(self.hero), "enemies": [vars(e) for e in self.enemies],
            "pickups": [[x, y, kind] for (x, y), kind in self.pickups.items()],
        })
        for actor in [snapshot["hero"]] + snapshot["enemies"]:
            actor["facing"] = list(actor["facing"])
            actor["previous"] = list(actor["previous"])
        return snapshot

    def restore(self, state):
        state = copy.deepcopy(state)
        state["journal"] = VillageJournal(state["journal"])
        state["stone"] = tuple(state["stone"])
        state["sawmill_log"] = tuple(state["sawmill_log"])
        state["root_pulse"] = RootPulse(**state["root_pulse"])
        for key in ("hero", "enemies"):
            actors = [state[key]] if key == "hero" else state[key]
            restored = []
            for data in actors:
                previous = tuple(data.pop("previous"))
                data["facing"] = tuple(data["facing"])
                actor = Actor(**data)
                actor.previous = previous
                restored.append(actor)
            state[key] = restored[0] if key == "hero" else restored
        state["pickups"] = {(x, y): kind for x, y, kind in state["pickups"]}
        for key, value in state.items():
            setattr(self, key, value)

    @property
    def visit(self):
        return JOURNEY[self.visit_index]

    @property
    def next_return_errand(self):
        return next((errand for errand in self.visit.errands if errand.name not in self.return_errands), None)

    @property
    def next_area_name(self):
        if self.visit_index + 1 < len(JOURNEY):
            return self.areas[JOURNEY[self.visit_index + 1].room].name
        return "RESTORED"

    def passable(self, position):
        if self.room == WATCHWOOD_ROOM and not watchwood_passable(position, self.watchwood_stage):
            return False
        if self.room == SAWMILL_ROOM:
            if position == self.sawmill_log:
                return False
            if position == SAWMILL_SHUTTER and self.sawmill_log != SAWMILL_PLATE:
                return False
        if self.room == BROOK_ROOM and not brook_open(position, self.brook_stage):
            return False
        if self.room == 1 and position in SPIRIT_TILES and not self.has_boots:
            return False
        if self.room == COURT_ROOM and not crossing_open(position, self.sluice_stage):
            return False
        if self.room == 2 and position == self.stone:
            return False
        if self.room == 2 and position == self.area.boots and self.stone != STONE_PLATE:
            return False
        return super().passable(position)

    @property
    def root_guardian(self):
        if self.room == 2:
            return next((enemy for enemy in self.enemies if enemy.kind == "guardian"), None)
        return None

    def _hero_turn(self):
        if self.room == SAWMILL_ROOM and self.sawmill_log != SAWMILL_PLATE:
            targets = [enemy.position for enemy in self.enemies]
            if not any(cell == self.hero.position or self.path(self.hero.position, cell) for cell in targets):
                routes = [self.path(self.hero.position, cell) for cell in self.pickups]
                route = min((route for route in routes if route), key=len, default=[])
                if route:
                    self.hero.move(route[0])
                    return
                action = next_stone_action(self.hero.position, self.sawmill_log, SAWMILL_PLATE,
                                           lambda cell: cell != SAWMILL_SHUTTER
                                           and super(CampaignGame, self).passable(cell))
                if action:
                    kind, target = action
                    if kind == "push":
                        previous = self.sawmill_log
                        self.sawmill_log = target
                        self.hero.move(previous)
                        if target == SAWMILL_PLATE:
                            self.interaction_label = "MILL OPEN"
                            self._set_phase("interact", 0.8)
                    else:
                        self.hero.move(target)
                return
        if self.root_guardian and self.root_pulse.mode == "warning":
            route = self.path(self.hero.position, self.root_pulse.safe_tile, {self.root_guardian.position})
            if route:
                self.hero.move(route[0])
            return
        if self.room == 2 and not self.enemies and not self.pickups and self.stone != STONE_PLATE:
            action = next_stone_action(self.hero.position, self.stone, STONE_PLATE,
                                       lambda cell: super(CampaignGame, self).passable(cell))
            if action:
                kind, target = action
                if kind == "push":
                    previous = self.stone
                    self.stone = target
                    self.hero.move(previous)
                else:
                    self.hero.move(target)
            return
        super()._hero_turn()

    def _strike(self, enemy):
        if enemy is self.root_guardian:
            if self.root_pulse.mode != "exposed":
                return
            super()._strike(enemy)
            self.root_pulse.struck(enemy not in self.enemies)
            return
        super()._strike(enemy)

    def _enemy_turn(self):
        if not self.root_guardian:
            super()._enemy_turn()

    def _objective(self):
        if self.room == WATCHWOOD_ROOM and self.watchwood_stage < len(CONTROLS):
            return CONTROLS[self.watchwood_stage]
        if self.room == BROOK_ROOM and self.brook_stage < len(BROOK_ERRANDS):
            return BROOK_ERRANDS[self.brook_stage].position
        if self.visit.exit:
            errand = self.next_return_errand
            return errand.position if errand else self.visit.exit
        if self.room == COURT_ROOM and self.sluice_stage < len(WHEELS):
            return WHEELS[self.sluice_stage]
        if self.room == 0 and not self.journal.finished:
            choices = [(self.path(self.hero.position, errand.position), errand)
                       for errand in self.journal.available]
            choices = [(route, errand) for route, errand in choices
                       if route or errand.position == self.hero.position]
            if choices:
                return min(choices, key=lambda choice: len(choice[0]))[1].position
        return super()._objective()

    def _contacts(self):
        if self.room == 0 and not self.enemies and self.hero.hp > 0:
            errand = next((item for item in self.journal.available if item.position == self.hero.position), None)
            if errand:
                self.journal.complete(errand.name, self.hero.position)
                self.interaction_label = errand.label
                self._set_phase("interact", 0.8)
                return
        if self.visit.exit and self.hero.hp > 0 and not self.enemies:
            errand = self.next_return_errand
            if errand and self.hero.position == errand.position:
                self.return_errands.append(errand.name)
                self.interaction_label = errand.label
                self._set_phase("interact", 0.8)
            elif errand is None and self.hero.position == self.visit.exit:
                self._set_phase("enter", 0.7)
            return
        if self.root_guardian:
            # Its attack is the telegraphed pulse, not incidental adjacency.
            self.root_guardian.cooldown = 0.85
        super()._contacts()
        if (self.room == BROOK_ROOM and self.phase == "explore" and self.hero.hp > 0
                and self.brook_stage < len(BROOK_ERRANDS)):
            errand = BROOK_ERRANDS[self.brook_stage]
            if self.hero.position == errand.position:
                self.brook_stage += 1
                self.interaction_label = errand.label
                self._set_phase("interact", 0.8)
        if (self.room == WATCHWOOD_ROOM and self.phase == "explore" and self.hero.hp > 0
                and self.watchwood_stage < len(CONTROLS)
                and self.hero.position == CONTROLS[self.watchwood_stage]):
            self.interaction_label = WATCH_LABELS[self.watchwood_stage]
            self.watchwood_stage += 1
            self._set_phase("interact", 0.8)
        if self.room == 2 and self.has_boots and self.root_pulse.mode == "dormant":
            self.enemies.append(Actor(*GUARDIAN_POSITION, kind="guardian", hp=GUARDIAN_HEALTH))
            self.root_pulse.warn()
        if (self.room == COURT_ROOM and self.phase == "explore" and self.hero.hp > 0
                and self.sluice_stage < len(WHEELS)
                and self.hero.position == WHEELS[self.sluice_stage]):
            self.interaction_label = LABELS[self.sluice_stage]
            self.sluice_stage += 1
            self._set_phase("interact", 0.8)

    def _advance_area(self):
        if self.room not in self.completed_areas:
            self.completed_areas.append(self.room)
        snapshot = self.capture()
        self.area_states[self.room] = {key: snapshot[key] for key in LOCAL_FIELDS}
        if self.visit_index + 1 == len(JOURNEY):
            self.finished = True
            self.phase = "complete"
            self.phase_time = 0.0
            return
        self.visit_index += 1
        self.has_key = self.chest_open = self.gate_open = False
        self.hero.hp = MAX_HEARTS
        self.hero.flash = 0.0
        self._load_room(self.visit.room)
        cached = self.area_states[self.room]
        if cached is not None:
            snapshot = self.capture()
            snapshot.update(copy.deepcopy(cached))
            self.restore(snapshot)
        self.hero.x, self.hero.y = self.visit.arrival
        self.hero.previous = self.hero.position
        self.hero.motion = 0.0
        self.checkpoint = self.capture()

    def update(self, dt):
        if self.finished:
            return
        self.pending_seconds += max(0.0, min(dt, 0.1))
        while self.pending_seconds + 1e-12 >= 1 / 60:
            self.pending_seconds = max(0.0, self.pending_seconds - 1 / 60)
            self._step(1 / 60)

    def _step(self, dt):
        if self.finished or dt == 0:
            return
        if self.phase != "defeat":
            self.active_seconds += dt
            self.content_seconds += dt
        super().update(dt)
        if self.root_guardian and self.phase == "explore":
            if self.root_pulse.tick(self.hero.position) == "damage":
                self.hero.hp = max(0, self.hero.hp - 1)
                self.hero.flash = 0.65
                if self.hero.hp == 0:
                    self._set_phase("defeat", 2.0)

    def _phase_expired(self):
        if self.phase == "defeat":
            self.deaths += 1
            self.restore(self.checkpoint)
        elif self.phase in ("enter", "victory"):
            self._advance_area()
        else:
            super()._phase_expired()
