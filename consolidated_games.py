import time
import random
from datetime import datetime
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image, ImageDraw, ImageFont

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

def tic_tac_toe_ai_move():
    """Make a move for the AI in Tic-Tac-Toe."""
    available_moves = [i for i, cell in enumerate(tic_tac_toe_board) if cell == ' ']
    move = random.choice(available_moves)
    tic_tac_toe_board[move] = 'O'

def tic_tac_toe_player_move(move):
    """Make a move for the player in Tic-Tac-Toe."""
    if tic_tac_toe_board[move] == ' ':
        tic_tac_toe_board[move] = 'X'
        return True
    return False

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
    while True:
        # Choose which game to play
        game_choice = input("Enter '1' for Tic-Tac-Toe or '2' for Snake: ")
        
        if game_choice == '1':
            # Tic-Tac-Toe game loop
            reset_tic_tac_toe_board()
            print_tic_tac_toe_board()
            while True:
                # Player move
                try:
                    move = int(input("Enter your move (0-8): "))
                    if move < 0 or move > 8:
                        print("Invalid move. Please enter a number between 0 and 8.")
                        continue
                except ValueError:
                    print("Invalid input. Please enter a number between 0 and 8.")
                    continue
                
                if tic_tac_toe_player_move(move):
                    print_tic_tac_toe_board()
                    if check_tic_tac_toe_winner(tic_tac_toe_board, 'X'):
                        print("Player wins!")
                        break
                
                # AI move
                tic_tac_toe_ai_move()
                print_tic_tac_toe_board()
                if check_tic_tac_toe_winner(tic_tac_toe_board, 'O'):
                    print("AI wins!")
                    break
        
        elif game_choice == '2':
            # Snake game loop
            reset_snake_game()
            while True:
                if game_over:
                    display_time_and_date()
                    reset_snake_game()
                
                draw_snake()
                move_snake()
                time.sleep(0.1)

if __name__ == '__main__':
    main()
