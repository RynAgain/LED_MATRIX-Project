import os
import sys
import time
import csv
import logging
from PIL import Image
from src.display._shared import should_stop
import cv2
import numpy as np
import yt_dlp
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def read_urls_from_csv(file_path):
    """Read YouTube URLs and durations from a CSV file."""
    urls = []
    try:
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                urls.append((row['url'], row.get('title', 'Unknown'), row.get('duration', 'x')))
        return urls
    except Exception as e:
        print(f"Error reading CSV file: {str(e)}")
        sys.exit(1)

# Target frame rate for video playback
TARGET_FPS = 30
FRAME_INTERVAL = 1.0 / TARGET_FPS  # ~0.033s per frame


def stream_video(url):
    """Stream video using yt_dlp and return the video URL.
    
    Requests the lowest reasonable quality since we resize to 64x64 anyway.
    This reduces bandwidth and decode time significantly.
    """
    ydl_opts = {
        # Prefer lowest resolution with video+audio, fallback to best
        'format': 'worst[ext=mp4]/worst/best[height<=480]/best',
        'quiet': True,
        'nocache': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        video_url = info_dict['url']
    return video_url

def stream_youtube_videos(urls, matrix):
    """Stream YouTube videos to LED matrix."""
    try:
        for url, title, duration in urls:
            print(f"\nPreparing to play: {title}")
            
            # Stream video
            video_url = stream_video(url)
            print(f"Streaming video from: {video_url}")
            
            # Open video capture from URL
            cap = cv2.VideoCapture(video_url)
            
            if not cap.isOpened():
                print(f"Failed to open video stream: {video_url}")
                continue
            
            print("Playback started!")
            print("Press Ctrl+C to skip to next video")
            
            start_time = time.time()  # Start the timer
            
            # Determine playback duration
            max_duration = None
            if duration.lower() != 'x':
                try:
                    max_duration = float(duration) * 60  # Convert minutes to seconds
                except ValueError:
                    print(f"Invalid duration '{duration}' for video '{title}'. Playing full video.")
            
            while cap.isOpened():
                frame_start = time.time()
                
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Check if the specified duration has passed
                elapsed_time = time.time() - start_time
                if max_duration and elapsed_time > max_duration:
                    print("Specified playback time reached. Stopping video.")
                    break
                
                # Resize frame to 64x64 (INTER_NEAREST is fastest for downscale)
                frame = cv2.resize(frame, (64, 64), interpolation=cv2.INTER_NEAREST)
                
                # Convert from BGR to RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Convert to PIL Image
                image = Image.fromarray(frame)
                
                # Display on matrix
                matrix.SetImage(image)
                
                # Maintain target frame rate (~30 FPS)
                elapsed = time.time() - frame_start
                sleep_time = FRAME_INTERVAL - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
            
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
    # Default CSV file path resolved relative to project root
    csv_path = os.path.join(PROJECT_ROOT, "config", "youtube_urls.csv")

    # Allow custom CSV file path from command line
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    
    # Read URLs and start streaming
    print(f"\nReading URLs from: {csv_path}")
    urls = read_urls_from_csv(csv_path)
    print(f"Found {len(urls)} videos to play")
    
    stream_youtube_videos(urls, matrix)

def run(matrix, duration=60):
    """Run the YouTube Stream display feature for the specified duration.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds.
    """
    logger = logging.getLogger(__name__)
    csv_path = os.path.join(PROJECT_ROOT, "config", "youtube_urls.csv")
    start_time = time.time()
    try:
        urls = read_urls_from_csv(csv_path)
        if not urls:
            logger.warning("No YouTube URLs found in %s", csv_path)
            return

        for url, title, dur in urls:
            if time.time() - start_time >= duration:
                break
            if should_stop():
                break

            logger.info("Preparing to play: %s", title)
            try:
                video_url = stream_video(url)
            except Exception as e:
                logger.error("Failed to get stream URL for %s: %s", title, e)
                continue

            cap = cv2.VideoCapture(video_url)
            if not cap.isOpened():
                logger.error("Failed to open video stream: %s", video_url)
                continue

            # Per-video max duration from CSV
            max_vid_duration = None
            if dur.lower() != 'x':
                try:
                    max_vid_duration = float(dur) * 60
                except ValueError:
                    pass

            vid_start = time.time()
            while cap.isOpened():
                frame_start = time.time()
                
                if time.time() - start_time >= duration:
                    break
                if should_stop():
                    break
                if max_vid_duration and time.time() - vid_start >= max_vid_duration:
                    break

                ret, frame = cap.read()
                if not ret:
                    break

                # INTER_NEAREST is fastest for extreme downscaling
                frame = cv2.resize(frame, (64, 64), interpolation=cv2.INTER_NEAREST)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame)
                matrix.SetImage(image)
                
                # Maintain target frame rate (~30 FPS)
                elapsed = time.time() - frame_start
                sleep_time = FRAME_INTERVAL - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            cap.release()

    except Exception as e:
        logger.error("Error in youtube_stream: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass


if __name__ == "__main__":
    print("This module should be imported and used with the LED matrix.")
    print("Please run consolidated_games.py instead.")
