# LED Matrix Project

A self-managing Raspberry Pi display system for a 64x64 RGB LED matrix. Cycles through games, utilities, and video features -- auto-updates from GitHub, connects to WiFi, and runs unattended from boot.

---

## Features

| Feature | Type | Description |
|---------|------|-------------|
| Tic Tac Toe | Game | AI vs AI on a 3x3 grid |
| Snake | Game | Autonomous AI pathfinding |
| Pong | Game | AI vs AI with increasing difficulty |
| Billiards | Game | Physics simulation with AI player |
| Time Display | Utility | Clock with gradient colors + binary clock mode |
| Bitcoin Price | Utility | Live BTC/USD from CoinDesk API |
| YouTube Stream | Video | Streams from playlist, resized to 64x64 |

### Web Control Panel

A password-protected web interface accessible from any device (phone, tablet, laptop) on the same network:

- **Dashboard**: Live display status, current feature, uptime, quick restart/update actions
- **Features**: Toggle features on/off with iOS-style switches, set display duration
- **WiFi**: Add/remove WiFi networks, set priorities
- **Settings**: Configure GitHub branch, log level
- **Authentication**: Username/password login with session timeout

Default credentials: `admin` / `ledmatrix` (change in `config/web.json`)

## Architecture

```
LED_MATRIX-Project/
  config/              # All configuration files
    config.json        # Feature sequence, update interval, display settings
    web.json           # Web control panel settings and credentials
    wifi.json          # WiFi network credentials and connection settings
    youtube_urls.csv   # YouTube playlist for the stream feature
  scripts/             # Operational scripts
    install.sh         # One-time Raspberry Pi setup
    update.sh          # Called by systemd timer to check for updates
  services/            # systemd unit files
    led-matrix.service             # Main display service
    led-matrix-updater.service     # Update check service (oneshot)
    led-matrix-updater.timer       # Triggers update checks every 30 min
    led-matrix-web.service         # Web control panel service
  src/                 # Application code
    main.py            # Entry point - config loader, feature loop, matrix init
    config_validator.py # JSON schema validation for config files
    display/           # Display feature modules
    simulator/         # Pygame LED matrix emulator (dev only)
    wifi/              # WiFi connection manager (nmcli/NetworkManager)
    updater/           # Git-based auto-updater
    web/               # Flask web control panel
      app.py           # Routes, auth, API endpoints
      templates/       # Jinja2 HTML templates
      static/          # CSS styles
  rgbmatrix/           # RGB LED matrix Cython library
  tests/               # Test suite (runs in simulator, no Pi needed)
  plans/               # Project planning documents
    FEATURES.md        # Feature tracker with checkboxes
    ARCHITECTURE.md    # System architecture documentation
  pytest.ini           # Pytest configuration
```

## Quick Start (Raspberry Pi)

### 1. Clone the repository

```bash
cd /home/pi
git clone https://github.com/RynAgain/LED_MATRIX-Project.git
cd LED_MATRIX-Project
```

### 2. Configure WiFi

Edit `config/wifi.json` with your network details:

```json
{
  "networks": [
    {
      "ssid": "YourWiFiName",
      "password": "",
      "priority": 1,
      "hidden": false
    }
  ],
  "connection_timeout": 30,
  "retry_attempts": 3,
  "retry_delay": 10
}
```

- For open/public WiFi: leave `password` as `""`
- For secured WiFi: enter the password
- Add multiple networks with different priorities (lower number = higher priority)

### 3. Run the installer

```bash
sudo bash scripts/install.sh
```

This will:
- Install system dependencies (Python 3, pip, git, NetworkManager)
- Create a Python virtual environment
- Install Python packages from `requirements.txt`
- Set up systemd services for auto-start and auto-update
- Enable services to start on boot

### 4. Reboot

```bash
sudo reboot
```

The system will:
1. Connect to WiFi on boot
2. Start the LED matrix display automatically
3. Check for GitHub updates every 30 minutes
4. Auto-restart if the display process crashes

**You should never need to touch the Pi again.**

### 5. Access the Web Control Panel

Open a browser on your phone/laptop and go to:
```
http://<pi-ip-address>:5000
```

Login with default credentials:
- Username: `admin`
- Password: `ledmatrix`

Change credentials by editing `config/web.json`.

## Configuration

