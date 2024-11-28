# LED Matrix Project

This project is designed to run on a Raspberry Pi and control a 64x64 LED matrix. It includes two games: Tic-Tac-Toe and Snake. The project also features an automatic update mechanism from a GitHub repository.

## Project Structure

- `consolidated_games.py`: Contains the logic for both Tic-Tac-Toe and Snake games.
- `requirements.txt`: Lists the Python dependencies required for the project.
- `install.sh`: Installs the necessary Python dependencies and system packages.
- `install_and_update.sh`: Checks for updates from the GitHub repository and restarts the program if updates are found.
- `add_to_startup.sh`: Adds `install_and_update.sh` to the Raspberry Pi's boot sequence using a cron job.

## Setup Instructions

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/RynAgain/LED_MATRIX-Project.git
   cd LED_MATRIX-Project
   ```

2. **Install Dependencies**:
   Run the `install.sh` script to install Python dependencies and necessary system packages.
   ```bash
   ./install.sh
   ```

3. **Add to Startup**:
   Run the `add_to_startup.sh` script to ensure the program updates and restarts on boot.
   ```bash
   ./add_to_startup.sh
   ```

## Usage

- **Running the Games**:
  Execute the `consolidated_games.py` script to start the games.
  ```bash
  python3 consolidated_games.py
  ```

- **Automatic Updates**:
  The `install_and_update.sh` script will automatically check for updates every 30 minutes and restart the program if updates are found.

## Additional Information

- Ensure your Raspberry Pi is connected to the internet for the update mechanism to work.
- The LED matrix should be properly connected to the Raspberry Pi GPIO pins as per the library's requirements.

## Troubleshooting

- If the program does not start, check the connections to the LED matrix and ensure all dependencies are installed.
- For any issues with updates, verify the GitHub repository URL and network connectivity.

## License

This project is licensed under the MIT License.
