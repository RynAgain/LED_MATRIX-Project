# LED Matrix Project - Complete Overview

## Project Purpose

This project transforms a Raspberry Pi with a 64x64 LED matrix into an interactive entertainment and information display system. It cycles through various games, utilities, and video content, creating an engaging visual experience.

---

## Core Functionality

The system automatically cycles through enabled features in a configurable sequence:
- **Games**: Tic-Tac-Toe, Snake, Pong, and Billiards with AI opponents
- **Utilities**: Real-time clock display and live Bitcoin price tracking
- **Media**: YouTube video streaming with customizable playlists

---

## File Structure & Functions

### Main Control Files

#### [`consolidated_games.py`](consolidated_games.py:1)
**Purpose:** Main orchestrator that runs the entire system

**Key Functions:**
- [`load_config()`](consolidated_games.py:28) - Loads feature sequence from config.json
- [`main()`](consolidated_games.py:33) - Infinite loop that cycles through enabled features
- Initializes 64x64 RGB LED matrix with proper hardware settings
- Handles game execution, utility displays, and video streaming
- Includes error handling and logging for all features

**How it works:**
1. Reads [`config.json`](config.json:1) to determine which features are enabled
2. Loops through each enabled feature in sequence
3. Executes games, utilities, or video streaming based on type
4. Repeats infinitely until manually stopped

---

#### [`config.json`](config.json:1)
**Purpose:** Configuration file that controls which features run and in what order

**Structure:**
```json
{
  "sequence": [
    {
      "name": "feature_name",
      "type": "game|utility|video",
      "enabled": true|false
    }
  ]
}
```

**Available Features:**
- `tic_tac_toe` (game) - Currently disabled
- `snake` (game) - Currently disabled
- `pong` (game) - Currently enabled
- `billiards` (game) - Currently enabled
- `time_display` (utility) - Currently disabled
- `youtube_stream` (video) - Currently enabled
- `bitcoin_price_display` (utility) - Currently enabled

---

### Game Files

#### [`tic_tac_toe.py`](tic_tac_toe.py:1)
**Purpose:** Classic Tic-Tac-Toe game with AI vs AI gameplay

**Key Functions:**
- [`print_tic_tac_toe_board(matrix)`](tic_tac_toe.py:8) - Renders 3x3 grid with X's and O's on LED matrix
- [`check_tic_tac_toe_winner(board, player)`](tic_tac_toe.py:31) - Checks all win conditions (rows, columns, diagonals)
- [`check_tic_tac_toe_draw(board)`](tic_tac_toe.py:38) - Determines if board is full (draw condition)
- [`tic_tac_toe_ai_move(player)`](tic_tac_toe.py:42) - AI makes random valid move
- [`reset_tic_tac_toe_board()`](tic_tac_toe.py:50) - Clears board for new game

**Gameplay:** Two AI players take turns making random moves until win or draw

---

#### [`snake.py`](snake.py:1)
**Purpose:** Snake game where the snake automatically pursues food

**Key Functions:**
- [`draw_snake(matrix)`](snake.py:11) - Renders snake (green) and food (red) on matrix
- [`move_snake()`](snake.py:25) - AI movement logic that always pursues food
- [`reset_snake_game()`](snake.py:57) - Resets snake to starting position and length

**Gameplay:** 
- Snake starts at center with 3 segments
- Automatically moves toward food using shortest path
- Grows when eating food
- Game ends on self-collision
- Food never spawns on snake body

---

#### [`pong.py`](pong.py:1)
**Purpose:** Classic Pong game with two AI-controlled paddles

**Key Functions:**
- [`draw_pong(matrix)`](pong.py:19) - Renders paddles (white) and ball (yellow)
- [`move_pong()`](pong.py:33) - Updates ball physics and AI paddle movement
- [`reset_pong_game()`](pong.py:90) - Resets game state with random ball direction
- [`play_pong(matrix)`](pong.py:103) - Main game loop (plays 1 full game)

**Gameplay Features:**
- Ball speed increases with each paddle hit (max speed: 3)
- Paddles shrink after every 10 successful passes (min height: 2)
- AI paddles track ball with slight randomness for realism
- Dynamic paddle boundary checking prevents out-of-bounds errors

---

#### [`billiards.py`](billiards.py:1)
**Purpose:** 2D billiards simulation with physics and AI player

**Key Classes:**
- [`Ball`](billiards.py:23) - Represents each ball with position, velocity, color, and physics

