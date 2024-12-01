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
import threading

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

def loading_animation(stop_event):
    """Display a loading animation."""
    animation = "|/-\\"
    idx = 0
    while not stop_event.is_set():
        print(f"\rDownloading video... {animation[idx % len(animation)]}", end="")
        idx += 1
        time.sleep(0.1)
    print("\rDownload complete!          ")

def download_video(url, download_path):
    """Download video from YouTube using yt-dlp."""
    # Set cache directory to a writable location
    os.environ['XDG_CACHE_HOME'] = os.path.abspath('yt-dlp-cache')
    
    ydl_opts = {
        'format': 'worst[ext=mp4]',  # Get lowest quality mp4
        'quiet': True,
        'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),  # Save to specified path
    }
    
    stop_event = threading.Event()
    animation_thread = threading.Thread(target=loading_animation, args=(stop_event,))
    animation_thread.start()
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        print(f"Error downloading video: {str(e)}")
    finally:
        stop_event.set()
        animation_thread.join()

def stream_youtube_videos(urls, matrix):
    """Stream YouTube videos to LED matrix."""
    download_path = os.path.abspath('downloaded_videos')
    try:
        os.makedirs(download_path, exist_ok=True)
    except Exception as e:
        print(f"Error creating directory {download_path}: {str(e)}")
        return
    
    try:
        for url, title in urls:
            print(f"\nPreparing to play: {title}")
            
            download_video(url, download_path)
            
            video_file = os.path.join(download_path, f"{title}.mp4")
            if not os.path.exists(video_file):
                print(f"Video file not found: {video_file}")
                continue
            
            print("\nInitializing playback...")
            
            # Open video capture
            cap = cv2.VideoCapture(video_file)
            
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
