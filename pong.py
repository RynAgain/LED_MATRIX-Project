import random
import logging
import time
from PIL import Image, ImageDraw

# Pong game variables
paddle1_y = 28
paddle2_y = 28
ball_pos = [32, 32]
ball_dir = [1, 1]
ball_speed = 1
max_ball_speed = 3  # Lower the maximum speed of the ball
paddle_height = 8
max_paddle_speed = 3  # Increase paddle speed
pong_game_over = False
pass_count = 0  # Counter for successful passes
min_paddle_height = 2  # Minimum paddle height to prevent disappearing

def draw_pong(matrix):
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
    global ball_pos, ball_dir, ball_speed, paddle1_y, paddle2_y, pong_game_over, pass_count, paddle_height
    
    # Move ball
    ball_pos[0] += ball_dir[0] * ball_speed
    ball_pos[1] += ball_dir[1] * ball_speed
    
    # Ball collision with top and bottom
    if ball_pos[1] <= 0 or ball_pos[1] >= 62:
        ball_dir[1] = -ball_dir[1]
    
    # Ball collision with paddles
    if ball_pos[0] <= 4 and paddle1_y <= ball_pos[1] <= paddle1_y + paddle_height:
        ball_dir[0] = -ball_dir[0]
        ball_speed = min(max_ball_speed, ball_speed + 0.2)  # Reduce speed increment
        pass_count += 1
    elif ball_pos[0] >= 58 and paddle2_y <= ball_pos[1] <= paddle2_y + paddle_height:
        ball_dir[0] = -ball_dir[0]
        ball_speed = min(max_ball_speed, ball_speed + 0.2)  # Reduce speed increment
        pass_count += 1
    
    # Check if it's time to shrink the paddles
    if pass_count >= 10:
        paddle_height = max(min_paddle_height, paddle_height - 1)
        pass_count = 0
    
    # Ball out of bounds
    if ball_pos[0] < 0 or ball_pos[0] > 64:
        pong_game_over = True
        logging.info("Pong game over")
        return
    
    # Simple AI for paddle1 with randomness
    if ball_dir[0] > 0:  # Ball moving away from paddle1
        if random.random() < 0.1:  # Small chance to move randomly
            paddle1_y += random.choice([-1, 1])
    else:  # Ball moving towards paddle1
        if ball_pos[1] > paddle1_y + paddle_height // 2:
            paddle1_y += min(max_paddle_speed, ball_pos[1] - (paddle1_y + paddle_height // 2))
        elif ball_pos[1] < paddle1_y + paddle_height // 2:
            paddle1_y -= min(max_paddle_speed, (paddle1_y + paddle_height // 2) - ball_pos[1])
    
    # Simple AI for paddle2 with randomness
    if ball_dir[0] < 0:  # Ball moving away from paddle2
        if random.random() < 0.1:  # Small chance to move randomly
            paddle2_y += random.choice([-1, 1])
    else:  # Ball moving towards paddle2
        if ball_pos[1] > paddle2_y + paddle_height // 2:
            paddle2_y += min(max_paddle_speed, ball_pos[1] - (paddle2_y + paddle_height // 2))
        elif ball_pos[1] < paddle2_y + paddle_height // 2:
            paddle2_y -= min(max_paddle_speed, (paddle2_y + paddle_height // 2) - ball_pos[1])
    
    # Ensure paddles stay within bounds
    paddle1_y = max(0, min(56, paddle1_y))
    paddle2_y = max(0, min(56, paddle2_y))

def reset_pong_game():
    """Reset the Pong game for a new game."""
    global paddle1_y, paddle2_y, ball_pos, ball_dir, ball_speed, pong_game_over, paddle_height, pass_count
    paddle1_y = 28
    paddle2_y = 28
    ball_pos = [32, 32]
    ball_dir = [random.choice([-1, 1]), random.choice([-1, 1])]  # Randomize initial direction
    ball_speed = 1
    pong_game_over = False
    paddle_height = 8  # Reset paddle height
    pass_count = 0  # Reset pass count
    logging.info("Pong game reset")

def play_pong(matrix):
    """Play the Pong game for 3 full games."""
    global pong_game_over
    games_played = 0
    while games_played < 1:
        reset_pong_game()  # Ensure game state is reset before each game
        while not pong_game_over:
            move_pong()
            draw_pong(matrix)
            time.sleep(0.05)  # Add delay to control game speed
        games_played += 1
        logging.info(f"Game {games_played} completed")
