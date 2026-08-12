"""load_config must self-heal the carousel sequence against the registry.

The updater preserves the device's local config.json across updates, so
new features can only reach the carousel through this merge. Five
features had silently drifted out before it existed.
"""

import json

import pytest

from src.main import load_config, _sync_sequence_with_registry
from src.feature_registry import FEATURE_MODULES


def _write(tmp_path, config):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(config))
    return str(p)


def test_missing_features_are_appended_and_persisted(tmp_path):
    config = {"sequence": [{"name": "snake", "type": "game", "enabled": False}]}
    path = _write(tmp_path, config)
    _sync_sequence_with_registry(config, path)

    names = [i["name"] for i in config["sequence"]]
    assert set(names) == set(FEATURE_MODULES) | {"snake"}
    # Existing entries keep their state; new ones default enabled.
    by_name = {i["name"]: i for i in config["sequence"]}
    assert by_name["snake"]["enabled"] is False
    assert by_name["dungeon"]["enabled"] is True
    assert by_name["missile_command"]["type"] == "game"
    assert by_name["rain_radar"]["type"] == "effect"
    # And the merge was written back for the toggle screen / web panel.
    on_disk = json.loads(open(path).read())
    assert {i["name"] for i in on_disk["sequence"]} == set(names)


def test_complete_sequence_is_untouched(tmp_path):
    config = {"sequence": [{"name": n, "type": "effect", "enabled": True}
                           for n in FEATURE_MODULES]}
    path = _write(tmp_path, config)
    before = json.dumps(config)
    _sync_sequence_with_registry(config, path)
    assert json.dumps(config) == before
    # No write-back needed either.
    assert json.loads(open(path).read()) != {}


def test_malformed_sequence_does_not_raise(tmp_path):
    for bad in ({}, {"sequence": "nope"}, {"sequence": [42]}):
        path = _write(tmp_path, dict(bad))
        _sync_sequence_with_registry(bad, path)   # must not raise


def test_unwritable_path_does_not_raise():
    config = {"sequence": []}
    _sync_sequence_with_registry(config, "Z:/nonexistent/nowhere.json")
    # Merge still happened in memory even though persisting failed.
    assert {i["name"] for i in config["sequence"]} == set(FEATURE_MODULES)


def test_committed_config_contains_every_registry_feature():
    """The shipped default config must not drift from the registry again."""
    cfg = json.load(open("config/config.json"))
    names = {i["name"] for i in cfg["sequence"]}
    missing = set(FEATURE_MODULES) - names
    assert not missing, f"features missing from config.json sequence: {missing}"
