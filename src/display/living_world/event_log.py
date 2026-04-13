"""Ring-buffer event log for the living world simulation.

Stores the last EVENT_LOG_MAX events with tick timestamp, category,
and human-readable message.  Designed for debugging villager behavior
and world state changes without impacting performance.
"""

import threading
from collections import deque

EVENT_LOG_MAX = 1000

# Categories for filtering
CAT_VILLAGER = "villager"
CAT_BUILDING = "building"
CAT_WEATHER = "weather"
CAT_COMBAT = "combat"
CAT_ECONOMY = "economy"
CAT_WORLD = "world"
CAT_DEATH = "death"
CAT_BIRTH = "birth"

_event_log = deque(maxlen=EVENT_LOG_MAX)
_event_lock = threading.Lock()


def log_event(tick, category, message):
    """Append an event to the ring buffer.

    Args:
        tick: The simulation tick when this event occurred.
        category: One of the CAT_* constants for filtering.
        message: Human-readable description of the event.
    """
    with _event_lock:
        _event_log.append({
            "tick": tick,
            "category": category,
            "message": message,
        })


def get_events(count=100, category=None):
    """Return the most recent events, optionally filtered by category.

    Args:
        count: Maximum number of events to return (default 100).
        category: If set, only return events matching this category.

    Returns:
        List of event dicts, newest first.
    """
    with _event_lock:
        if category is not None:
            filtered = [e for e in _event_log if e["category"] == category]
        else:
            filtered = list(_event_log)
        return list(reversed(filtered[-count:]))


def get_all_events():
    """Return all events in the buffer, newest first."""
    with _event_lock:
        return list(reversed(_event_log))


def clear_events():
    """Clear the event log. Useful for testing."""
    with _event_lock:
        _event_log.clear()


def event_count():
    """Return the current number of events in the log."""
    with _event_lock:
        return len(_event_log)
