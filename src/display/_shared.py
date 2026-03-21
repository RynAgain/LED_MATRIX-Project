"""Shared state for display modules to support instant switching."""
import threading

_stop_flag = False
_lock = threading.Lock()


def request_stop():
    """Signal the current feature to stop ASAP."""
    global _stop_flag
    with _lock:
        _stop_flag = True


def clear_stop():
    """Clear the stop flag before starting a new feature."""
    global _stop_flag
    with _lock:
        _stop_flag = False


def should_stop():
    """Check if the current feature should stop. Call this in your render loop."""
    with _lock:
        return _stop_flag
