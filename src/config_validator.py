#!/usr/bin/env python3
"""
Configuration validator for LED Matrix Project.
Validates config.json and wifi.json against expected schemas.
"""

import json
import os
import sys
import logging

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Known feature names that map to display modules
VALID_FEATURE_NAMES = {
    "tic_tac_toe", "snake", "pong", "billiards",
    "time_display", "bitcoin_price", "youtube_stream",
    "fire", "plasma", "matrix_rain", "starfield",
    "game_of_life", "rainbow_waves", "weather", "text_scroller",
    "stock_ticker", "sp500_heatmap", "binary_clock", "countdown",
    "lava_lamp", "living_world", "qr_code", "slideshow",
    "galaga", "space_invaders", "logo_wholefoods",
    "github_stats", "tanks", "wireframe", "maze_3d",
    "terrain_ball"
}

VALID_FEATURE_TYPES = {"game", "utility", "video", "effect"}


class ConfigValidationError:
    """Represents a single validation error."""

    def __init__(self, field, message, severity="error"):
        self.field = field
        self.message = message
        self.severity = severity  # "error" or "warning"

    def __str__(self):
        return f"[{self.severity.upper()}] {self.field}: {self.message}"


def validate_config(config_path=None):
    """
    Validate config/config.json.

    Args:
        config_path: Path to config.json. Defaults to config/config.json.

    Returns:
        List of ConfigValidationError objects. Empty list means valid.
    """
    if config_path is None:
        config_path = os.path.join(PROJECT_ROOT, "config", "config.json")

    errors = []

    # Check file exists
    if not os.path.exists(config_path):
        errors.append(ConfigValidationError("file", f"Config file not found: {config_path}"))
        return errors

    # Parse JSON
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(ConfigValidationError("json", f"Invalid JSON: {e}"))
        return errors

    # Must be a dict
    if not isinstance(config, dict):
        errors.append(ConfigValidationError("root", "Config must be a JSON object"))
        return errors

    # Validate github_branch
    if "github_branch" in config:
        if not isinstance(config["github_branch"], str):
            errors.append(ConfigValidationError("github_branch", "Must be a string"))
        elif not config["github_branch"].strip():
            errors.append(ConfigValidationError("github_branch", "Must not be empty"))

    # Validate display_duration
    if "display_duration" in config:
        dur = config["display_duration"]
        if not isinstance(dur, (int, float)):
            errors.append(ConfigValidationError("display_duration", "Must be a number"))
        elif dur <= 0:
            errors.append(ConfigValidationError("display_duration", "Must be positive"))
        elif dur < 5:
            errors.append(ConfigValidationError("display_duration", "Very short duration (<5s), features may not display properly", "warning"))

    # Validate log_level
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if "log_level" in config:
        if config["log_level"] not in valid_levels:
            errors.append(ConfigValidationError("log_level", f"Must be one of: {', '.join(sorted(valid_levels))}"))

    # Validate sequence
    if "sequence" not in config:
        errors.append(ConfigValidationError("sequence", "Missing required field 'sequence'"))
    elif not isinstance(config["sequence"], list):
        errors.append(ConfigValidationError("sequence", "Must be an array"))
    else:
        seen_names = set()
        enabled_count = 0

        for i, item in enumerate(config["sequence"]):
            prefix = f"sequence[{i}]"

            if not isinstance(item, dict):
                errors.append(ConfigValidationError(prefix, "Each sequence item must be an object"))
                continue

            # Check required fields
            if "name" not in item:
                errors.append(ConfigValidationError(f"{prefix}.name", "Missing required field 'name'"))
            else:
                name = item["name"]
                if not isinstance(name, str):
                    errors.append(ConfigValidationError(f"{prefix}.name", "Must be a string"))
                elif name not in VALID_FEATURE_NAMES:
                    errors.append(ConfigValidationError(f"{prefix}.name", f"Unknown feature '{name}'. Valid: {', '.join(sorted(VALID_FEATURE_NAMES))}"))
                elif name in seen_names:
                    errors.append(ConfigValidationError(f"{prefix}.name", f"Duplicate feature name '{name}'", "warning"))
                seen_names.add(name)

            if "type" not in item:
                errors.append(ConfigValidationError(f"{prefix}.type", "Missing required field 'type'"))
            elif item["type"] not in VALID_FEATURE_TYPES:
                errors.append(ConfigValidationError(f"{prefix}.type", f"Unknown type '{item['type']}'. Valid: {', '.join(sorted(VALID_FEATURE_TYPES))}"))

            if "enabled" not in item:
                errors.append(ConfigValidationError(f"{prefix}.enabled", "Missing required field 'enabled'"))
            elif not isinstance(item["enabled"], bool):
                errors.append(ConfigValidationError(f"{prefix}.enabled", "Must be a boolean (true/false)"))
            elif item["enabled"]:
                enabled_count += 1

        if enabled_count == 0:
            errors.append(ConfigValidationError("sequence", "No features are enabled. At least one feature must be enabled.", "warning"))

    return errors


