import os
import sys
import time
import csv
from PIL import Image
import cv2
import numpy as np
import yt_dlp
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

def download_video(url):
    """Download video using yt_dlp and return the file path."""
    ydl_opts = {
        'format': 'best',
        'outtmpl': 'downloaded_videos/%(title)s.%(ext)s',
        'quiet': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        video_path = ydl.prepare_filename(info_dict)
    return video_path

def stream_youtube_videos(urls, matrix):
    """Stream YouTube videos to LED matrix."""
    try:
        for url, title in urls:
            print(f"\nPreparing to play: {title}")
            
            # Download video
            video_path = download_video(url)
            print(f"Downloaded video to: {video_path}")
            
            # Open video capture from file
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                print(f"Failed to open video stream: {video_path}")
                continue
            
            print("Playback started!")
            print("Press Ctrl+C to skip to next video")
            
            start_time = time.time()  # Start the timer
            
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Check if 3 minutes have passed
                elapsed_time = time.time() - start_time
                if elapsed_time > 180:  # 180 seconds = 3 minutes
                    print("Maximum playback time reached. Stopping video.")
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
