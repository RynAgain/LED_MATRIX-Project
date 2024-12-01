import time
import logging
import json
from rgbmatrix import RGBMatrix, RGBMatrixOptions
import youtube_stream
import tic_tac_toe
import snake
import pong
import time_display
import billiards
import bitcoin_price_display

# Configuration for the 64x64 matrix
options = RGBMatrixOptions()
options.rows = 64
options.cols = 64
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = 'regular'

# Create the matrix
matrix = RGBMatrix(options=options)

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def load_config():
    """Load the configuration from a JSON file."""
    with open('config.json', 'r') as f:
        return json.load(f)

def main():
    """Main loop to execute games and utilities based on config."""
    config = load_config()
    sequence = config.get("sequence", [])
    
    for item in sequence:
        if not item.get("enabled", False):
            continue
        
        name = item.get("name")
        item_type = item.get("type")
        
        if item_type == "game":
            if name == "tic_tac_toe":
                for _ in range(3):
                    tic_tac_toe.reset_tic_tac_toe_board()
                    tic_tac_toe.print_tic_tac_toe_board(matrix)
                    while True:
                        tic_tac_toe.tic_tac_toe_ai_move('X')
                        tic_tac_toe.print_tic_tac_toe_board(matrix)
                        time.sleep(1)
                        if tic_tac_toe.check_tic_tac_toe_winner(tic_tac_toe.tic_tac_toe_board, 'X'):
                            logging.info("Player X wins")
                            break
                        if tic_tac_toe.check_tic_tac_toe_draw(tic_tac_toe.tic_tac_toe_board):
                            logging.info("Game is a draw")
                            break
                        tic_tac_toe.tic_tac_toe_ai_move('O')
                        tic_tac_toe.print_tic_tac_toe_board(matrix)
                        time.sleep(1)
                        if tic_tac_toe.check_tic_tac_toe_winner(tic_tac_toe.tic_tac_toe_board, 'O'):
                            logging.info("Player O wins")
                            break
                        if tic_tac_toe.check_tic_tac_toe_draw(tic_tac_toe.tic_tac_toe_board):
                            logging.info("Game is a draw")
                            break
            elif name == "snake":
                snake.reset_snake_game()
                while not snake.game_over:
                    snake.draw_snake(matrix)
                    snake.move_snake()
                    time.sleep(0.1)
            elif name == "pong":
                pong.play_pong(matrix)
            elif name == "billiards":
                billiards.main(matrix)
        
        elif item_type == "utility":
            if name == "time_display":
                time_display.display_time_and_date(matrix)
                time_display.display_binary_clock(matrix)
            elif name == "bitcoin_price_display":
                bitcoin_price_display.main()
        
        elif item_type == "video":
            if name == "youtube_stream":
                try:
                    youtube_stream.play_videos_on_matrix(matrix)
                except Exception as e:
                    logging.error(f"Error playing videos: {str(e)}")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Exiting...")
    finally:
        matrix.Clear()
