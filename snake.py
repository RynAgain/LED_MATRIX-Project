import random
import logging
from PIL import Image, ImageDraw

# Snake game variables
snake = [(32, 32), (32, 31), (32, 30)]  # Start with a longer snake
direction = (0, 1)
food = (random.randint(0, 63), random.randint(0, 63))
game_over = False

def draw_snake(matrix):
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
    """Move the snake towards the food."""
    global game_over, food, direction
    head_x, head_y = snake[0]
    
    # Always pursue food
    if head_x < food[0]:
        new_head = (head_x + 1, head_y)
    elif head_x > food[0]:
        new_head = (head_x - 1, head_y)
    elif head_y < food[1]:
        new_head = (head_x, head_y + 1)
    else:
        new_head = (head_x, head_y - 1)
    
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