**Key Functions:**
- [`Ball.draw(canvas)`](billiards.py:34) - Renders circular ball on matrix
- [`Ball.move()`](billiards.py:40) - Updates position with velocity and friction
- [`Ball.check_collision(other)`](billiards.py:64) - Handles ball-to-ball collisions
- [`Ball.is_in_pocket(pockets)`](billiards.py:75) - Checks if ball is pocketed
- [`ai_play(balls, pockets)`](billiards.py:90) - AI calculates optimal shot angle and strength
- [`draw_table_edges(canvas)`](billiards.py:122) - Renders green table borders
- [`draw_pockets(canvas, pockets)`](billiards.py:130) - Renders blue corner pockets
- [`main(matrix)`](billiards.py:137) - Main game loop

**Gameplay:**
- White cue ball + 4 colored balls (red, yellow, blue, green)
- AI aims to pocket all balls using physics calculations
- Realistic collision physics and friction
- Cue ball resets if pocketed
- Game ends when all colored balls are pocketed or max shots (100) reached

---

### Utility Files

#### [`time_display.py`](time_display.py:1)
**Purpose:** Displays current time and date on LED matrix

**Key Functions:**
- [`display_time_and_date(matrix)`](time_display.py:5) - Shows time (HH:MM:SS) with gradient colors and date (YYYY-MM-DD)
- [`display_binary_clock(matrix)`](time_display.py:32) - Shows time in binary format (6-bit representation)

**Display Duration:** Each mode runs for 60 seconds

**Visual Features:**
- Time displayed with color gradient effect
- Date shown in cyan
- Binary clock uses green LEDs for 1s, black for 0s

---

#### [`bitcoin_price_display.py`](bitcoin_price_display.py:1)
**Purpose:** Fetches and displays live Bitcoin price in USD

**Key Functions:**
- [`display_bitcoin_price_on_matrix(matrix, canvas, price)`](bitcoin_price_display.py:6) - Renders price on matrix using PIL
- [`fetch_bitcoin_price()`](bitcoin_price_display.py:15) - Gets current BTC price from CoinDesk API
- [`main(matrix, canvas)`](bitcoin_price_display.py:26) - Updates price every 10 seconds for 60 seconds total

