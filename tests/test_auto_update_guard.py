"""Safety guards around AutoUpdater's destructive `reset --hard` sync.

has_updates() used to return True whenever HEAD != origin/<branch>, which
includes a dev checkout that is AHEAD of origin. pull_updates() then ran
`git reset --hard origin/<branch>` and silently destroyed the local commits
(this actually happened: a test run's idle-cycle update check orphaned three
unpushed commits). These tests pin the ancestry guard that prevents it.
"""

import subprocess
from types import SimpleNamespace

import pytest

from src.updater.auto_update import AutoUpdater


def _result(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def _updater_with_git(monkeypatch, responses):
    """Build an AutoUpdater whose _run_git answers from a canned table.

    :param responses: dict mapping the first distinguishing git arg tuple to a
        result; keys are matched by ``args[0]`` (rev-parse / merge-base).
    """
    updater = AutoUpdater.__new__(AutoUpdater)  # skip config-loading __init__
    updater.branch = "main"

    def fake_run_git(args, timeout=60):
        if args[0] == "rev-parse":
            target = args[1]
            return responses[target]
        if args[0] == "merge-base":
            return responses["is-ancestor"]
        raise AssertionError(f"unexpected git call: {args}")

    updater._run_git = fake_run_git
    return updater


class TestHasUpdatesAncestryGuard:
    def test_identical_hashes_no_update(self, monkeypatch):
        upd = _updater_with_git(monkeypatch, {
            "HEAD": _result("aaa111\n"),
            "origin/main": _result("aaa111\n"),
        })
        assert upd.has_updates() is False

    def test_remote_strictly_ahead_is_an_update(self, monkeypatch):
        upd = _updater_with_git(monkeypatch, {
            "HEAD": _result("aaa111\n"),
            "origin/main": _result("bbb222\n"),
            "is-ancestor": _result(returncode=0),  # HEAD is ancestor of origin
        })
        assert upd.has_updates() is True

    def test_local_ahead_refuses_update(self, monkeypatch):
        """Local-only commits must never be treated as an available update."""
        upd = _updater_with_git(monkeypatch, {
            "HEAD": _result("ccc333\n"),
            "origin/main": _result("bbb222\n"),
            "is-ancestor": _result(returncode=1),  # HEAD NOT ancestor -> ahead
        })
        assert upd.has_updates() is False

    def test_git_failure_refuses_update(self, monkeypatch):
        upd = _updater_with_git(monkeypatch, {
            "HEAD": _result(returncode=128),
            "origin/main": _result("bbb222\n"),
        })
        assert upd.has_updates() is False

    def test_merge_base_unavailable_refuses_update(self, monkeypatch):
        """If ancestry can't be proven, err on the side of not resetting."""
        upd = _updater_with_git(monkeypatch, {
            "HEAD": _result("ccc333\n"),
            "origin/main": _result("bbb222\n"),
            "is-ancestor": None,  # git itself failed
        })
        assert upd.has_updates() is False


class TestSuiteLockout:
    def test_pull_updates_is_fenced_inside_tests(self):
        """The conftest guard must make real pull_updates() unreachable."""
        updater = AutoUpdater.__new__(AutoUpdater)
        with pytest.raises(AssertionError, match="real AutoUpdater"):
            updater.pull_updates()

    def test_fetch_remote_is_inert_inside_tests(self):
        updater = AutoUpdater.__new__(AutoUpdater)
        assert updater.fetch_remote() is False

    def test_carousel_update_check_is_noop(self, tmp_path):
        from src.app_state import DemoCarousel

        assert DemoCarousel._trigger_update_check(object()) is None
