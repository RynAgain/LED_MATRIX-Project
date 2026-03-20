"""
Tests for the configuration validator.
"""

import json
import os
import tempfile
import pytest
from src.config_validator import validate_config, validate_wifi_config, ConfigValidationError


class TestConfigValidation:
    """Tests for config.json validation."""

    def _write_temp_config(self, data):
        """Write a temp config file and return its path."""
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        return path

    def test_valid_config(self):
        config = {
            "github_branch": "main",
            "display_duration": 60,
            "log_level": "INFO",
            "sequence": [
                {"name": "snake", "type": "game", "enabled": True}
            ]
        }
        path = self._write_temp_config(config)
        try:
            errors = validate_config(path)
            error_msgs = [e for e in errors if e.severity == "error"]
            assert len(error_msgs) == 0
        finally:
            os.unlink(path)

    def test_missing_file(self):
        errors = validate_config("/nonexistent/config.json")
        assert len(errors) > 0
        assert errors[0].field == "file"

    def test_invalid_json(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            f.write("{not valid json}")
        try:
            errors = validate_config(path)
            assert len(errors) > 0
            assert errors[0].field == "json"
        finally:
            os.unlink(path)

    def test_missing_sequence(self):
        config = {"github_branch": "main"}
        path = self._write_temp_config(config)
        try:
            errors = validate_config(path)
            assert any(e.field == "sequence" for e in errors)
        finally:
            os.unlink(path)

    def test_unknown_feature_name(self):
        config = {
            "sequence": [
                {"name": "nonexistent_game", "type": "game", "enabled": True}
            ]
        }
        path = self._write_temp_config(config)
        try:
            errors = validate_config(path)
            assert any("Unknown feature" in e.message for e in errors)
        finally:
            os.unlink(path)

    def test_invalid_log_level(self):
        config = {
            "log_level": "VERBOSE",
            "sequence": [
                {"name": "snake", "type": "game", "enabled": True}
            ]
        }
        path = self._write_temp_config(config)
        try:
            errors = validate_config(path)
            assert any(e.field == "log_level" for e in errors)
        finally:
            os.unlink(path)

    def test_negative_duration(self):
        config = {
            "display_duration": -10,
            "sequence": [
                {"name": "snake", "type": "game", "enabled": True}
            ]
        }
        path = self._write_temp_config(config)
        try:
            errors = validate_config(path)
            assert any(e.field == "display_duration" for e in errors)
        finally:
            os.unlink(path)

    def test_no_enabled_features_warning(self):
        config = {
            "sequence": [
                {"name": "snake", "type": "game", "enabled": False}
            ]
        }
        path = self._write_temp_config(config)
        try:
            errors = validate_config(path)
            warnings = [e for e in errors if e.severity == "warning"]
            assert any("No features are enabled" in e.message for e in warnings)
        finally:
            os.unlink(path)

    def test_duplicate_feature_warning(self):
        config = {
            "sequence": [
                {"name": "snake", "type": "game", "enabled": True},
                {"name": "snake", "type": "game", "enabled": True}
            ]
        }
        path = self._write_temp_config(config)
        try:
            errors = validate_config(path)
            warnings = [e for e in errors if e.severity == "warning"]
            assert any("Duplicate" in e.message for e in warnings)
        finally:
            os.unlink(path)


class TestWifiConfigValidation:
    """Tests for wifi.json validation."""

    def _write_temp_config(self, data):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        return path

    def test_valid_wifi_config(self):
        config = {
            "networks": [
                {"ssid": "TestNet", "password": "", "priority": 1, "hidden": False}
            ],
            "connection_timeout": 30,
            "retry_attempts": 3,
            "retry_delay": 10,
            "connectivity_check_url": "http://example.com"
        }
        path = self._write_temp_config(config)
        try:
            errors = validate_wifi_config(path)
            error_msgs = [e for e in errors if e.severity == "error"]
            assert len(error_msgs) == 0
        finally:
            os.unlink(path)

    def test_placeholder_ssid_warning(self):
        config = {
            "networks": [
                {"ssid": "YOUR_WIFI_SSID", "password": "", "priority": 1}
            ]
        }
        path = self._write_temp_config(config)
        try:
            errors = validate_wifi_config(path)
            assert any("placeholder" in e.message.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_empty_ssid(self):
        config = {
            "networks": [
                {"ssid": "", "password": ""}
            ]
        }
        path = self._write_temp_config(config)
        try:
            errors = validate_wifi_config(path)
            assert any("empty" in e.message.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_negative_timeout(self):
        config = {
            "networks": [],
            "connection_timeout": -5
        }
        path = self._write_temp_config(config)
        try:
            errors = validate_wifi_config(path)
            assert any(e.field == "connection_timeout" for e in errors)
        finally:
            os.unlink(path)

    def test_invalid_url(self):
        config = {
            "networks": [],
            "connectivity_check_url": "not-a-url"
        }
        path = self._write_temp_config(config)
        try:
            errors = validate_wifi_config(path)
            assert any(e.field == "connectivity_check_url" for e in errors)
        finally:
            os.unlink(path)