**Data Source:** CoinDesk API (https://api.coindesk.com/v1/bpi/currentprice/BTC.json)

**Visual Features:**
- Price displayed in gold color (255, 215, 0)
- "USD" label in white
- Updates every 10 seconds
- Graceful error handling if API fails

---

### Media Files

#### [`youtube_stream.py`](youtube_stream.py:1)
**Purpose:** Streams YouTube videos to LED matrix with playlist support

**Key Functions:**
- [`read_urls_from_csv(file_path)`](youtube_stream.py:11) - Parses CSV file with video URLs and durations
- [`stream_video(url)`](youtube_stream.py:24) - Uses yt-dlp to get video stream URL
- [`stream_youtube_videos(urls, matrix)`](youtube_stream.py:36) - Main streaming loop
- [`play_videos_on_matrix(matrix)`](youtube_stream.py:103) - Entry point for video playback

**How it works:**
1. Reads [`youtube_urls.csv`](youtube_urls.csv:1) for video list
2. Downloads video stream using yt-dlp
3. Captures frames with OpenCV
4. Resizes frames to 64x64 pixels
5. Converts BGR to RGB color space
6. Displays on LED matrix at ~10 FPS

**Duration Control:**
- Specify duration in minutes in CSV (e.g., "3" for 3 minutes)
- Use "x" to play entire video
- Automatically moves to next video when duration reached

---

#### [`youtube_urls.csv`](youtube_urls.csv:1)
**Purpose:** Playlist configuration for YouTube streaming

**Format:**
```csv
url,title,duration
https://www.youtube.com/watch?v=VIDEO_ID,Video Title,duration_in_minutes_or_x
```

**Current Playlist:**
1. dandadan - Full video
2. Mario! - 1 minute
3. nyancat - 30 seconds
4. TestDemo - 3 minutes
5. gamecube - Full video
6. NeonLights - 1 minute
7. colours - 1 minute

---

### Installation & Setup Files

#### [`install.sh`](install.sh:1)
**Purpose:** Automated installation script for Raspberry Pi

**What it does:**
1. Updates system package list
2. Installs system dependencies:
   - Python 3 and pip
   - Git version control
   - VLC media player
3. Installs Python packages from [`requirements.txt`](requirements.txt:1)
4. Installs RGB Matrix library (Raspberry Pi only)
5. Creates `downloaded_videos/` directory
6. Makes scripts executable

**Usage:** `./install.sh`

---

#### [`requirements.txt`](requirements.txt:1)
**Purpose:** Lists all Python dependencies

**Dependencies:**
- `yt_dlp` - YouTube video downloading
- `Pillow` - Image processing and rendering
- `opencv-python==3.4.11.12` - Video frame capture and processing
- `numpy` - Numerical operations for image arrays
- `requests` - HTTP requests for Bitcoin API

---

#### [`install_and_update.sh`](install_and_update.sh:1)
**Purpose:** Automatic update checker and program restarter

**Functionality:**
- Checks GitHub repository for updates every 30 minutes
- Pulls latest changes if available
- Restarts the program automatically
- Runs continuously in background

**Usage:** Called by startup script or run manually

---

#### [`add_to_startup.sh`](add_to_startup.sh:1)
**Purpose:** Adds program to Raspberry Pi boot sequence

**What it does:**
- Creates cron job to run [`install_and_update.sh`](install_and_update.sh:1) on boot
- Ensures program starts automatically after reboot
- Enables automatic updates on startup

**Usage:** `./add_to_startup.sh`

---

#### [`fix_python_path.bat`](fix_python_path.bat:1)
**Purpose:** Windows-specific utility to fix Python path issues

**Use case:** Helps Windows users troubleshoot Python installation and PATH configuration

---

### Support Files

#### [`.gitignore`](.gitignore:1)
**Purpose:** Specifies files Git should ignore

**Ignored items:**
- Python cache files (`__pycache__/`, `*.pyc`)
- Virtual environments
- IDE settings
- Downloaded video files
- System files

---

#### [`.gitattributes`](.gitattributes:1)
**Purpose:** Git configuration for line endings and file handling

---

#### [`downloaded_videos/`](downloaded_videos/)
**Purpose:** Storage directory for cached YouTube videos

**Contents:** Temporary video files downloaded by yt-dlp (automatically managed)

---

### RGB Matrix Library

#### [`rgbmatrix/`](rgbmatrix/)
**Purpose:** Python bindings for controlling RGB LED matrices

**Key Files:**
- [`__init__.py`](rgbmatrix/__init__.py:1) - Package initialization
- [`core.pyx`](rgbmatrix/core.pyx:1) - Cython core matrix control
- [`graphics.pyx`](rgbmatrix/graphics.pyx:1) - Cython graphics primitives
- [`Makefile`](rgbmatrix/Makefile:1) - Build configuration

**Note:** This is a compiled library specific to Raspberry Pi hardware

---

## System Architecture

### Execution Flow:
```
1. User starts system → consolidated_games.py
2. Load config.json → Determine enabled features
3. Initialize LED matrix (64x64, hardware settings)
4. Enter infinite loop:
   a. For each enabled feature in sequence:
      - If game: Run game logic until completion
      - If utility: Display for set duration (60s)
      - If video: Stream from YouTube playlist
   b. Repeat sequence
5. Handle errors gracefully, log all events
```

### Hardware Requirements:
- **Raspberry Pi** (any model with GPIO)
- **64x64 RGB LED Matrix**
- **Power supply** (adequate for LED matrix)
- **Internet connection** (for YouTube and Bitcoin price)

### Software Stack:
- **Python 3** - Main programming language
- **RGB Matrix Library** - Hardware control
- **PIL/Pillow** - Image rendering
- **OpenCV** - Video processing
- **yt-dlp** - YouTube downloading
- **VLC** - Media playback support

---

## Configuration & Customization

### Enable/Disable Features:
Edit [`config.json`](config.json:1) and set `"enabled": true` or `"enabled": false` for any feature

### Change Feature Order:
Rearrange items in the `"sequence"` array in [`config.json`](config.json:1)

### Modify YouTube Playlist:
Edit [`youtube_urls.csv`](youtube_urls.csv:1) to add/remove videos or change durations

### Adjust Game Parameters:
Each game file has constants at the top that can be modified:
- Snake speed, starting length
- Pong ball speed, paddle size
- Billiards friction, AI strength
- Display durations

---

## Platform Support

### Raspberry Pi (Full Support):
- All games functional
- LED matrix display
- YouTube streaming
- Automatic updates
- Boot-on-startup

### Windows (Limited Support):
- YouTube streaming only
- Bitcoin price fetching (console output)
- No LED matrix support
- Useful for development/testing

---

## Error Handling

The system includes comprehensive error handling:
- YouTube streaming failures logged, system continues
- Bitcoin API failures logged, system continues
- Game crashes caught and logged
- Network issues handled gracefully
- All errors logged with timestamps

---

## Performance Characteristics

- **Frame Rate:** ~10 FPS for video streaming
- **Game Speed:** Configurable via sleep() calls
- **Update Frequency:** Bitcoin price every 10 seconds
- **Memory Usage:** Minimal (suitable for Raspberry Pi)
- **CPU Usage:** Moderate during video streaming

---

*This project provides an automated, self-updating entertainment and information display system for RGB LED matrices.*