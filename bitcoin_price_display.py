import requests
import time
from rgbmatrix import FrameCanvas

def display_bitcoin_price_on_matrix(matrix, canvas, price):
    canvas.Clear()
    # Assuming a method to draw text on the canvas, e.g., canvas.DrawText(...)
    # This is a placeholder for actual text drawing logic
    # You might need to implement or use an existing method to draw text
    # For example: canvas.DrawText(font, x, y, color, text)
    # Here, we assume a simple print to console as a placeholder
    print(f"Displaying on matrix: Current Bitcoin Price in USD: ${price}")
    canvas = matrix.SwapOnVSync(canvas)

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
