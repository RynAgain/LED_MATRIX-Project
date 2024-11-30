import time
import random
from datetime import datetime
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image, ImageDraw, ImageFont
import youtube_stream

# Configuration for the 64x64 matrix
options = RGBMatrixOptions()
options.rows = 64
options.cols = 64
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = 'regular'

# Create the matrix
matrix = RGBMatrix(options=options)

# Tic-Tac-Toe game variables
tic_tac_toe_board = [' ' for _ in range(9)]

def print_tic_tac_toe_board():
    """Display the current Tic-Tac-Toe board on the LED matrix."""
    image = Image.new("RGB", (64, 64))
    draw = ImageDraw.Draw(image)
    
    # Draw the grid
    draw.line((21, 0, 21, 64), fill=(255, 255, 255))
    draw.line((42, 0, 42, 64), fill=(255, 255, 255))
    draw.line((0, 21, 64, 21), fill=(255, 255, 255))
    draw.line((0, 42, 64, 42), fill=(255, 255, 255))
    
    # Draw the Xs and Os
    for i, cell in enumerate(tic_tac_toe_board):
        x = (i % 3) * 21
        y = (i // 3) * 21
        if cell == 'X':
            draw.line((x+5, y+5, x+16, y+16), fill=(255, 0, 0), width=2)
            draw.line((x+16, y+5, x+5, y+16), fill=(255, 0, 0), width=2)
        elif cell == 'O':
            draw.ellipse((x+5, y+5, x+16, y+16), outline=(0, 255, 0), width=2)
    
    matrix.SetImage(image)

def check_tic_tac_toe_winner(board, player):
    """Check if the given player has won in Tic-Tac-Toe."""
    win_conditions = [(0, 1, 2), (3, 4, 5), (6, 7, 8),
                      (0, 3, 6), (1, 4, 7), (2, 5, 8),
                      (0, 4, 8), (2, 4, 6)]
    return any(all(board[i] == player for i in condition) for condition in win_conditions)

def tic_tac_toe_ai_move(player):
    """Make a move for the AI in Tic-Tac-Toe."""
    available_moves = [i for i, cell in enumerate(tic_tac_toe_board) if cell == ' ']
    if available_moves:  # Ensure there are available moves
        move = random.choice(available_moves)
        tic_tac_toe_board[move] = player

def reset_tic_tac_toe_board():
    """Reset the Tic-Tac-Toe board for a new game."""
    global tic_tac_toe_board
    tic_tac_toe_board = [' ' for _ in range(9)]

# Snake game variables
snake = [(32, 32)]
direction = (0, 1)
food = (random.randint(0, 63), random.randint(0, 63))
game_over = False

def draw_snake():
    """Draw the snake and food on the LED matrix."""
    image = Image.new("RGB", (64, 64))
    draw = ImageDraw.Draw(image)
    
    # Draw the snake
    for segment in snake:
        draw.rectangle((segment[0], segment[1], segment[0]+1, segment[1]+1), fill=(0, 255, 0))
    
    # Draw the food
    draw.rectangle((food[0], food[1], food[0]+1, food[1]+1), fill=(255, 0, 0))
    
    matrix.SetImage(image)

def move_snake():
    """Move the snake in the current direction."""
    global game_over, food
    new_head = (snake[0][0] + direction[0], snake[0][1] + direction[1])
    
    # Check for collisions
    if new_head in snake or not (0 <= new_head[0] < 64) or not (0 <= new_head[1] < 64):
        game_over = True
        return
    
    # Check for food
    if new_head == food:
        snake.insert(0, new_head)
        food = (random.randint(0, 63), random.randint(0, 63))
    else:
        snake.insert(0, new_head)
        snake.pop()

def reset_snake_game():
    """Reset the Snake game for a new game."""
    global snake, direction, game_over
    snake = [(32, 32)]
    direction = (0, 1)
    game_over = False

def display_time_and_date():
    """Display the current time and date on the LED matrix."""
    end_time = time.time() + 60  # Display for 1 minute
    while time.time() < end_time:
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        current_date = now.strftime("%Y-%m-%d")
        
        image = Image.new("RGB", (64, 64))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        
        draw.text((0, 0), current_time, font=font, fill=(255, 255, 255))
        draw.text((0, 32), current_date, font=font, fill=(255, 255, 255))
        
        matrix.SetImage(image)
        time.sleep(1)

def main():
    """Main game loop."""
    global game_over
    for _ in range(10):  # Play 10 games of Tic-Tac-Toe
        reset_tic_tac_toe_board()
        print_tic_tac_toe_board()
        while True:
            # AI move for 'X'
            tic_tac_toe_ai_move('X')
            print_tic_tac_toe_board()
            time.sleep(1)  # Slow down the game for visibility
            if check_tic_tac_toe_winner(tic_tac_toe_board, 'X'):
                break
            
            # AI move for 'O'
            tic_tac_toe_ai_move('O')
            print_tic_tac_toe_board()
            time.sleep(1)  # Slow down the game for visibility
            if check_tic_tac_toe_winner(tic_tac_toe_board, 'O'):
                break
    
    # Snake game loop
    reset_snake_game()
    while not game_over:
        draw_snake()
        move_snake()
        time.sleep(0.1)
    
    # Display time and date
    display_time_and_date()
    
    # Play YouTube videos
    try:
        youtube_stream.play_videos_on_matrix(matrix)
    except Exception as e:
        print(f"Error playing videos: {str(e)}")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        matrix.Clear()
