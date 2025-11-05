# LED Matrix Auto-Start & Auto-Update System Guide

## Overview

The LED Matrix project includes a robust auto-start and auto-update system that:
- Automatically starts the program on Raspberry Pi boot
- Checks for updates from GitHub every 30 minutes
- Automatically restarts the program after updates
- Maintains detailed logs of all operations
- Ensures the program stays running even after crashes

---

## System Components

### 1. [`install_and_update.sh`](install_and_update.sh:1)
**Main auto-update and monitoring script**

**Features:**
- Checks GitHub for updates every 30 minutes
- Automatically pulls and applies updates
- Restarts program after updates
- Monitors program health and restarts if crashed
- Maintains PID file for process tracking
- Comprehensive logging system

**Key Functions:**
- `check_for_updates()` - Fetches and applies GitHub updates
- `start_program()` - Starts the LED Matrix program
- `stop_program()` - Gracefully stops the program
- `restart_program()` - Stops and restarts the program
- `ensure_running()` - Checks if program is running and starts if needed
- `is_running()` - Checks program status via PID file

**Logs Location:** `logs/update.log` and `logs/program.log`

---

### 2. [`add_to_startup.sh`](add_to_startup.sh:1)
**Startup configuration script**

**Features:**
- Configures automatic startup on boot
- Supports two methods: systemd (preferred) and cron (fallback)
- Can remove existing configurations
- Provides helpful management commands

**Usage:**
```bash
./add_to_startup.sh           # Install with systemd (or cron fallback)
./add_to_startup.sh --cron    # Force cron installation
./add_to_startup.sh --remove  # Remove all startup configs
./add_to_startup.sh --help    # Show help
```

---

## Installation & Setup

### Step 1: Initial Installation
```bash
# Clone the repository
git clone https://github.com/RynAgain/LED_MATRIX-Project.git
cd LED_MATRIX-Project

# Run installation script
chmod +x install.sh
./install.sh
```

### Step 2: Configure Auto-Start
```bash
# Make startup script executable
chmod +x add_to_startup.sh

# Install auto-start (systemd preferred)
./add_to_startup.sh
```

### Step 3: Verify Installation
```bash
# If using systemd:
sudo systemctl status led-matrix

# If using cron:
crontab -l
```

---

## Systemd Service (Preferred Method)

### Service Details
- **Service Name:** `led-matrix`
- **Service File:** `/etc/systemd/system/led-matrix.service`
- **Auto-restart:** Yes (10 second delay)
- **Logs:** `logs/service.log` and systemd journal

### Management Commands

**Start the service:**
```bash
sudo systemctl start led-matrix
```

**Stop the service:**
```bash
sudo systemctl stop led-matrix
```

**Restart the service:**
```bash
sudo systemctl restart led-matrix
```

**Check status:**
```bash
sudo systemctl status led-matrix
```

**View logs (live):**
```bash
sudo journalctl -u led-matrix -f
```

**View logs (last 100 lines):**
```bash
sudo journalctl -u led-matrix -n 100
```

**Enable auto-start on boot:**
```bash
sudo systemctl enable led-matrix
```

**Disable auto-start:**
```bash
sudo systemctl disable led-matrix
```

---

## Cron Method (Fallback)

### Cron Job Details
- **Trigger:** `@reboot` (runs on system boot)
- **Delay:** 30 seconds after boot
- **Logs:** `logs/cron.log`

### Management Commands

**View cron jobs:**
```bash
crontab -l
```

**Edit cron jobs:**
```bash
crontab -e
```

**Remove cron job:**
```bash
./add_to_startup.sh --remove
```

---

## Auto-Update System

### How It Works

1. **Initial Start:**
   - Program starts via systemd or cron
   - Checks for updates immediately
   - Starts LED Matrix program

2. **Continuous Monitoring:**
   - Checks GitHub every 30 minutes
   - Compares local and remote versions
   - Pulls updates if available

3. **Update Process:**
   - Stashes local changes
   - Pulls latest code from GitHub
   - Installs new dependencies
   - Restarts the program

4. **Health Monitoring:**
   - Checks if program is running
   - Restarts if crashed
   - Maintains PID file for tracking

### Update Interval
Default: 30 minutes (1800 seconds)

To change, edit [`install_and_update.sh`](install_and_update.sh:13):
```bash
CHECK_INTERVAL=1800  # Change this value (in seconds)
```

---

## Logging System

