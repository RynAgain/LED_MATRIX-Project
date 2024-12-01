import random
import logging
from PIL import Image, ImageDraw

# Tic-Tac-Toe game variables
tic_tac_toe_board = [' ' for _ in range(9)]

def print_tic_tac_toe_board(matrix):
    """Display the current Tic-Tac-Toe board on the LED matrix."""
    image = Image.new("RGB", (64, 64))
    draw = ImageDraw.Draw(image)
    
    # Draw the grid
    draw.line((21, 0, 21, 64), fill=(255, 255, 255))
    draw.line((42, 0, 42, 64), fill=(255, 255, 255))
    draw.line((0, 21, 64, 21), fill=(255, 255, 255))
    draw.line((0, 42, 64, 42, 64), fill=(255, 255, 255))
    
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
