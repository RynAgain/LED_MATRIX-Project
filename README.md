# LED Matrix Project

This project is designed to run on a Raspberry Pi and control a 64x64 LED matrix. It includes three games: Tic-Tac-Toe, Snake, and Pong, as well as YouTube video streaming capabilities. The project also features an automatic update mechanism from a GitHub repository.

## Project Structure

- `consolidated_games.py`: Main script that orchestrates the execution of games and features, cycling through Tic-Tac-Toe, Snake, Pong, time display, and YouTube streaming.
- `tic_tac_toe.py`: Contains the logic for the Tic-Tac-Toe game.
- `snake.py`: Contains the logic for the Snake game.
- `pong.py`: Contains the logic for the Pong game.
- `time_display.py`: Contains functions for displaying the current time and date on the LED matrix.
- `youtube_stream.py`: Handles YouTube video streaming functionality using yt-dlp. **New:** Downloads videos locally to avoid repeated streaming.
- `youtube_urls.csv`: Contains list of YouTube URLs to play in sequence.
- `requirements.txt`: Lists all Python dependencies (for Raspberry Pi deployment).
- `install_and_update.sh`: Checks for updates from the GitHub repository and restarts the program if updates are found.
- `add_to_startup.sh`: Adds `install_and_update.sh` to the Raspberry Pi's boot sequence using a cron job.
- `billiards.py`: Simulates a 2D billiards game with AI, featuring full physics and graphical representation. **Updated:** Improved code structure for better readability and maintainability.

## System Requirements

### Raspberry Pi
- Raspberry Pi (any model with sufficient GPIO pins)
- Python 3
- VLC media player
- LED Matrix (64x64)
- Internet connection for YouTube streaming and updates

### Windows
- Python 3
- VLC media player (architecture must match Python installation)
- Internet connection for YouTube streaming
- Note: LED Matrix functionality is NOT available on Windows

## Setup Instructions

### For Raspberry Pi (Full Functionality)

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/RynAgain/LED_MATRIX-Project.git
   cd LED_MATRIX-Project
   ```

2. **Install Dependencies**:
   Run the `install.sh` script to install Python dependencies and necessary system packages (including VLC).
   ```bash
   ./install.sh
   ```

3. **Add to Startup**:
   Run the `add_to_startup.sh` script to ensure the program updates and restarts on boot.
   ```bash
   ./add_to_startup.sh
   ```

### For Windows (Limited Functionality - YouTube Streaming Only)

1. **Clone the Repository**:
   ```cmd
   git clone https://github.com/RynAgain/LED_MATRIX-Project.git
   cd LED_MATRIX-Project
   ```

2. **Install Dependencies**:
   Follow the instructions in the `requirements.txt` to install Windows-compatible Python dependencies.

3. **Install VLC Media Player**:
   - Download VLC from https://www.videolan.org/vlc/download-windows.html
   - **IMPORTANT**: Match VLC architecture with Python
     - If using 64-bit Python (recommended), install 64-bit VLC
     - If using 32-bit Python, install 32-bit VLC
   - During installation:
     - Select "Add VLC to PATH" option
     - Use default installation directory (usually in Program Files)
   - After installation:
     - Restart your computer to ensure PATH changes take effect

## Usage

- **Running the Games and Features** (Raspberry Pi Only):
  Execute the `consolidated_games.py` script to start the automatic cycling through Tic-Tac-Toe, Snake, Pong, time display, and YouTube streaming.
  ```bash
  python3 consolidated_games.py
  ```

- **Streaming YouTube Videos** (Both Platforms):
  The YouTube streaming feature now supports playing videos from a CSV file in sequence.

  1. **CSV File Format**:
     Create a CSV file (default: youtube_urls.csv) with the following format:
     ```csv
     url,title
     https://www.youtube.com/watch?v=example1,Video Title 1
     https://www.youtube.com/watch?v=example2,Video Title 2
     ```

  2. **Running the Stream**:
     ```bash
     python youtube_stream.py                  # Uses default youtube_urls.csv
     python youtube_stream.py custom_list.csv  # Uses custom CSV file
     ```

  3. **Features**:
     - Plays videos in sequence from the CSV file
     - **New:** Downloads videos locally to `downloaded_videos` directory
     - Videos play automatically in sequence
     - Shows title and quality information for each video
     - Each video is limited to a maximum playback time of 3 minutes

- **Running the Billiards Game** (Both Platforms):
  Execute the `billiards.py` script to start the billiards game simulation.
  ```bash
  python billiards.py
  ```

- **Automatic Updates** (Raspberry Pi only):
  The `install_and_update.sh` script will automatically check for updates every 30 minutes and restart the program if updates are found.

## Platform-Specific Features

### Raspberry Pi
- Full LED matrix support
- Games (Tic-Tac-Toe, Snake, and Pong)
- YouTube video streaming
- Automatic updates

### Windows
- YouTube video streaming only
- Useful for development and testing of streaming functionality
- **Note:** Windows support is intended for debugging and development purposes only.

## Troubleshooting

### VLC Installation Issues (Windows)
1. **Architecture Mismatch**:
   - Check Python architecture: Run `python -c "import platform; print(platform.architecture()[0])"` in command prompt
   - Install matching VLC version (32-bit or 64-bit)
   - If unsure, uninstall current VLC and install 64-bit version (recommended)

2. **VLC Not Found**:
   - Verify VLC is installed in one of these locations:
     - C:\Program Files\VideoLAN\VLC (64-bit)
     - C:\Program Files (x86)\VideoLAN\VLC (32-bit)
   - Ensure libvlc.dll exists in the VLC installation directory
   - Try uninstalling and reinstalling VLC
   - Make sure to restart your computer after installation

3. **DLL Load Issues**:
   - Run the script as administrator
   - Check Windows Defender or antivirus isn't blocking VLC
   - Verify PATH environment variable includes VLC directory

### YouTube Streaming Issues
1. **CSV File Issues**:
   - Verify CSV file format is correct (url,title columns)
   - Check that URLs are valid and accessible
   - Ensure no extra spaces or special characters in the CSV

2. **Playback Issues**:
   - Check internet connection
   - Verify VLC is properly installed
   - Try updating yt-dlp: `pip install --upgrade yt-dlp`
   - Check if videos are available in your region

### Raspberry Pi Issues
- If the program does not start, check the connections to the LED matrix
- For update issues, verify the GitHub repository URL and network connectivity

## License
