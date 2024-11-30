import yt_dlp
import os
import sys
import time
import csv
from PIL import Image
import io
import cv2
import numpy as np
import urllib.request

def read_urls_from_csv(file_path):
    """Read YouTube URLs from a CSV file."""
    urls = []
    try:
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                urls.append((row['url'], row.get('title', 'Unknown')))
        return urls
    except Exception as e:
        print(f"Error reading CSV file: {str(e)}")
        sys.exit(1)

def get_frame_from_url(url):
    """Get a frame from a URL as a PIL Image."""
    try:
        # Read the image from URL
        with urllib.request.urlopen(url) as response:
            image_data = response.read()
        
        # Convert to numpy array
        nparr = np.frombuffer(image_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Resize to 64x64
        frame = cv2.resize(frame, (64, 64))
        
        # Convert from BGR to RGB
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Convert to PIL Image
        return Image.fromarray(frame)
    except Exception as e:
        print(f"Error getting frame: {str(e)}")
        return None

def stream_youtube_videos(urls, matrix):
    """Stream YouTube videos to LED matrix."""
    # Configure yt-dlp options for lowest quality to save bandwidth
    ydl_opts = {
        'format': 'worst[ext=mp4]',  # Get lowest quality mp4
        'quiet': True,
    }
    
    try:
        for url, title in urls:
            print(f"\nPreparing to play: {title}")
            print("Fetching video information...")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info['url']
                
                print(f"Video Title: {info.get('title', 'Unknown Title')}")
                print("\nInitializing playback...")
                
                # Open video capture
                cap = cv2.VideoCapture(stream_url)
                
                print("Playback started!")
                print("Press Ctrl+C to skip to next video")
                
                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    # Resize frame to 64x64
                    frame = cv2.resize(frame, (64, 64))
                    
                    # Convert from BGR to RGB
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    # Convert to PIL Image
                    image = Image.fromarray(frame)
                    
                    # Display on matrix
                    matrix.SetImage(image)
                    
                    # Control playback speed
                    time.sleep(0.1)
                
                cap.release()
                print("\nPlayback finished.")
                
    except KeyboardInterrupt:
        print("\nSkipping to next video...")
    except Exception as e:
        print(f"\nAn error occurred: {str(e)}")
        print("\nTroubleshooting tips:")
        print("1. Check your internet connection")
        print("2. Verify the YouTube URLs are valid")
        print("3. Try updating yt-dlp: pip install --upgrade yt-dlp")

def play_videos_on_matrix(matrix):
    """Main function to play videos on LED matrix."""
    # Default CSV file path
    csv_path = 'youtube_urls.csv'
    
    # Allow custom CSV file path from command line
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    
    # Read URLs and start streaming
    print(f"\nReading URLs from: {csv_path}")
    urls = read_urls_from_csv(csv_path)
    print(f"Found {len(urls)} videos to play")
    
    stream_youtube_videos(urls, matrix)

if __name__ == "__main__":
    print("This module should be imported and used with the LED matrix.")
    print("Please run consolidated_games.py instead.")
