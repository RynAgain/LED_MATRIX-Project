#!/bin/bash

# LED Matrix Project - Add to Startup Script
# This script configures the system to automatically start the LED Matrix program on boot

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="led-matrix"
SYSTEMD_SERVICE="/etc/systemd/system/${SERVICE_NAME}.service"
CRON_METHOD=false

echo "=========================================="
echo "LED Matrix - Add to Startup Configuration"
echo "=========================================="
echo ""
echo "Project Directory: $PROJECT_DIR"
echo ""

# Function to create systemd service (preferred method)
create_systemd_service() {
    echo "Creating systemd service..."
    
    sudo tee "$SYSTEMD_SERVICE" > /dev/null <<EOF
[Unit]
Description=LED Matrix Display System
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=/bin/bash $PROJECT_DIR/install_and_update.sh
Restart=always
RestartSec=10
StandardOutput=append:$PROJECT_DIR/logs/service.log
StandardError=append:$PROJECT_DIR/logs/service.log

[Install]
WantedBy=multi-user.target
EOF

    if [ $? -eq 0 ]; then
        echo "✓ Systemd service file created"
        
        # Reload systemd
        sudo systemctl daemon-reload
        echo "✓ Systemd daemon reloaded"
        
        # Enable service to start on boot
        sudo systemctl enable "$SERVICE_NAME"
        echo "✓ Service enabled for startup"
        
        # Start the service now
        sudo systemctl start "$SERVICE_NAME"
        echo "✓ Service started"
        
        echo ""
        echo "=========================================="
        echo "Systemd service installed successfully!"
        echo "=========================================="
        echo ""
        echo "Useful commands:"
        echo "  Start:   sudo systemctl start $SERVICE_NAME"
        echo "  Stop:    sudo systemctl stop $SERVICE_NAME"
        echo "  Restart: sudo systemctl restart $SERVICE_NAME"
        echo "  Status:  sudo systemctl status $SERVICE_NAME"
        echo "  Logs:    sudo journalctl -u $SERVICE_NAME -f"
        echo "  Disable: sudo systemctl disable $SERVICE_NAME"
        echo ""
        return 0
    else
        echo "✗ Failed to create systemd service"
        return 1
    fi
}

# Function to create cron job (fallback method)
create_cron_job() {
    echo "Creating cron job..."
    
    # Check if cron job already exists
    if crontab -l 2>/dev/null | grep -q "$PROJECT_DIR/install_and_update.sh"; then
        echo "✓ Cron job already exists"
        return 0
    fi
    
    # Add cron job
    (crontab -l 2>/dev/null; echo "@reboot sleep 30 && /bin/bash $PROJECT_DIR/install_and_update.sh >> $PROJECT_DIR/logs/cron.log 2>&1") | crontab -
    
    if [ $? -eq 0 ]; then
        echo "✓ Cron job added"
        echo ""
        echo "=========================================="
        echo "Cron job installed successfully!"
        echo "=========================================="
        echo ""
        echo "The program will start automatically on boot (after 30 second delay)"
        echo ""
        echo "To view cron jobs: crontab -l"
        echo "To remove: crontab -e (then delete the line)"
        echo ""
        return 0
    else
        echo "✗ Failed to create cron job"
        return 1
    fi
}

# Function to remove existing startup configurations
remove_existing() {
    echo "Checking for existing configurations..."
    
    # Remove systemd service if exists
    if [ -f "$SYSTEMD_SERVICE" ]; then
        echo "Removing existing systemd service..."
        sudo systemctl stop "$SERVICE_NAME" 2>/dev/null
        sudo systemctl disable "$SERVICE_NAME" 2>/dev/null
        sudo rm "$SYSTEMD_SERVICE"
        sudo systemctl daemon-reload
        echo "✓ Existing systemd service removed"
    fi
    
    # Remove cron job if exists
    if crontab -l 2>/dev/null | grep -q "$PROJECT_DIR/install_and_update.sh"; then
        echo "Removing existing cron job..."
        crontab -l 2>/dev/null | grep -v "$PROJECT_DIR/install_and_update.sh" | crontab -
        echo "✓ Existing cron job removed"
    fi
}

# Main execution
main() {
    # Create logs directory
    mkdir -p "$PROJECT_DIR/logs"
    
    # Parse command line arguments
    case "$1" in
        --remove)
            remove_existing
            echo ""
            echo "All startup configurations removed."
            exit 0
            ;;
        --cron)
            CRON_METHOD=true
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  (none)    Install using systemd (preferred) or cron (fallback)"
            echo "  --cron    Force installation using cron method"
            echo "  --remove  Remove all startup configurations"
            echo "  --help    Show this help message"
            echo ""
            exit 0
            ;;
    esac
    
    # Make install_and_update.sh executable
    chmod +x "$PROJECT_DIR/install_and_update.sh"
    echo "✓ Made install_and_update.sh executable"
    
    # Try systemd first (unless --cron specified)
    if [ "$CRON_METHOD" = false ] && command -v systemctl &> /dev/null; then
        if create_systemd_service; then
            exit 0
        else
            echo ""
            echo "Systemd installation failed. Falling back to cron..."
            echo ""
        fi
    fi
    
    # Fallback to cron
    if create_cron_job; then
        exit 0
    else
        echo ""
        echo "=========================================="
        echo "ERROR: Failed to configure startup"
        echo "=========================================="
        echo ""
        echo "Please manually add the following to your startup:"
        echo "$PROJECT_DIR/install_and_update.sh"
        exit 1
    fi
}

# Run main function
main "$@"