### Log Files

**Update Log:** `logs/update.log`
- Update checks and results
- Git operations
- Program start/stop events
- Error messages

**Program Log:** `logs/program.log`
- Program output (stdout)
- Program errors (stderr)
- Game events
- Feature execution

**Service Log:** `logs/service.log` (systemd only)
- Systemd service output
- Service start/stop events

**Cron Log:** `logs/cron.log` (cron only)
- Cron job execution output

### Viewing Logs

**View update log:**
```bash
tail -f logs/update.log
```

**View program log:**
```bash
tail -f logs/program.log
```

**View all logs:**
```bash
tail -f logs/*.log
```

**Search logs:**
```bash
grep "ERROR" logs/*.log
grep "Update" logs/update.log
```

---

## Process Management

### PID File
Location: `led_matrix.pid`

Contains the process ID of the running program for tracking and management.

### Manual Control

**Check if running:**
```bash
if [ -f led_matrix.pid ]; then
    cat led_matrix.pid
    ps -p $(cat led_matrix.pid)
fi
```

**Manually stop:**
```bash
if [ -f led_matrix.pid ]; then
    kill $(cat led_matrix.pid)
    rm led_matrix.pid
fi
```

**Manually start:**
```bash
nohup python3 consolidated_games.py >> logs/program.log 2>&1 &
echo $! > led_matrix.pid
```

---

## Troubleshooting

### Program Not Starting

**Check service status:**
```bash
sudo systemctl status led-matrix
```

**Check logs:**
```bash
tail -50 logs/update.log
tail -50 logs/program.log
```

**Manually test:**
```bash
python3 consolidated_games.py
```

### Updates Not Working

**Check git status:**
```bash
git status
git remote -v
```

**Check network:**
```bash
ping github.com
```

**Manual update:**
```bash
git fetch
git pull
```

### Service Won't Start

**Check service file:**
```bash
sudo systemctl cat led-matrix
```

**Reload systemd:**
```bash
sudo systemctl daemon-reload
sudo systemctl restart led-matrix
```

**Check permissions:**
```bash
ls -la install_and_update.sh
chmod +x install_and_update.sh
```

### High CPU Usage

**Check running processes:**
```bash
top -p $(cat led_matrix.pid)
```

**Restart service:**
```bash
sudo systemctl restart led-matrix
```

---

## Uninstallation

### Remove Auto-Start
```bash
./add_to_startup.sh --remove
```

### Stop All Processes
```bash
# If using systemd:
sudo systemctl stop led-matrix
sudo systemctl disable led-matrix

# Manual cleanup:
pkill -f consolidated_games.py
rm -f led_matrix.pid
```

### Remove Service Files
```bash
sudo rm /etc/systemd/system/led-matrix.service
sudo systemctl daemon-reload
```

---

## Best Practices

1. **Monitor Logs Regularly:**
   - Check `logs/update.log` for update status
   - Check `logs/program.log` for errors

2. **Test Updates:**
   - Test major changes before deploying
   - Keep backups of working configurations

3. **Network Reliability:**
   - Ensure stable internet connection
   - Consider local git mirror for critical deployments

4. **Resource Management:**
   - Monitor CPU and memory usage
   - Adjust update interval if needed

5. **Backup Configuration:**
   - Keep backup of `config.json`
   - Document custom modifications

---

## Advanced Configuration

### Custom Update Interval

Edit [`install_and_update.sh`](install_and_update.sh:13):
```bash
CHECK_INTERVAL=3600  # 1 hour
CHECK_INTERVAL=7200  # 2 hours
CHECK_INTERVAL=900   # 15 minutes
```

### Custom Log Rotation

Add to crontab:
```bash
0 0 * * * find /path/to/LED_MATRIX-Project/logs -name "*.log" -mtime +7 -delete
```

### Email Notifications

Add to [`install_and_update.sh`](install_and_update.sh:1) after successful update:
```bash
echo "LED Matrix updated" | mail -s "Update Notification" your@email.com
```

---

## Security Considerations

1. **Run as Non-Root:**
   - Service runs as current user
   - Avoid running as root

2. **File Permissions:**
   - Scripts should be executable by owner only
   - Logs directory should be writable

3. **Network Security:**
   - Use SSH keys for GitHub access
   - Consider VPN for remote management

4. **Update Verification:**
   - Review changes before auto-update
   - Test in development environment first

---

*For additional support, check the main README.md or project documentation.*