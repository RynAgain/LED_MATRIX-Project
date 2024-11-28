#!/bin/bash

# Function to install necessary dependencies
install_dependencies() {
    echo "Installing dependencies..."
    sudo apt update
    sudo apt install -y git
    # Add other dependencies as needed
}

# Function to check for updates from GitHub
check_for_updates() {
    echo "Checking for updates..."
    if [ -d "LED_MATRIX" ]; then
        cd LED_MATRIX
        git fetch
        LOCAL=$(git rev-parse HEAD)
        REMOTE=$(git rev-parse @{u})
        if [ $LOCAL != $REMOTE ]; then
            echo "New version found. Updating..."
            git pull
            restart_program
        else
            echo "No updates found."
        fi
        cd ..
    else
        echo "Cloning repository..."
        git clone https://github.com/RynAgain/LED_MATRIX-Project.git
        cd LED_MATRIX-Project
        restart_program
        cd ..
    fi
}

# Function to restart the program
restart_program() {
    echo "Restarting the program..."
    # Add commands to stop the current program if running
    # Add commands to start the program
}

# Main script execution
install_dependencies

# Loop to check for updates every 30 minutes
while true; do
    check_for_updates
    echo "Waiting for 30 minutes before checking again..."
    sleep 1800 # 1800 seconds = 30 minutes
done
