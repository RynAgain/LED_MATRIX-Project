#!/bin/bash

# LED Matrix Project - Auto-Update and Restart Script
# This script checks for updates from GitHub and restarts the program if updates are found

# Configuration
REPO_URL="https://github.com/RynAgain/LED_MATRIX-Project.git"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/update.log"
PID_FILE="$PROJECT_DIR/led_matrix.pid"
PYTHON_SCRIPT="consolidated_games.py"
CHECK_INTERVAL=1800  # 30 minutes in seconds

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to check if program is running
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0  # Running
        fi
    fi
    return 1  # Not running
}

# Function to stop the program
stop_program() {
    log "Stopping LED Matrix program..."
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            kill "$PID"
            sleep 2
            
            # Force kill if still running
            if ps -p "$PID" > /dev/null 2>&1; then
                log "Force killing process $PID"
                kill -9 "$PID"
            fi
        fi
        rm -f "$PID_FILE"
    fi
    
    # Fallback: kill any remaining instances
    pkill -f "$PYTHON_SCRIPT"
    log "Program stopped"
}

# Function to start the program
start_program() {
    log "Starting LED Matrix program..."
    
    cd "$PROJECT_DIR"
    
    # Start the program in background and save PID
    nohup python3 "$PYTHON_SCRIPT" >> "$LOG_DIR/program.log" 2>&1 &
    echo $! > "$PID_FILE"
    
    log "Program started with PID $(cat $PID_FILE)"
}

# Function to restart the program
restart_program() {
    log "Restarting LED Matrix program..."
    stop_program
    sleep 2
    start_program
}

# Function to check for updates from GitHub
check_for_updates() {
    log "Checking for updates..."
    
    cd "$PROJECT_DIR"
    
    # Ensure we're in a git repository
    if [ ! -d ".git" ]; then
        log "ERROR: Not a git repository. Please clone from $REPO_URL"
        return 1
    fi
    
    # Fetch latest changes
    git fetch origin 2>&1 | tee -a "$LOG_FILE"
    
    # Check if there are updates
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse origin/main 2>/dev/null || git rev-parse origin/master 2>/dev/null)
    
    if [ "$LOCAL" != "$REMOTE" ]; then
        log "New version found! Updating..."
        log "Local: $LOCAL"
        log "Remote: $REMOTE"
        
        # Stash any local changes
        git stash 2>&1 | tee -a "$LOG_FILE"
        
        # Pull updates
        if git pull origin main 2>&1 | tee -a "$LOG_FILE" || git pull origin master 2>&1 | tee -a "$LOG_FILE"; then
            log "Update successful!"
            
            # Install any new dependencies
            log "Updating dependencies..."
            pip3 install -r requirements.txt 2>&1 | tee -a "$LOG_FILE"
            
            # Restart the program
            restart_program
            return 0
        else
            log "ERROR: Failed to pull updates"
            return 1
        fi
    else
        log "No updates found. System is up to date."
        return 0
    fi
}

# Function to ensure program is running
ensure_running() {
    if ! is_running; then
        log "Program is not running. Starting..."
        start_program
    fi
}

# Function to install dependencies
install_dependencies() {
    log "Checking and installing dependencies..."
    
    cd "$PROJECT_DIR"
    
    # Update package list
    sudo apt-get update 2>&1 | tee -a "$LOG_FILE"
    
    # Install system dependencies
    sudo apt-get install -y python3 python3-pip git vlc 2>&1 | tee -a "$LOG_FILE"
    
    # Install Python dependencies
    pip3 install -r requirements.txt 2>&1 | tee -a "$LOG_FILE"
    
    log "Dependencies installed"
}

# Main script execution
main() {
    log "=========================================="
    log "LED Matrix Auto-Update Script Started"
    log "=========================================="
    log "Project Directory: $PROJECT_DIR"
    log "Log File: $LOG_FILE"
    log "Check Interval: $CHECK_INTERVAL seconds ($(($CHECK_INTERVAL / 60)) minutes)"
    
    # Install dependencies on first run
    if [ "$1" == "--install" ]; then
        install_dependencies
    fi
    
    # Initial check and start
    check_for_updates
    ensure_running
    
    # Continuous monitoring loop
    log "Entering monitoring loop..."
    while true; do
        sleep "$CHECK_INTERVAL"
        
        log "Running scheduled update check..."
        check_for_updates
        ensure_running
    done
}

# Handle script termination
cleanup() {
    log "Received termination signal. Cleaning up..."
    stop_program
    exit 0
}

trap cleanup SIGTERM SIGINT

# Run main function
main "$@"
