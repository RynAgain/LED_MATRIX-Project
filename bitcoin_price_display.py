import requests
import time
from PIL import Image, ImageDraw, ImageFont
from rgbmatrix import graphics

def display_bitcoin_price_on_matrix(matrix, canvas, price):
    """Display Bitcoin price on the LED matrix using PIL."""
    # Create an image for the matrix
    image = Image.new("RGB", (64, 64))
    draw = ImageDraw.Draw(image)
    
    # Try to load a font, fall back to default if not available
    try:
        font = ImageFont.truetype("arial.ttf", 8)
    except IOError:
        font = ImageFont.load_default()
    
    # Format the price text
    price_text = f"BTC: ${price}"
    
    # Draw the text on the image
    draw.text((2, 20), price_text, font=font, fill=(255, 215, 0))  # Gold color
    draw.text((2, 35), "USD", font=font, fill=(255, 255, 255))
    
    # Display the image on the matrix
    matrix.SetImage(image)

def fetch_bitcoin_price():
    url = "https://api.coindesk.com/v1/bpi/currentprice/BTC.json"
    try:
        response = requests.get(url)
        data = response.json()
        price = data['bpi']['USD']['rate']
        return price
    except Exception as e:
        print(f"Error fetching Bitcoin price: {e}")
        return None

def main(matrix, canvas):
    start_time = time.time()
    while time.time() - start_time < 60:
        price = fetch_bitcoin_price()
        if price:
            display_bitcoin_price_on_matrix(matrix, canvas, price)
        time.sleep(10)  # Update every 10 seconds
