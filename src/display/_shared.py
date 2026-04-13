"""Shared state for display modules to support instant switching."""
import threading
import time

_stop_event = threading.Event()


def request_stop():
    """Signal the current feature to stop ASAP."""
    _stop_event.set()


def clear_stop():
    """Clear the stop flag before starting a new feature."""
    _stop_event.clear()


def should_stop():
    """Check if the current feature should stop. Call this in your render loop."""
    return _stop_event.is_set()


def interruptible_sleep(seconds, interval=0.1):
    """Sleep for the given duration, returning early if stop is signalled.
    Returns True if sleep completed, False if interrupted by stop signal."""
    if _stop_event.wait(timeout=seconds):
        return False  # interrupted
    return True
