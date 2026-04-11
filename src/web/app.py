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
from flask_sock import Sock

logger = logging.getLogger(__name__)


# --- Password hashing utilities ---

def _hash_password(password, salt=None):
    """Hash a password with SHA-256 + salt."""
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{hashed}"


def _verify_password(password, stored_hash):
    """Verify a password against a stored hash. Also accepts plaintext for migration."""
    if ':' in stored_hash and len(stored_hash) > 40:
        # Hashed format: salt:hash
        salt = stored_hash.split(':')[0]
        return _hash_password(password, salt) == stored_hash
    else:
        # Plaintext (legacy) - verify directly
        return password == stored_hash


# --- Rate limiting for login attempts ---

_login_attempts = {}  # IP -> (count, last_attempt_time)
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5 minutes


def _check_rate_limit(ip):
    """Check if IP is rate limited. Returns (allowed, message)."""
    now = time.time()
    if ip in _login_attempts:
        count, last_time = _login_attempts[ip]
        # Reset if lockout period passed
        if now - last_time > LOCKOUT_SECONDS:
            del _login_attempts[ip]
            return True, ""
        if count >= MAX_LOGIN_ATTEMPTS:
            remaining = int(LOCKOUT_SECONDS - (now - last_time))
            return False, f"Too many failed attempts. Try again in {remaining}s."
    return True, ""


def _record_failed_login(ip):
    """Record a failed login attempt."""
    now = time.time()
    if ip in _login_attempts:
        count, _ = _login_attempts[ip]
        _login_attempts[ip] = (count + 1, now)
    else:
        _login_attempts[ip] = (1, now)


def _clear_login_attempts(ip):
    """Clear failed attempts on successful login."""
    _login_attempts.pop(ip, None)


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
COUNTDOWN_PATH = os.path.join(PROJECT_ROOT, "config", "countdown.json")
QR_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "qr.json")
WEATHER_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "weather.json")
SCHEDULE_PATH = os.path.join(PROJECT_ROOT, "config", "schedule.json")
WIREFRAME_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "wireframe.json")
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


