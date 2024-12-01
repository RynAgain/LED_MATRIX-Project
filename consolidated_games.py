import time
import logging
from rgbmatrix import RGBMatrix, RGBMatrixOptions
import youtube_stream
import tic_tac_toe
import snake
import pong
import time_display
import billiards  # Import the billiards module

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

def main():
    """Main game loop."""
    while True:
        # Play Tic-Tac-Toe
        for _ in range(10):  # Play 10 games of Tic-Tac-Toe
            tic_tac_toe.reset_tic_tac_toe_board()
            tic_tac_toe.print_tic_tac_toe_board(matrix)
            while True:
                # AI move for 'X'
                tic_tac_toe.tic_tac_toe_ai_move('X')
                tic_tac_toe.print_tic_tac_toe_board(matrix)
                time.sleep(1)  # Slow down the game for visibility
                if tic_tac_toe.check_tic_tac_toe_winner(tic_tac_toe.tic_tac_toe_board, 'X'):
                    logging.info("Player X wins")
                    break
                if tic_tac_toe.check_tic_tac_toe_draw(tic_tac_toe.tic_tac_toe_board):
                    logging.info("Game is a draw")
                    break
                
                # AI move for 'O'
                tic_tac_toe.tic_tac_toe_ai_move('O')
                tic_tac_toe.print_tic_tac_toe_board(matrix)
                time.sleep(1)  # Slow down the game for visibility
                if tic_tac_toe.check_tic_tac_toe_winner(tic_tac_toe.tic_tac_toe_board, 'O'):
                    logging.info("Player O wins")
                    break
                if tic_tac_toe.check_tic_tac_toe_draw(tic_tac_toe.tic_tac_toe_board):
                    logging.info("Game is a draw")
                    break
        
        # Snake game loop
        snake.reset_snake_game()
        while not snake.game_over:
            snake.draw_snake(matrix)
            snake.move_snake()
            time.sleep(0.1)
        
        # Pong game loop
        pong.play_pong(matrix)
        
        # Billiards game loop
        billiards.main(matrix)  # Call the main function of the billiards game
        
        # Display time and date
        time_display.display_time_and_date(matrix)
        
        # Display binary clock
        time_display.display_binary_clock(matrix)
        
        # Play YouTube videos
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
