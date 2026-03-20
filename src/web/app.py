#!/usr/bin/env python3
"""
LED Matrix Web Control Panel - Flask Application.
Provides a mobile-friendly web interface for controlling the LED matrix display.
"""

import json
import os
import sys
import signal
import logging
import time
import hashlib
import secrets
from functools import wraps
from datetime import timedelta

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify
)

logger = logging.getLogger(__name__)

# Project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Paths
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.json")
WEB_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "web.json")
WIFI_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "wifi.json")
STATUS_PATH = os.path.join(PROJECT_ROOT, "logs", "status.json")
PID_PATH = os.path.join(PROJECT_ROOT, "logs", "display.pid")


def load_web_config():
    """Load web server configuration."""
    try:
        with open(WEB_CONFIG_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "host": "0.0.0.0",
            "port": 5000,
            "secret_key": secrets.token_hex(32),
            "users": {"admin": "ledmatrix"},
            "session_timeout_minutes": 60
        }


def load_display_config():
    """Load the display configuration."""
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("Failed to load display config: %s", e)
        return {"sequence": [], "display_duration": 60, "github_branch": "main", "log_level": "INFO"}


def save_display_config(config):
    """Save the display configuration."""
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        logger.error("Failed to save display config: %s", e)
        return False


def load_wifi_config():
    """Load WiFi configuration."""
    try:
        with open(WIFI_CONFIG_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"networks": []}


def save_wifi_config(config):
    """Save WiFi configuration."""
    try:
        with open(WIFI_CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        logger.error("Failed to save wifi config: %s", e)
        return False


def get_display_status():
    """Read the current display service status."""
    try:
        if os.path.exists(STATUS_PATH):
            # Only use status if it's recent (within last 30 seconds)
            mtime = os.path.getmtime(STATUS_PATH)
            if time.time() - mtime < 30:
                with open(STATUS_PATH, "r") as f:
                    return json.load(f)
        return {"status": "unknown", "current_feature": None, "message": "Status not available"}
    except (json.JSONDecodeError, OSError):
        return {"status": "unknown", "current_feature": None, "message": "Status file error"}


def get_display_pid():
    """Get the PID of the display service."""
    try:
        if os.path.exists(PID_PATH):
            with open(PID_PATH, "r") as f:
                return int(f.read().strip())
    except (ValueError, OSError):
        pass
    return None


def signal_display_reload():
    """Send SIGHUP to the display service to reload config."""
    pid = get_display_pid()
    if pid and hasattr(signal, "SIGHUP"):
        try:
            os.kill(pid, signal.SIGHUP)
            return True
        except (OSError, ProcessLookupError):
            pass
    # Fallback: try systemctl
    try:
        import subprocess
        subprocess.run(
            ["sudo", "systemctl", "reload", "led-matrix.service"],
            capture_output=True, timeout=5
        )
        return True
    except Exception:
        pass
    return False


def create_app():
    """Create and configure the Flask application."""
    web_config = load_web_config()

    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static")
    )

    app.secret_key = web_config.get("secret_key", secrets.token_hex(32))
    app.permanent_session_lifetime = timedelta(
        minutes=web_config.get("session_timeout_minutes", 60)
    )

    users = web_config.get("users", {"admin": "ledmatrix"})

    # --- Auth decorator ---
    def login_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return decorated

    # --- Routes ---

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            if username in users and users[username] == password:
                session.permanent = True
                session["user"] = username
                logger.info("User '%s' logged in from %s", username, request.remote_addr)
                return redirect(url_for("dashboard"))
            else:
                flash("Invalid username or password", "error")
                logger.warning("Failed login attempt for '%s' from %s", username, request.remote_addr)

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        user = session.pop("user", None)
        if user:
            logger.info("User '%s' logged out", user)
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def dashboard():
        config = load_display_config()
        status = get_display_status()
        return render_template("dashboard.html",
                               config=config,
                               status=status,
                               user=session.get("user"))

    @app.route("/features", methods=["GET", "POST"])
    @login_required
    def features():
        config = load_display_config()

        if request.method == "POST":
            # Update feature enabled states
            sequence = config.get("sequence", [])
            for feature in sequence:
                key = f"feature_{feature['name']}"
                feature["enabled"] = key in request.form

            # Update display duration
            try:
                duration = int(request.form.get("display_duration", 60))
                if duration > 0:
                    config["display_duration"] = duration
            except (ValueError, TypeError):
                pass

            save_display_config(config)
            flash("Features updated. Changes take effect on next cycle.", "success")

            # Try to signal the display service to reload
            signal_display_reload()

            return redirect(url_for("features"))

        return render_template("features.html", config=config, user=session.get("user"))

    @app.route("/wifi", methods=["GET", "POST"])
    @login_required
    def wifi():
        wifi_config = load_wifi_config()

        if request.method == "POST":
            action = request.form.get("action")

            if action == "add":
                ssid = request.form.get("ssid", "").strip()
                password = request.form.get("password", "")
                priority = int(request.form.get("priority", 99))
                hidden = "hidden" in request.form

                if ssid:
                    networks = wifi_config.get("networks", [])
                    networks.append({
                        "ssid": ssid,
                        "password": password,
                        "priority": priority,
                        "hidden": hidden
                    })
                    wifi_config["networks"] = networks
                    save_wifi_config(wifi_config)
                    flash(f"Network '{ssid}' added", "success")

            elif action == "remove":
                idx = int(request.form.get("index", -1))
                networks = wifi_config.get("networks", [])
                if 0 <= idx < len(networks):
                    removed = networks.pop(idx)
                    wifi_config["networks"] = networks
                    save_wifi_config(wifi_config)
                    flash(f"Network '{removed.get('ssid', '')}' removed", "success")

            return redirect(url_for("wifi"))

        return render_template("wifi.html", config=wifi_config, user=session.get("user"))

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        config = load_display_config()

        if request.method == "POST":
            config["github_branch"] = request.form.get("github_branch", "main").strip()
            config["log_level"] = request.form.get("log_level", "INFO")
            save_display_config(config)
            flash("Settings saved", "success")
            return redirect(url_for("settings"))

        return render_template("settings.html", config=config, user=session.get("user"))

    @app.route("/api/status")
    @login_required
    def api_status():
        """API endpoint for live status updates."""
        return jsonify(get_display_status())

    @app.route("/api/restart", methods=["POST"])
    @login_required
    def api_restart():
        """Restart the display service."""
        try:
            import subprocess
            result = subprocess.run(
                ["sudo", "systemctl", "restart", "led-matrix.service"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return jsonify({"success": True, "message": "Display service restarted"})
            else:
                return jsonify({"success": False, "message": result.stderr.strip()})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/api/update", methods=["POST"])
    @login_required
    def api_update():
        """Trigger an immediate update check."""
        try:
            import subprocess
            result = subprocess.run(
                ["sudo", "systemctl", "start", "led-matrix-updater.service"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return jsonify({"success": True, "message": "Update check triggered"})
            else:
                return jsonify({"success": False, "message": result.stderr.strip()})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    return app


def main():
    """Run the web server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    web_config = load_web_config()
    app = create_app()

    logger.info("Starting LED Matrix Web Control Panel on %s:%d",
                web_config.get("host", "0.0.0.0"),
                web_config.get("port", 5000))

    app.run(
        host=web_config.get("host", "0.0.0.0"),
        port=web_config.get("port", 5000),
        debug=False
    )


if __name__ == "__main__":
    main()
