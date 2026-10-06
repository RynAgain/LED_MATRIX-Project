"""Published forest demo lifecycle and registry integration."""
import importlib
import json
from unittest.mock import create_autospec

import pytest

from src.display import _shared, zelda_quest
from src.display.zelda_quest import woods
from src.display.zelda_quest.campaign import CampaignGame
from src.display.zelda_quest.persistence import SaveStore, encode, decode
from src.feature_registry import FEATURE_MODULES
from src.simulator.matrix import RGBMatrix


@pytest.fixture(autouse=True)
def clear_stop():
    _shared.clear_stop()
    yield
    _shared.clear_stop()


@pytest.fixture
def clock(monkeypatch):
    value = [0.0]
    monkeypatch.setattr(zelda_quest.time, "monotonic", lambda: value[0])
    monkeypatch.setattr(zelda_quest, "interruptible_sleep", lambda seconds: value.__setitem__(0, value[0] + seconds))
    return value


@pytest.fixture
def path(monkeypatch, tmp_path):
    path = tmp_path / "woods.json"
    monkeypatch.setattr(woods, "SAVE_PATH", path)
    return path


@pytest.fixture(scope="module")
def ending():
    game = CampaignGame()
    for _ in range(30 * 600):
        game.update(1 / 30)
        if "restore_village" in game.return_errands:
            return encode(game)
    pytest.fail("Did not reach ending")


def test_registry_and_menu(tmp_path):
    from src.main import _sync_sequence_with_registry
    from src.menu.menu_data import build_demos_menu, build_lock_menu

    assert importlib.import_module(FEATURE_MODULES["zelda_quest"]).run is zelda_quest.run
    assert importlib.import_module(FEATURE_MODULES["zelda_woods"]).run is woods.run
    assert any(i.payload == "zelda_woods" and i.label == "ZELDA WOODS" for i in build_demos_menu().items)
    assert any(i.payload == "zelda_woods" and i.label == "ZELDA WOODS" for i in build_lock_menu().items)
    config = {"sequence": []}
    config_path = tmp_path / "config.json"
    _sync_sequence_with_registry(config, str(config_path))
    assert {"name": "zelda_woods", "type": "effect", "enabled": True} in json.loads(
        config_path.read_text())["sequence"]


def test_actual_runner_resumes(clock, path):
    matrix = create_autospec(RGBMatrix, instance=True)
    run = importlib.import_module(FEATURE_MODULES["zelda_woods"]).run
    run(matrix, duration=1)
    first = SaveStore(path).load()
    run(matrix, duration=1)
    second = SaveStore(path).load()
    assert 0.8 < first.active_seconds < 1.1
    assert first.active_seconds + 0.8 < second.active_seconds < 2.1
    assert matrix.Clear.call_count == 2
    assert matrix.SetImage.call_args.args[0].size == (64, 64)


def test_finished_save_restarts(clock, path, ending):
    game = decode(ending)
    for _ in range(90):
        game.update(1 / 30)
    assert game.finished and SaveStore(path).save(game)
    woods.run(create_autospec(RGBMatrix, instance=True), duration=0.2)
    restored = SaveStore(path).load()
    assert not restored.finished and restored.room == 0
    assert 0 < restored.active_seconds < 0.3


def test_continuous_repeat(clock, path, ending):
    assert SaveStore(path).save(decode(ending))
    woods.run(create_autospec(RGBMatrix, instance=True), duration=6)
    restored = SaveStore(path).load()
    assert not restored.finished and restored.room == 0
    assert 0.5 < restored.active_seconds < 3


def test_invalid_save_preserved(clock, path):
    original = b"invalid json"
    path.write_bytes(original)
    woods.run(create_autospec(RGBMatrix, instance=True), duration=0.2)
    assert path.read_bytes() == original


@pytest.mark.parametrize("duration", [0, -1])
def test_nonpositive_duration(clock, path, duration):
    matrix = create_autospec(RGBMatrix, instance=True)
    woods.run(matrix, duration=duration)
    matrix.SetImage.assert_not_called()
    matrix.Clear.assert_called_once()
    assert clock[0] == 0


def test_stop_and_save(path):
    matrix = create_autospec(RGBMatrix, instance=True)
    matrix.SetImage.side_effect = lambda image: _shared.request_stop()
    woods.run(matrix)
    matrix.SetImage.assert_called_once()
    matrix.Clear.assert_called_once()
    assert path.exists()


def test_error_and_save(path):
    matrix = create_autospec(RGBMatrix, instance=True)
    matrix.SetImage.side_effect = RuntimeError("display failure")
    with pytest.raises(RuntimeError, match="display failure"):
        woods.run(matrix)
    matrix.Clear.assert_called_once()
    assert path.exists()