def validate_wifi_config(config_path=None):
    """
    Validate config/wifi.json.

    Args:
        config_path: Path to wifi.json. Defaults to config/wifi.json.

    Returns:
        List of ConfigValidationError objects. Empty list means valid.
    """
    if config_path is None:
        config_path = os.path.join(PROJECT_ROOT, "config", "wifi.json")

    errors = []

    if not os.path.exists(config_path):
        errors.append(ConfigValidationError("file", f"WiFi config not found: {config_path}"))
        return errors

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(ConfigValidationError("json", f"Invalid JSON: {e}"))
        return errors

    if not isinstance(config, dict):
        errors.append(ConfigValidationError("root", "WiFi config must be a JSON object"))
        return errors

    # Validate networks array
    if "networks" not in config:
        errors.append(ConfigValidationError("networks", "Missing required field 'networks'"))
    elif not isinstance(config["networks"], list):
        errors.append(ConfigValidationError("networks", "Must be an array"))
    else:
        if len(config["networks"]) == 0:
            errors.append(ConfigValidationError("networks", "No WiFi networks configured", "warning"))

        for i, net in enumerate(config["networks"]):
            prefix = f"networks[{i}]"

            if not isinstance(net, dict):
                errors.append(ConfigValidationError(prefix, "Each network must be an object"))
                continue

            if "ssid" not in net:
                errors.append(ConfigValidationError(f"{prefix}.ssid", "Missing required field 'ssid'"))
            elif not isinstance(net["ssid"], str):
                errors.append(ConfigValidationError(f"{prefix}.ssid", "Must be a string"))
            elif not net["ssid"].strip():
                errors.append(ConfigValidationError(f"{prefix}.ssid", "SSID must not be empty"))
            elif net["ssid"] == "YOUR_WIFI_SSID":
                errors.append(ConfigValidationError(f"{prefix}.ssid", "WiFi SSID has not been configured (still using placeholder)", "warning"))

            if "password" in net and not isinstance(net["password"], str):
                errors.append(ConfigValidationError(f"{prefix}.password", "Must be a string"))

            if "priority" in net:
                if not isinstance(net["priority"], int):
                    errors.append(ConfigValidationError(f"{prefix}.priority", "Must be an integer"))
                elif net["priority"] < 0:
                    errors.append(ConfigValidationError(f"{prefix}.priority", "Must be non-negative"))

            if "hidden" in net and not isinstance(net["hidden"], bool):
                errors.append(ConfigValidationError(f"{prefix}.hidden", "Must be a boolean"))

    # Validate numeric settings
    for key in ["connection_timeout", "retry_attempts", "retry_delay"]:
        if key in config:
            val = config[key]
            if not isinstance(val, (int, float)):
                errors.append(ConfigValidationError(key, "Must be a number"))
            elif val <= 0:
                errors.append(ConfigValidationError(key, "Must be positive"))

    # Validate connectivity check URL
    if "connectivity_check_url" in config:
        url = config["connectivity_check_url"]
        if not isinstance(url, str):
            errors.append(ConfigValidationError("connectivity_check_url", "Must be a string"))
        elif not url.startswith("http"):
            errors.append(ConfigValidationError("connectivity_check_url", "Must be an HTTP URL"))

    return errors


def validate_all():
    """
    Validate all configuration files.

    Returns:
        dict mapping config file name to list of errors.
    """
    return {
        "config.json": validate_config(),
        "wifi.json": validate_wifi_config()
    }


def main():
    """CLI entry point for config validation."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    results = validate_all()

    has_errors = False
    has_warnings = False

    for config_name, errors in results.items():
        if not errors:
            print(f"[OK] config/{config_name}")
        else:
            for err in errors:
                print(f"  config/{config_name} -> {err}")
                if err.severity == "error":
                    has_errors = True
                else:
                    has_warnings = True

    print()
    if has_errors:
        print("Validation FAILED - fix errors above before running")
        sys.exit(1)
    elif has_warnings:
        print("Validation passed with warnings")
        sys.exit(0)
    else:
        print("All configuration files are valid")
        sys.exit(0)


if __name__ == "__main__":
    main()
