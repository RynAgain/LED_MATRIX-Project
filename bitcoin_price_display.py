import requests
import time

def display_bitcoin_price():
    url = "https://api.coindesk.com/v1/bpi/currentprice/BTC.json"
    try:
        response = requests.get(url)
        data = response.json()
        price = data['bpi']['USD']['rate']
        print(f"Current Bitcoin Price in USD: ${price}")
    except Exception as e:
        print(f"Error fetching Bitcoin price: {e}")

def main():
    start_time = time.time()
    while time.time() - start_time < 60:
        display_bitcoin_price()
        time.sleep(10)  # Update every 10 seconds

if __name__ == "__main__":
    main()
