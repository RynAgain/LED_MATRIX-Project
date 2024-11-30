import time
import random
import logging
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

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

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

def check_tic_tac_toe_draw(board):
    """Check if the Tic-Tac-Toe game is a draw."""
    return all(cell != ' ' for cell in board)

def tic_tac_toe_ai_move(player):
    """Make a move for the AI in Tic-Tac-Toe."""
    available_moves = [i for i, cell in enumerate(tic_tac_toe_board) if cell == ' ']
    if available_moves:  # Ensure there are available moves
        move = random.choice(available_moves)
        tic_tac_toe_board[move] = player
        logging.debug(f"Player {player} moved to position {move}")

def reset_tic_tac_toe_board():
    """Reset the Tic-Tac-Toe board for a new game."""
    global tic_tac_toe_board
    tic_tac_toe_board = [' ' for _ in range(9)]
    logging.info("Tic-Tac-Toe board reset")

# Snake game variables
snake = [(32, 32), (32, 31), (32, 30)]  # Start with a longer snake
direction = (0, 1)
food = (random.randint(0, 63), random.randint(0, 63))
game_over = False

def generate_hamiltonian_path():
    """Generate a Hamiltonian path for a 64x64 grid."""
    path = []
    for y in range(64):
        if y % 2 == 0:
            # Left to right on even rows
            for x in range(64):
                path.append((x, y))
        else:
            # Right to left on odd rows
            for x in range(63, -1, -1):
                path.append((x, y))
    return path

hamiltonian_path = generate_hamiltonian_path()

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
    global game_over, food, direction
    head_x, head_y = snake[0]
    
    # Follow the Hamiltonian path
    current_index = hamiltonian_path.index((head_x, head_y))
    next_index = (current_index + 1) % len(hamiltonian_path)
    new_head = hamiltonian_path[next_index]
    
    # Check for collisions
    if new_head in snake:
        game_over = True
        logging.warning("Snake game over due to collision")
        return
    
    # Check for food
    if new_head == food:
        snake.insert(0, new_head)
        # Ensure food is not placed on the snake
        while food in snake:
            food = (random.randint(0, 63), random.randint(0, 63))
        logging.info("Snake ate food")
    else:
        snake.insert(0, new_head)
        snake.pop()

def reset_snake_game():
    """Reset the Snake game for a new game."""
    global snake, direction, game_over
    snake = [(32, 32), (32, 31), (32, 30)]  # Reset with a longer snake
    direction = (0, 1)
    game_over = False
    logging.info("Snake game reset")

# Pong game variables
paddle1_y = 28
paddle2_y = 28
ball_pos = [32, 32]
ball_dir = [1, 1]
paddle_height = 8

def draw_pong():
    """Draw the Pong game on the LED matrix."""
    image = Image.new("RGB", (64, 64))
    draw = ImageDraw.Draw(image)
    
    # Draw paddles
    draw.rectangle((2, paddle1_y, 4, paddle1_y + paddle_height), fill=(255, 255, 255))
    draw.rectangle((60, paddle2_y, 62, paddle2_y + paddle_height), fill=(255, 255, 255))
    
    # Draw ball
    draw.rectangle((ball_pos[0], ball_pos[1], ball_pos[0] + 2, ball_pos[1] + 2), fill=(255, 255, 0))
    
    matrix.SetImage(image)

def move_pong():
    """Move the ball and paddles in the Pong game."""
    global ball_pos, ball_dir, paddle1_y, paddle2_y
    
    # Move ball
    ball_pos[0] += ball_dir[0]
    ball_pos[1] += ball_dir[1]
    
    # Ball collision with top and bottom
    if ball_pos[1] <= 0 or ball_pos[1] >= 62:
        ball_dir[1] = -ball_dir[1]
    
    # Ball collision with paddles
    if ball_pos[0] <= 4 and paddle1_y <= ball_pos[1] <= paddle1_y + paddle_height:
        ball_dir[0] = -ball_dir[0]
    elif ball_pos[0] >= 58 and paddle2_y <= ball_pos[1] <= paddle2_y + paddle_height:
        ball_dir[0] = -ball_dir[0]
    
    # Ball out of bounds
    if ball_pos[0] < 0 or ball_pos[0] > 64:
        ball_pos = [32, 32]  # Reset ball position
        ball_dir = [random.choice([-1, 1]), random.choice([-1, 1])]  # Randomize direction
    
    # Simple AI for paddle1
    if ball_pos[1] > paddle1_y + paddle_height // 2:
        paddle1_y += 1
    elif ball_pos[1] < paddle1_y + paddle_height // 2:
        paddle1_y -= 1
    
    # Simple AI for paddle2
    if ball_pos[1] > paddle2_y + paddle_height // 2:
        paddle2_y += 1
    elif ball_pos[1] < paddle2_y + paddle_height // 2:
        paddle2_y -= 1
    
    # Ensure paddles stay within bounds
    paddle1_y = max(0, min(56, paddle1_y))
    paddle2_y = max(0, min(56, paddle2_y))

def reset_pong_game():
    """Reset the Pong game for a new game."""
    global paddle1_y, paddle2_y, ball_pos, ball_dir
    paddle1_y = 28
    paddle2_y = 28
    ball_pos = [32, 32]
    ball_dir = [1, 1]
    logging.info("Pong game reset")

def display_time_and_date():
    """Display the current time and date on the LED matrix."""
    end_time = time.time() + 60  # Display for 1 minute
    while time.time() < end_time:
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        current_date = now.strftime("%Y-%m-%d")
        
        image = Image.new("RGB", (64, 64))
        draw = ImageDraw.Draw(image)
        
        # Load a custom font
        try:
            font = ImageFont.truetype("arial.ttf", 10)
        except IOError:
            font = ImageFont.load_default()
        
        # Draw time with a gradient color
        for i, char in enumerate(current_time):
            draw.text((i * 10, 0), char, font=font, fill=(255 - i * 20, 100 + i * 15, 150))
        
        # Draw date with a different color
        draw.text((0, 32), current_date, font=font, fill=(0, 255, 255))
        
        matrix.SetImage(image)
        time.sleep(1)

def main():
    """Main game loop."""
    global game_over
    while True:
        # Play Tic-Tac-Toe
        for _ in range(10):  # Play 10 games of Tic-Tac-Toe
            reset_tic_tac_toe_board()
            print_tic_tac_toe_board()
            while True:
                # AI move for 'X'
                tic_tac_toe_ai_move('X')
                print_tic_tac_toe_board()
                time.sleep(1)  # Slow down the game for visibility
                if check_tic_tac_toe_winner(tic_tac_toe_board, 'X'):
                    logging.info("Player X wins")
                    break
                if check_tic_tac_toe_draw(tic_tac_toe_board):
                    logging.info("Game is a draw")
                    break
                
                # AI move for 'O'
                tic_tac_toe_ai_move('O')
                print_tic_tac_toe_board()
                time.sleep(1)  # Slow down the game for visibility
                if check_tic_tac_toe_winner(tic_tac_toe_board, 'O'):
                    logging.info("Player O wins")
                    break
                if check_tic_tac_toe_draw(tic_tac_toe_board):
                    logging.info("Game is a draw")
                    break
        
        # Snake game loop
        reset_snake_game()
        while not game_over:
            draw_snake()
            move_snake()
            time.sleep(0.1)
        
        # Pong game loop
        reset_pong_game()
        for _ in range(100):  # Play Pong for 100 iterations
            draw_pong()
            move_pong()
            time.sleep(0.05)
        
        # Display time and date
        display_time_and_date()
        
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
