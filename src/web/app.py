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
CSV_PATH = os.path.join(PROJECT_ROOT, "config", "youtube_urls.csv")
COMMAND_PATH = os.path.join(PROJECT_ROOT, "logs", "command.json")
WIFI_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "wifi.json")
MESSAGES_PATH = os.path.join(PROJECT_ROOT, "config", "messages.json")
STOCKS_PATH = os.path.join(PROJECT_ROOT, "config", "stocks.json")
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


def load_messages():
    """Load scroller messages."""
    try:
        with open(MESSAGES_PATH, "r") as f:
            data = json.load(f)
        return data.get("messages", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return ["Welcome to LED Matrix!", "Hello World!"]


def save_messages(messages):
    """Save scroller messages."""
    try:
        with open(MESSAGES_PATH, "w") as f:
            json.dump({"messages": messages}, f, indent=2)
        return True
    except Exception as e:
        logger.error("Failed to save messages: %s", e)
        return False


def load_stocks():
    """Load stock symbols."""
    try:
        with open(STOCKS_PATH, "r") as f:
            data = json.load(f)
        return data.get("symbols", ["AMZN"])
    except (FileNotFoundError, json.JSONDecodeError):
        return ["AMZN"]


def save_stocks(symbols):
    """Save stock symbols."""
    try:
        with open(STOCKS_PATH, "w") as f:
            json.dump({"symbols": symbols}, f, indent=2)
        return True
    except Exception as e:
        logger.error("Failed to save stocks: %s", e)
        return False


import csv


def load_youtube_playlist():
    """Load YouTube video playlist from CSV."""
    videos = []
    try:
        with open(CSV_PATH, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                videos.append({
                    "url": row.get("url", ""),
                    "title": row.get("title", "Unknown"),
                    "duration": row.get("duration", "x")
                })
    except FileNotFoundError:
        pass
    return videos


def save_youtube_playlist(videos):
    """Save YouTube video playlist to CSV."""
    try:
        with open(CSV_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["url", "title", "duration"])
            writer.writeheader()
            for v in videos:
                writer.writerow(v)
        return True
    except Exception as e:
        logger.error("Failed to save playlist: %s", e)
        return False


def send_command(command_type, data=None):
    """Write a command for the display service to pick up."""
    try:
        os.makedirs(os.path.dirname(COMMAND_PATH), exist_ok=True)
        cmd = {
            "command": command_type,
            "data": data or {},
            "timestamp": time.time()
        }
        with open(COMMAND_PATH, "w") as f:
            json.dump(cmd, f)
        return True
    except Exception as e:
        logger.error("Failed to send command: %s", e)
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

    @app.route("/youtube", methods=["GET", "POST"])
    @login_required
    def youtube():
        """YouTube playlist management page."""
        videos = load_youtube_playlist()

        if request.method == "POST":
            action = request.form.get("action")

            if action == "add":
                url = request.form.get("url", "").strip()
                title = request.form.get("title", "").strip()
                dur = request.form.get("duration", "x").strip()
                if url and title:
                    videos.append({"url": url, "title": title, "duration": dur})
                    save_youtube_playlist(videos)
                    flash(f"Added '{title}' to playlist", "success")

            elif action == "remove":
                idx = int(request.form.get("index", -1))
                if 0 <= idx < len(videos):
                    removed = videos.pop(idx)
                    save_youtube_playlist(videos)
                    flash(f"Removed '{removed.get('title', '')}' from playlist", "success")

            return redirect(url_for("youtube"))

        return render_template("youtube.html", videos=videos, user=session.get("user"))

    @app.route("/api/play", methods=["POST"])
    @login_required
    def api_play_video():
        """Command the display to play a specific YouTube video immediately."""
        data = request.get_json()
        if not data or "url" not in data:
            return jsonify({"success": False, "message": "Missing 'url' in request"})

        url = data["url"]
        title = data.get("title", "Unknown")

        success = send_command("play_video", {"url": url, "title": title})
        if success:
            logger.info("Play command sent: %s (%s)", title, url)
            return jsonify({"success": True, "message": f"Playing: {title}"})
        else:
            return jsonify({"success": False, "message": "Failed to send command"})

    @app.route("/api/play_feature", methods=["POST"])
    @login_required
    def api_play_feature():
        """Command the display to switch to a specific feature immediately."""
        data = request.get_json()
        if not data or "feature" not in data:
            return jsonify({"success": False, "message": "Missing 'feature' in request"})

        feature = data["feature"]
        success = send_command("play_feature", {"feature": feature})
        if success:
            logger.info("Feature switch command sent: %s", feature)
            return jsonify({"success": True, "message": f"Switching to: {feature}"})
        else:
            return jsonify({"success": False, "message": "Failed to send command"})

    @app.route("/messages", methods=["GET", "POST"])
    @login_required
    def messages():
        """Text scroller message management page."""
        msgs = load_messages()

        if request.method == "POST":
            action = request.form.get("action")

            if action == "add":
                text = request.form.get("message", "").strip()
                if text:
                    msgs.append(text)
                    save_messages(msgs)
                    flash(f"Message added", "success")

            elif action == "remove":
                idx = int(request.form.get("index", -1))
                if 0 <= idx < len(msgs):
                    removed = msgs.pop(idx)
                    save_messages(msgs)
                    flash(f"Message removed", "success")

            elif action == "play":
                text = request.form.get("message", "").strip()
                if text:
                    # Send as a command to display immediately
                    send_command("play_feature", {"feature": "text_scroller"})
                    flash(f"Text scroller activated", "success")

            return redirect(url_for("messages"))

        return render_template("messages.html", messages=msgs, user=session.get("user"))

    @app.route("/stocks", methods=["GET", "POST"])
    @login_required
    def stocks():
        """Stock ticker management page."""
        symbols = load_stocks()

        if request.method == "POST":
            action = request.form.get("action")

            if action == "add":
                symbol = request.form.get("symbol", "").strip().upper()
                if symbol and symbol not in symbols:
                    symbols.append(symbol)
                    save_stocks(symbols)
                    flash(f"Added {symbol}", "success")
                elif symbol in symbols:
                    flash(f"{symbol} already tracked", "error")

            elif action == "remove":
                idx = int(request.form.get("index", -1))
                if 0 <= idx < len(symbols):
                    removed = symbols.pop(idx)
                    save_stocks(symbols)
                    flash(f"Removed {removed}", "success")

            elif action == "play":
                send_command("play_feature", {"feature": "stock_ticker"})
                flash("Stock ticker activated", "success")

            return redirect(url_for("stocks"))

        return render_template("stocks.html", symbols=symbols, user=session.get("user"))

    return app


def _kill_existing_on_port(port):
    """Kill any existing process on the given port (Windows only)."""
    if sys.platform != "win32":
        return
    try:
        import subprocess
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5
        )
        pids = set()
        for line in result.stdout.strip().split("\n"):
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    try:
                        pid = int(parts[-1])
                        if pid != os.getpid():
                            pids.add(pid)
                    except ValueError:
                        pass
        for pid in pids:
            logger.info("Killing existing process on port %d (PID %d)", port, pid)
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                             capture_output=True, timeout=5)
            except Exception:
                pass
        if pids:
            import time as _time
            _time.sleep(1)
    except Exception as e:
        logger.debug("Port cleanup skipped: %s", e)


def main():
    """Run the web server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    web_config = load_web_config()
    port = web_config.get("port", 5000)

    # Kill any stale processes on our port
    _kill_existing_on_port(port)

    app = create_app()

    logger.info("Starting LED Matrix Web Control Panel on %s:%d",
                web_config.get("host", "0.0.0.0"), port)

    app.run(
        host=web_config.get("host", "0.0.0.0"),
        port=port,
        debug=False
    )


if __name__ == "__main__":
    main()