### Feature Sequence (`config/config.json`)

```json
{
  "update_interval": 1800,
  "github_branch": "main",
  "display_duration": 60,
  "log_level": "INFO",
  "sequence": [
    {"name": "tic_tac_toe", "type": "game", "enabled": true},
    {"name": "snake", "type": "game", "enabled": true},
    {"name": "pong", "type": "game", "enabled": true},
    {"name": "billiards", "type": "game", "enabled": true},
    {"name": "time_display", "type": "utility", "enabled": true},
    {"name": "bitcoin_price", "type": "utility", "enabled": false},
    {"name": "youtube_stream", "type": "video", "enabled": false}
  ]
}
```

- `display_duration`: seconds each feature runs before cycling to the next
- `enabled`: toggle features on/off
- Config is reloaded between full cycles -- changes take effect without restart

### WiFi Networks (`config/wifi.json`)

- `networks`: array of WiFi networks to try, in priority order
- `connection_timeout`: seconds to wait for a connection attempt
- `retry_attempts`: number of retries per network
- `connectivity_check_url`: URL used to verify internet access

## Managing the System

### Service Commands

```bash
# Display service
sudo systemctl status led-matrix.service
sudo systemctl start led-matrix.service
sudo systemctl stop led-matrix.service
sudo systemctl restart led-matrix.service

# Auto-updater timer
sudo systemctl status led-matrix-updater.timer
sudo systemctl list-timers led-matrix-updater.timer

# Force an update check now
sudo systemctl start led-matrix-updater.service
```

### Viewing Logs

```bash
# Display service logs
journalctl -u led-matrix.service -f

# Updater logs
journalctl -u led-matrix-updater.service -f

# Application logs
tail -f logs/display.log
tail -f logs/updater.log
```

### WiFi Management

```bash
# Check current WiFi status
cd /home/pi/LED_MATRIX-Project
venv/bin/python3 -m src.wifi.manager status

# Scan for networks
venv/bin/python3 -m src.wifi.manager scan

# Reconnect to WiFi
venv/bin/python3 -m src.wifi.manager connect
```

### Web Control Panel

```bash
# Web panel service
sudo systemctl status led-matrix-web.service
sudo systemctl restart led-matrix-web.service

# View web panel logs
journalctl -u led-matrix-web.service -f
```

Access at `http://<pi-ip>:5000` from any device on the same network.

## How Auto-Update Works

1. A systemd timer triggers every 30 minutes (configurable)
2. The updater script ensures WiFi connectivity
3. Runs `git fetch` to check for remote changes
4. If the remote branch has new commits:
   - Stashes local changes
   - Pulls updates (`git pull --ff-only`)
   - Reinstalls Python dependencies
   - Restarts the display service
5. All activity is logged to `logs/updater.log`

## Development (Windows/macOS)

The project includes a pygame-based LED matrix simulator for development without Pi hardware:

```bash
# Install dependencies (pygame installs automatically on Windows/macOS)
pip install -r requirements.txt

# Run with simulator
python src/main.py
```

A window will open showing a virtual 64x64 LED matrix. Each pixel is rendered as a small square with gaps to simulate the LED grid appearance.

### Config Validation

Validate your configuration files before deploying:

```bash
python -m src.config_validator
```

### WiFi Diagnostics

Test WiFi connectivity and captive portal detection:

```bash
python -m src.wifi.manager status
python -m src.wifi.manager portal
python -m src.wifi.manager scan
```

### Testing

Run the test suite (uses the simulator, no Pi hardware needed):

```bash
pytest
```

80 tests across 5 files. Tests cover:
- Simulator API compliance (pixel buffer, matrix, canvas, graphics)
- Config validation (schema errors, warnings, edge cases)
- Display module interface (all 7 modules have `run(matrix, duration)`)
- Integration (full feature cycle, crash recovery, config validation)
- Web endpoints (authentication, routes, API, config management)

Test files: `test_simulator.py`, `test_config_validator.py`, `test_display_modules.py`, `test_integration.py`, `test_web.py`

## Hardware Requirements

- Raspberry Pi (any model with GPIO headers)
- 64x64 RGB LED Matrix panel
- Adafruit RGB Matrix HAT or Bonnet
- 5V power supply (4A+ recommended)
- WiFi connectivity (built-in or USB adapter)

## License

See repository for license information.