def save_web_config(config):
    """Save web server configuration."""
    try:
        with open(WEB_CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        logger.error("Failed to save web config: %s", e)
        return False


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


def load_countdown():
    """Load countdown timer configuration."""
    try:
        with open(COUNTDOWN_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"label": "Timer", "seconds": 300}


def save_countdown(data):
    """Save countdown timer configuration."""
    try:
        with open(COUNTDOWN_PATH, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False


def load_weather_config():
    """Load weather location configuration."""
    try:
        with open(WEATHER_CONFIG_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"lat": 30.27, "lon": -97.74, "city": "Austin, TX"}


def save_weather_config(data):
    """Save weather location configuration."""
    try:
        with open(WEATHER_CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False


def load_qr_config():
    """Load QR code configuration."""
    try:
        with open(QR_CONFIG_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"content": "https://github.com/RynAgain/LED_MATRIX-Project", "label": "Scan Me"}


def save_qr_config(data):
    """Save QR code configuration."""
    try:
        with open(QR_CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False


def load_schedule():
    try:
        with open(SCHEDULE_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"enabled": False, "night_mode": {"enabled": False, "start_hour": 22, "end_hour": 7, "brightness": 20}}

def save_schedule(data):
    try:
        with open(SCHEDULE_PATH, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False


def load_wireframe_config():
    """Load wireframe shape configuration."""
    defaults = {
        "shapes": {
            "cube": True, "tetrahedron": True, "octahedron": True,
            "icosahedron": True, "diamond": True, "pyramid": True,
            "star": True, "torus": True,
        },
        "seconds_per_shape": 10,
        "rotation_speed": 1.0,
    }
    try:
        with open(WIREFRAME_CONFIG_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return defaults

def save_wireframe_config(data):
    """Save wireframe shape configuration."""
    try:
        with open(WIREFRAME_CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
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


def _get_system_stats():
    """Collect system resource stats using psutil.

    Returns a dict with cpu_percent, ram_percent, disk_percent,
    cpu_temp, and uptime. Gracefully handles missing psutil or
    unavailable sensors.
    """
    stats = {
        "cpu_percent": 0.0,
        "ram_percent": 0.0,
        "disk_percent": 0.0,
        "cpu_temp": None,
        "uptime": "N/A",
    }

    try:
        import psutil
    except ImportError:
        logger.warning("psutil not installed -- system stats unavailable")
        return stats

    try:
        stats["cpu_percent"] = psutil.cpu_percent(interval=0)
    except Exception:
        pass

    try:
        stats["ram_percent"] = psutil.virtual_memory().percent
    except Exception:
        pass

    try:
        stats["disk_percent"] = psutil.disk_usage('/').percent
    except Exception:
        pass

    # CPU temperature
    try:
        if hasattr(psutil, 'sensors_temperatures'):
            temps = psutil.sensors_temperatures()
            if temps:
                for name in ('coretemp', 'cpu_thermal', 'cpu-thermal',
                             'soc_thermal', 'k10temp', 'zenpower'):
                    if name in temps and temps[name]:
                        stats["cpu_temp"] = round(temps[name][0].current, 1)
                        break
                if stats["cpu_temp"] is None:
                    for sensor_list in temps.values():
                        if sensor_list:
                            stats["cpu_temp"] = round(sensor_list[0].current, 1)
                            break
    except Exception:
        pass

    # Raspberry Pi thermal zone fallback
    if stats["cpu_temp"] is None:
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                stats["cpu_temp"] = round(int(f.read().strip()) / 1000.0, 1)
        except (FileNotFoundError, ValueError, OSError):
            pass

    # System uptime
    try:
        boot_time = psutil.boot_time()
        uptime_secs = time.time() - boot_time
        days = int(uptime_secs // 86400)
        hours = int((uptime_secs % 86400) // 3600)
        minutes = int((uptime_secs % 3600) // 60)
        if days > 0:
            stats["uptime"] = f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            stats["uptime"] = f"{hours}h {minutes}m"
        else:
            stats["uptime"] = f"{minutes}m"
    except Exception:
        pass

    return stats


def _generate_self_signed_cert(cert_path, key_path):
    """Generate a self-signed certificate for HTTPS."""
    try:
        import subprocess
        # Use OpenSSL if available (common on Raspberry Pi)
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", key_path, "-out", cert_path,
            "-days", "365", "-nodes",
            "-subj", "/CN=ledmatrix/O=LED Matrix/C=US"
        ], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback: try Python's cryptography package
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            import datetime

            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, "ledmatrix"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "LED Matrix"),
            ])
            cert = (x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.datetime.utcnow())
                .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
                .sign(key, hashes.SHA256()))

            with open(key_path, "wb") as f:
                f.write(key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.TraditionalOpenSSL,
                    serialization.NoEncryption()))
            with open(cert_path, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            return True
        except ImportError:
            return False


def _get_status_data():
    """Gather current status data for API/WebSocket responses.

    Combines display status and system stats into a single dict.
    """
    status = get_display_status()
    status["system"] = _get_system_stats()
    return status


def create_app():
    """Create and configure the Flask application."""
    web_config = load_web_config()

    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static")
    )

    sock = Sock(app)

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
            ip = request.remote_addr

            # Check rate limit
            allowed, msg = _check_rate_limit(ip)
            if not allowed:
                flash(msg, "error")
                return render_template("login.html")

            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            if username in users and _verify_password(password, users[username]):
                session.permanent = True
                session["user"] = username
                _clear_login_attempts(ip)
                logger.info("User '%s' logged in from %s", username, ip)
                return redirect(url_for("dashboard"))
            else:
                _record_failed_login(ip)
                flash("Invalid username or password", "error")
                logger.warning("Failed login attempt for '%s' from %s", username, ip)

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

                # Per-feature duration
                dur_key = f"duration_{feature['name']}"
                dur_val = request.form.get(dur_key, "").strip()
                if dur_val:
                    try:
                        feature["duration"] = int(dur_val)
                    except ValueError:
                        pass
                elif "duration" in feature:
                    del feature["duration"]  # Remove if cleared

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
            section = request.form.get("section")
            if section == "weather":
                try:
                    lat = float(request.form.get("lat", 30.27))
                    lon = float(request.form.get("lon", -97.74))
                    save_weather_config({"lat": lat, "lon": lon})
                    flash("Weather location saved", "success")
                except ValueError:
                    flash("Invalid coordinates", "error")
                return redirect(url_for("settings"))

            elif section == "schedule":
                sched = load_schedule()
                sched["enabled"] = True
                sched["night_mode"] = {
                    "enabled": "night_enabled" in request.form,
                    "start_hour": int(request.form.get("night_start", 22)),
                    "end_hour": int(request.form.get("night_end", 7)),
                    "brightness": int(request.form.get("night_brightness", 20)),
                    "allowed_features": ["time_display", "binary_clock"]
                }

                # Feature schedules (new)
                schedules = []
                count = int(request.form.get("schedule_count", 0))
                for i in range(min(count, 5)):  # Cap at 5
                    name = request.form.get(f"sched_{i}_name", "").strip()
                    if not name:
                        continue
                    start = int(request.form.get(f"sched_{i}_start", 0))
                    end = int(request.form.get(f"sched_{i}_end", 0))
                    brightness_val = request.form.get(f"sched_{i}_brightness", "")
                    brightness = int(brightness_val) if brightness_val else None
                    features = request.form.getlist(f"sched_{i}_features")
                    if features:
                        schedules.append({
                            "name": name[:30],
                            "start_hour": max(0, min(23, start)),
                            "end_hour": max(0, min(23, end)),
                            "allowed_features": features,
                            "brightness": brightness
                        })
                sched["schedules"] = schedules

                save_schedule(sched)
                flash("Schedule settings saved", "success")
                return redirect(url_for("settings"))

            elif section == "https":
                web_config = load_web_config()
                https_conf = web_config.get("https", {})
                https_conf["enabled"] = "https_enabled" in request.form
                web_config["https"] = https_conf
                save_web_config(web_config)
                flash("HTTPS settings saved. Restart the web service to apply.", "success")
                return redirect(url_for("settings"))

            elif section == "schedule_delete":
                idx = int(request.form.get("index", -1))
                sched = load_schedule()
                schedules = sched.get("schedules", [])
                if 0 <= idx < len(schedules):
                    removed = schedules.pop(idx)
                    sched["schedules"] = schedules
                    save_schedule(sched)
                    flash(f"Removed schedule: {removed.get('name', '')}", "success")
                return redirect(url_for("settings"))

            config["github_branch"] = request.form.get("github_branch", "main").strip()
            config["log_level"] = request.form.get("log_level", "INFO")
            save_display_config(config)
            flash("Settings saved", "success")
            return redirect(url_for("settings"))

        weather_config = load_weather_config()
        schedule_config = load_schedule()
        web_config = load_web_config()
        https_config = web_config.get("https", {})
        feature_list = config.get("sequence", [])
        return render_template("settings.html", config=config, weather_config=weather_config, schedule_config=schedule_config, feature_list=feature_list, https_config=https_config, user=session.get("user"))

    @app.route("/api/status")
    @login_required
    def api_status():
        """API endpoint for live status updates."""
        return jsonify(_get_status_data())

    @app.route("/api/system-stats")
    @login_required
    def api_system_stats():
        """API endpoint for system resource monitoring (CPU, RAM, disk, temp, uptime)."""
        stats = _get_system_stats()
        return jsonify(stats)

    @sock.route("/ws/status")
    def ws_status(ws):
        """WebSocket endpoint for real-time status updates."""
        import time as time_mod
        while True:
            try:
                status_data = _get_status_data()
                ws.send(json.dumps(status_data))
                time_mod.sleep(2)
            except Exception:
                break  # Client disconnected

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

    @app.route("/api/brightness", methods=["POST"])
    @login_required
    def api_brightness():
        """Set display brightness."""
        data = request.get_json()
        if not data or "brightness" not in data:
            return jsonify({"success": False, "message": "Missing 'brightness'"})

        brightness = max(10, min(100, int(data["brightness"])))
        success = send_command("set_brightness", {"brightness": brightness})
        if success:
            return jsonify({"success": True, "message": f"Brightness set to {brightness}%"})
        return jsonify({"success": False, "message": "Failed to send command"})

    @app.route("/countdown", methods=["GET", "POST"])
    @login_required
    def countdown_page():
        config = load_countdown()
        if request.method == "POST":
            label = request.form.get("label", "Timer").strip()[:10]
            hours = int(request.form.get("hours", 0))
            minutes = int(request.form.get("minutes", 5))
            secs = int(request.form.get("secs", 0))
            total = hours * 3600 + minutes * 60 + secs
            save_countdown({"label": label, "seconds": total})
            send_command("play_feature", {"feature": "countdown"})
            flash(f"Countdown started: {label}", "success")
            return redirect(url_for("countdown_page"))
        return render_template("countdown.html", config=config, user=session.get("user"))

    @app.route("/api/countdown", methods=["POST"])
    @login_required
    def api_countdown():
        data = request.get_json()
        if not data:
            return jsonify({"success": False})
        seconds = data.get("seconds", 300)
        label = data.get("label", "Timer")
        save_countdown({"label": label, "seconds": seconds})
        send_command("play_feature", {"feature": "countdown"})
        return jsonify({"success": True, "message": f"Countdown: {label}"})

    @app.route("/qr", methods=["GET", "POST"])
    @login_required
    def qr_page():
        config = load_qr_config()
        if request.method == "POST":
            content = request.form.get("content", "").strip()
            label = request.form.get("label", "").strip()[:10]
            if content:
                save_qr_config({"content": content, "label": label})
                send_command("play_feature", {"feature": "qr_code"})
                flash("QR code displayed", "success")
            return redirect(url_for("qr_page"))
        return render_template("qr.html", config=config, user=session.get("user"))

    @app.route("/api/qr", methods=["POST"])
    @login_required
    def api_qr():
        data = request.get_json()
        if not data or "content" not in data:
            return jsonify({"success": False})
        save_qr_config({"content": data["content"], "label": data.get("label", "")})
        send_command("play_feature", {"feature": "qr_code"})
        return jsonify({"success": True, "message": "QR code displayed"})

    @app.route("/wireframe", methods=["GET", "POST"])
    @login_required
    def wireframe_page():
        """Wireframe polygon configuration page."""
        cfg = load_wireframe_config()
        shape_names = ["cube", "tetrahedron", "octahedron", "icosahedron",
                       "diamond", "pyramid", "star", "torus"]

        if request.method == "POST":
            shapes = {}
            for s in shape_names:
                shapes[s] = request.form.get(f"shape_{s}") == "on"
            cfg["shapes"] = shapes
            cfg["seconds_per_shape"] = max(3, int(request.form.get("seconds_per_shape", 10)))
            cfg["rotation_speed"] = max(0.1, min(5.0, float(request.form.get("rotation_speed", 1.0))))
            save_wireframe_config(cfg)
            signal_display_reload()
            flash("Wireframe settings saved", "success")
            return redirect(url_for("wireframe_page"))

        return render_template("wireframe.html", config=cfg,
                               shape_names=shape_names, user=session.get("user"))

    @app.route("/api/reorder-features", methods=["POST"])
    @login_required
    def api_reorder_features():
        """Reorder features in the display sequence."""
        try:
            data = request.get_json()
            new_order = data.get("order", [])
            if not new_order:
                return jsonify({"success": False, "error": "No order provided"})

            config = load_display_config()
            sequence = config.get("sequence", [])

            # Build lookup by name
            feature_map = {f["name"]: f for f in sequence}

            # Rebuild sequence in new order, preserving all feature data
            reordered = []
            for name in new_order:
                if name in feature_map:
                    reordered.append(feature_map[name])
                    del feature_map[name]

            # Append any features not in the new order list (safety)
            for remaining in feature_map.values():
                reordered.append(remaining)

            config["sequence"] = reordered
            save_display_config(config)

            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/preview")
    @login_required
    def api_preview():
        """Get a base64 PNG of the current matrix display."""
        try:
            import src.main as main_module
            matrix = getattr(main_module, '_matrix_ref', None)
            if matrix and hasattr(matrix, 'get_frame_base64'):
                data = matrix.get_frame_base64()
                return jsonify({"success": True, "image": data})
        except Exception as e:
            logger.debug("Preview failed: %s", e)
        return jsonify({"success": False, "message": "Preview not available"})

    # --- Living World routes ---

    @app.route("/living-world")
    @login_required
    def living_world():
        """Living World viewer with minimap, villager inspector, and controls."""
        return render_template("living_world.html", user=session.get("user"))

    @app.route("/api/living-world/state")
    @login_required
    def api_living_world_state():
        """API: get current living world snapshot for the minimap."""
        try:
            from src.display.living_world.world_api import get_world_snapshot
            snapshot = get_world_snapshot()
            if snapshot is not None:
                return jsonify({"success": True, "data": snapshot})
            return jsonify({"success": False, "message": "No world state available"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/api/living-world/events")
    @login_required
    def api_living_world_events():
        """API: get recent event log entries."""
        try:
            count = int(request.args.get("count", 100))
            category = request.args.get("category")
            if category == "":
                category = None
            from src.display.living_world.world_api import get_event_log_snapshot
            events = get_event_log_snapshot(count=count, category=category)
            return jsonify({"success": True, "events": events})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/api/living-world/command", methods=["POST"])
    @login_required
    def api_living_world_command():
        """API: send a command directly to the living world simulation.

        Uses a separate command file to avoid triggering the main display
        loop's request_stop() mechanism, which would reset the simulation.
        """
        data = request.get_json()
        if not data or "action" not in data:
            return jsonify({"success": False, "message": "Missing 'action'"})
        action = data["action"]
        params = data.get("params", {})
        # Write to a separate file that the living world sim reads directly
        lw_cmd_path = os.path.join(PROJECT_ROOT, "logs", "living_world_command.json")
        try:
            os.makedirs(os.path.dirname(lw_cmd_path), exist_ok=True)
            cmd = {"action": action, "params": params, "timestamp": time.time()}
            with open(lw_cmd_path, "w") as f:
                json.dump(cmd, f)
            logger.info("Living world command written: %s", action)
            return jsonify({"success": True, "message": f"Command sent: {action}"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/pixel-editor")
    @login_required
    def pixel_editor():
        return render_template("pixel_editor.html", user=session.get("user"))

    @app.route("/api/pixel-art", methods=["POST"])
    @login_required
    def api_pixel_art():
        """Send pixel art directly to the matrix."""
        data = request.get_json()
        if not data or "pixels" not in data:
            return jsonify({"success": False})
        
        # Save pixel data as a command
        pixel_path = os.path.join(PROJECT_ROOT, "logs", "pixel_art.json")
        try:
            with open(pixel_path, "w") as f:
                json.dump({"pixels": data["pixels"]}, f)
            send_command("show_pixel_art", {})
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/api/save-pixel-art", methods=["POST"])
    @login_required
    def api_save_pixel_art():
        """Save pixel art as an image file for the slideshow."""
        data = request.get_json()
        if not data or "pixels" not in data:
            return jsonify({"success": False})
        
        try:
            from PIL import Image as PILImage
            img = PILImage.new("RGB", (64, 64))
            img_pixels = img.load()
            for y in range(64):
                for x in range(64):
                    if y < len(data["pixels"]) and x < len(data["pixels"][y]):
                        c = data["pixels"][y][x]
                        img_pixels[x, y] = (c[0], c[1], c[2])
            
            images_dir = os.path.join(PROJECT_ROOT, "config", "images")
            os.makedirs(images_dir, exist_ok=True)
            
            import datetime
            fname = f"pixel_art_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            img.save(os.path.join(images_dir, fname))
            return jsonify({"success": True, "filename": fname})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/change-password", methods=["GET", "POST"])
    @login_required
    def change_password():
        if request.method == "POST":
            current = request.form.get("current_password", "")
            new_pass = request.form.get("new_password", "")
            confirm = request.form.get("confirm_password", "")

            username = session.get("user")
            if not username or username not in users:
                flash("Invalid session", "error")
                return redirect(url_for("login"))

            if not _verify_password(current, users[username]):
                flash("Current password is incorrect", "error")
                return redirect(url_for("change_password"))

            if len(new_pass) < 4:
                flash("Password must be at least 4 characters", "error")
                return redirect(url_for("change_password"))

            if new_pass != confirm:
                flash("New passwords don't match", "error")
                return redirect(url_for("change_password"))

            # Hash and save
            hashed = _hash_password(new_pass)
            web_config = load_web_config()
            web_config["users"][username] = hashed
            try:
                with open(WEB_CONFIG_PATH, "w") as f:
                    json.dump(web_config, f, indent=2)
                # Update in-memory users dict
                users[username] = hashed
                flash("Password changed successfully", "success")
                logger.info("Password changed for user '%s'", username)
            except Exception as e:
                flash("Failed to save password", "error")
                logger.error("Failed to save password: %s", e)

            return redirect(url_for("settings"))

        return render_template("change_password.html", user=session.get("user"))

    @app.route("/logs")
    @login_required
    def logs_page():
        return render_template("logs.html", user=session.get("user"))

    @app.route("/api/logs")
    @login_required
    def api_logs():
        """Return recent log lines as JSON for the logs viewer.

        Query params:
            file: 'display' (default) or 'updater'
            lines: number of lines to return (default 200, max 2000)
            filter: optional text filter (case-insensitive substring match)
        """
        log_file = request.args.get("file", "display")
        num_lines = min(int(request.args.get("lines", 200)), 2000)
        text_filter = request.args.get("filter", "").strip().lower()

        # Map log file names to actual paths
        log_files = {
            "display": os.path.join(PROJECT_ROOT, "logs", "display.log"),
            "updater": os.path.join(PROJECT_ROOT, "logs", "updater.log"),
        }

        log_path = log_files.get(log_file)
        if not log_path or not os.path.exists(log_path):
            return jsonify({"lines": [], "file": log_file, "error": "Log file not found"})

        try:
            # Read last N lines efficiently (read from end)
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()

            # Take last N lines
            recent = all_lines[-num_lines:] if len(all_lines) > num_lines else all_lines

            # Apply filter if specified
            if text_filter:
                recent = [l for l in recent if text_filter in l.lower()]

            # Strip trailing newlines
            recent = [l.rstrip("\n\r") for l in recent]

            return jsonify({
                "lines": recent,
                "file": log_file,
                "total_lines": len(all_lines),
                "showing": len(recent),
            })
        except Exception as e:
            return jsonify({"lines": [], "file": log_file, "error": str(e)})

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
    host = web_config.get("host", "0.0.0.0")
    port = web_config.get("port", 5000)

    # Kill any stale processes on our port
    _kill_existing_on_port(port)

    app = create_app()

    # HTTPS / TLS support
    https_config = web_config.get("https", {})
    ssl_context = None

    if https_config.get("enabled", False):
        cert_path = https_config.get("cert_path", "config/cert.pem")
        key_path = https_config.get("key_path", "config/key.pem")

        # Resolve relative paths against project root
        if not os.path.isabs(cert_path):
            cert_path = os.path.join(PROJECT_ROOT, cert_path)
        if not os.path.isabs(key_path):
            key_path = os.path.join(PROJECT_ROOT, key_path)

        # Auto-generate self-signed cert if files don't exist
        if https_config.get("auto_generate", True):
            if not (os.path.exists(cert_path) and os.path.exists(key_path)):
                logger.info("Generating self-signed certificate...")
                if _generate_self_signed_cert(cert_path, key_path):
                    logger.info("Certificate generated successfully")
                else:
                    logger.warning("Failed to generate certificate, falling back to HTTP")

        if os.path.exists(cert_path) and os.path.exists(key_path):
            ssl_context = (cert_path, key_path)
            logger.info("HTTPS enabled with cert=%s key=%s", cert_path, key_path)
        else:
            logger.warning("HTTPS enabled but certificates not found, using HTTP")

    protocol = "https" if ssl_context else "http"
    logger.info("Starting LED Matrix Web Control Panel on %s://%s:%d", protocol, host, port)

    app.run(
        host=host,
        port=port,
        debug=False,
        ssl_context=ssl_context
    )


if __name__ == "__main__":
    main()
