"""Authored Greenhollow errands, with explicit prerequisite and inventory rules."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Errand:
    name: str
    position: tuple
    kind: str
    requires: tuple = ()
    item: str = ""
    label: str = ""


VILLAGE_ERRANDS = (
    Errand("elder_request", (5, 4), "talk", label="HELP US"),
    Errand("orchard_food", (1, 1), "collect", ("elder_request",), "food", "FOOD"),
    Errand("mill_tools", (18, 6), "collect", ("elder_request",), "tools", "TOOLS"),
    Errand("watchpost_medicine", (3, 10), "collect", ("elder_request",), "medicine", "MEDICINE"),
    Errand("restore_supplies", (5, 4), "deliver",
           ("orchard_food", "mill_tools", "watchpost_medicine"), label="THANKS"),
    Errand("ranger_map", (10, 4), "talk", ("restore_supplies",), "woodland_map", "MAP"),
)


class VillageJournal:
    def __init__(self, completed=()):
        self.completed = list(completed)
        if len(set(completed)) != len(completed):
            raise ValueError("Duplicate village errand")
        seen = set()
        by_name = {errand.name: errand for errand in VILLAGE_ERRANDS}
        for name in completed:
            if name not in by_name or not set(by_name[name].requires) <= seen:
                raise ValueError("Village errand prerequisites were skipped")
            seen.add(name)

    @property
    def available(self):
        return tuple(errand for errand in VILLAGE_ERRANDS
                     if errand.name not in self.completed and set(errand.requires) <= set(self.completed))

    @property
    def inventory(self):
        items = {errand.item for errand in VILLAGE_ERRANDS
                 if errand.item and errand.name in self.completed}
        if "restore_supplies" in self.completed:
            items -= {"food", "tools", "medicine"}
        return items

    @property
    def finished(self):
        return len(self.completed) == len(VILLAGE_ERRANDS)

    def complete(self, name, position):
        errand = next((errand for errand in self.available if errand.name == name), None)
        if errand is None or errand.position != position:
            raise ValueError("Village interaction is unavailable or out of reach")
        self.completed.append(name)
        return errand
