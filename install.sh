#!/bin/bash

# LED Matrix Project Installation Script
# This script installs all necessary dependencies for the Raspberry Pi

echo "=========================================="
echo "LED Matrix Project - Installation Script"
echo "=========================================="
echo ""

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "WARNING: This script is designed for Raspberry Pi."
    echo "Some features may not work on other systems."
    echo ""
fi

# Update package list
echo "Updating package list..."
sudo apt-get update

# Install system dependencies
echo ""
echo "Installing system dependencies..."
sudo apt-get install -y python3 python3-pip git vlc

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip3 install -r requirements.txt

# Install RGB Matrix library (Raspberry Pi only)
if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo ""
    echo "Installing RGB Matrix library..."
    
    # Check if rgbmatrix is already installed
    if ! python3 -c "import rgbmatrix" 2>/dev/null; then
        echo "Cloning rpi-rgb-led-matrix repository..."
        cd /tmp
        git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
        cd rpi-rgb-led-matrix
        
        echo "Building RGB Matrix library..."
        make build-python PYTHON=$(which python3)
        sudo make install-python PYTHON=$(which python3)
        
        cd -
        echo "RGB Matrix library installed successfully."
    else
        echo "RGB Matrix library is already installed."
    fi
fi

# Create downloaded_videos directory if it doesn't exist
echo ""
echo "Creating necessary directories..."
mkdir -p downloaded_videos

# Make scripts executable
echo ""
echo "Making scripts executable..."
chmod +x install_and_update.sh
chmod +x add_to_startup.sh

echo ""
echo "=========================================="
echo "Installation complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. To add the program to startup, run: ./add_to_startup.sh"
echo "2. To start the program manually, run: python3 consolidated_games.py"
echo ""