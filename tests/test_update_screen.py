"""
Tests for the menu UPDATE flow, especially the git "dubious ownership"
self-heal (root-run service in a user-owned repo).
"""

import subprocess
from unittest.mock import MagicMock, patch, call

import pytest

from src.menu import update_screen
from src.menu.update_screen import run_force_update, _fix_dubious_ownership


def _cp(returncode=0, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


DUBIOUS = ("fatal: detected dubious ownership in repository at "
           "'/home/ryn/LED_MATRIX-Project'")


class TestFixDubiousOwnership:
    def test_writes_system_safe_directory(self):
        with patch.object(update_screen.subprocess, "run",
                          return_value=_cp(0)) as run:
            assert _fix_dubious_ownership("/repo")
        args = run.call_args[0][0]
        assert args == ["git", "config", "--system", "--add",
                        "safe.directory", "/repo"]

    def test_returns_false_on_failure(self):
        with patch.object(update_screen.subprocess, "run",
                          return_value=_cp(1, stderr="denied")):
            assert not _fix_dubious_ownership("/repo")

    def test_never_raises(self):
        with patch.object(update_screen.subprocess, "run",
                          side_effect=OSError("boom")):
            assert not _fix_dubious_ownership("/repo")


class _FakeGit:
    """Simulates git: fetch fails with dubious ownership until the
    safe.directory config write happens, then everything succeeds."""

    def __init__(self, fixable=True):
        self.fixed = False
        self.fixable = fixable
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        if args[:2] == ["git", "config"]:
            if self.fixable:
                self.fixed = True
                return _cp(0)
            return _cp(1, stderr="read-only fs")
        if args[:2] == ["git", "fetch"]:
            if self.fixed:
                return _cp(0)
            return _cp(128, stderr=DUBIOUS)
        if args[:2] == ["git", "reset"]:
            return _cp(0, stdout="HEAD is now at abc1234")
        return _cp(0)


@pytest.fixture
def linux_env():
    """Pretend we're on the Pi and don't actually sleep or restart."""
    with patch.object(update_screen.platform, "system", return_value="Linux"), \
         patch.object(update_screen.time, "sleep"), \
         patch.object(update_screen.subprocess, "Popen") as popen:
        yield popen


class TestRunForceUpdateSelfHeal:
    def test_dubious_ownership_is_healed_and_fetch_retried(self, linux_env):
        fake = _FakeGit()
        matrix = MagicMock()
        with patch.object(update_screen.subprocess, "run", side_effect=fake):
            run_force_update(matrix)
        fetches = [c for c in fake.calls if c[:2] == ["git", "fetch"]]
        configs = [c for c in fake.calls if c[:2] == ["git", "config"]]
        resets = [c for c in fake.calls if c[:2] == ["git", "reset"]]
        assert len(fetches) == 2       # failed, healed, retried
        assert len(configs) == 1
        assert len(resets) == 1        # update proceeded after the heal

    def test_unfixable_still_shows_fetch_fail_without_crash(self, linux_env):
        fake = _FakeGit(fixable=False)
        matrix = MagicMock()
        with patch.object(update_screen.subprocess, "run", side_effect=fake):
            run_force_update(matrix)   # must not raise
        fetches = [c for c in fake.calls if c[:2] == ["git", "fetch"]]
        assert len(fetches) == 1       # heal failed -> no pointless retry
        resets = [c for c in fake.calls if c[:2] == ["git", "reset"]]
        assert len(resets) == 0        # no reset after failed fetch

    def test_other_fetch_errors_do_not_trigger_heal(self, linux_env):
        def git(args, **kwargs):
            if args[:2] == ["git", "fetch"]:
                return _cp(1, stderr="could not resolve host github.com")
            return _cp(0)
        matrix = MagicMock()
        with patch.object(update_screen.subprocess, "run",
                          side_effect=git) as run:
            run_force_update(matrix)
        config_calls = [c for c in run.call_args_list
                        if c[0][0][:2] == ["git", "config"]]
        assert config_calls == []      # network errors are not ownership errors

    def test_healthy_repo_updates_normally(self, linux_env):
        def git(args, **kwargs):
            return _cp(0, stdout="ok")
        matrix = MagicMock()
        with patch.object(update_screen.subprocess, "run", side_effect=git):
            run_force_update(matrix)
        linux_env.assert_called_once()  # service restart issued

    def test_non_linux_returns_early(self):
        matrix = MagicMock()
        with patch.object(update_screen.platform, "system",
                          return_value="Windows"), \
             patch.object(update_screen.time, "sleep"), \
             patch.object(update_screen.subprocess, "run") as run:
            run_force_update(matrix)
        run.assert_not_called()
