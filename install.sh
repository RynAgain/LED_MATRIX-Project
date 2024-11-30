#!/bin/bash

# Update package list and install Python3 and pip
sudo apt-get update
sudo apt-get install -y python3 python3-pip

# Install VLC media player
sudo apt-get install -y vlc

# Install Python dependencies
pip3 install -r requirements.txt

# Install additional system dependencies for rgbmatrix
sudo apt-get install -y libgraphicsmagick++-dev libwebp-dev
