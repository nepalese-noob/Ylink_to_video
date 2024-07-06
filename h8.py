import logging
import os
import re
import yt_dlp
from pyrogram import Client, filters
from threading import Thread
from queue import Queue
import requests
import shutil
from flask import Flask
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)

# Define the path to the session file
session_file_path = "my_bot.session"

# Initialize the Pyrogram client
api_id = "22519301"
api_hash = "1a503c6dce6195a37e082a88f7e20dd5"
bot_token = "6960079953:AAFMvhZBsE-FKV-gCaq8oJByGkHFjFhmes8"
app = Client("my_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# Define the directory where videos are saved (in the same directory as the script)
VIDEO_DIR = os.path.join(os.path.dirname(__file__), "sentvideo_in_telegram/")
os.makedirs(VIDEO_DIR, exist_ok=True)  # Create the directory if it doesn't exist

# Define YouTube URL pattern
youtube_url_pattern = r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+'

# Queue to hold tuples of (chat_id, YouTube link)
youtube_links_queue = Queue()

# Retry delay in seconds
RETRY_DELAY = 5

# List of time API URLs
time_api_urls = [
    'http://worldtimeapi.org/api/timezone/Etc/UTC',
    'https://timeapi.io/api/Time/current/zone?timeZone=Etc/UTC',
    'https://worldtimeapi.org/api/timezone/Etc/GMT',
    'http://worldclockapi.com/api/json/utc/now',
    'https://www.timeapi.io/api/Time/current/zone?timeZone=Etc/GMT',
    'https://api.timezonedb.com/v2.1/get-time-zone?key=0H0RX6SCXA7T&format=json&by=zone&zone=Etc/UTC',
    'https://www.timeapi.io/api/Time/current/zone?timeZone=UTC',
    'https://worldtimeapi.org/api/ip',
    'http://worldtimeapi.org/api/timezone/Etc/GMT+0',
    'http://worldclockapi.com/api/json/est/now',
    'http://worldclockapi.com/api/json/pst/now',
    'https://api.ipgeolocation.io/timezone?apiKey=3e90fca262914fc98fe4a8ded86b52b6&tz=Etc/UTC',
    'http://worldtimeapi.org/api/timezone/Etc/Greenwich',
    'http://worldtimeapi.org/api/timezone/Etc/GMT0',
    'http://worldtimeapi.org/api/timezone/Etc/UCT',
    'http://worldtimeapi.org/api/timezone/Etc/Universal',
    'http://worldtimeapi.org/api/timezone/Etc/Zulu',
    'https://timeapi.io/api/Time/current/zone?timeZone=Etc/Greenwich',
    'https://timeapi.io/api/Time/current/zone?timeZone=Etc/GMT+0',
    'https://timeapi.io/api/Time/current/zone?timeZone=Etc/GMT0',
    'https://timeapi.io/api/Time/current/zone?timeZone=Etc/UCT',
    'https://timeapi.io/api/Time/current/zone?timeZone=Etc/Universal',
    'https://timeapi.io/api/Time/current/zone?timeZone=Etc/Zulu',
    'https://api.ipgeolocation.io/timezone?apiKey=3e90fca262914fc98fe4a8ded86b52b6&tz=Etc/GMT',
    'https://api.ipgeolocation.io/timezone?apiKey=3e90fca262914fc98fe4a8ded86b52b6&tz=Etc/Greenwich',
    'https://api.ipgeolocation.io/timezone?apiKey=3e90fca262914fc98fe4a8ded86b52b6&tz=Etc/GMT+0',
    'https://api.ipgeolocation.io/timezone?apiKey=3e90fca262914fc98fe4a8ded86b52b6&tz=Etc/GMT0',
]

# Function to get current time from an API with retry logic
def get_current_time(retries=5):
    for i in range(retries):
        for url in time_api_urls:
            try:
                response = requests.get(url)
                response.raise_for_status()
                current_time = response.json().get('unixtime') or response.json().get('currentFileTime')
                if current_time is not None:
                    return current_time
            except requests.RequestException as e:
                logging.error(f"Failed to get time from {url}: {e}")
        if i < retries - 1:
            sleep_for(RETRY_DELAY * (2 ** i))  # Exponential backoff
    return None

# Function to sleep for a given number of seconds using external time
def sleep_for(seconds):
    start_time = get_current_time()
    if start_time is None:
        return  # If the time cannot be fetched, do not sleep
    while True:
        current_time = get_current_time()
        if current_time is None:
            return  # If the time cannot be fetched, break the loop
        if current_time - start_time >= seconds:
            break

# Function to delete all files in the video directory
def clear_video_directory():
    for filename in os.listdir(VIDEO_DIR):
        file_path = os.path.join(VIDEO_DIR, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
            logging.info(f"Deleted file: {file_path}")
        except Exception as e:
            logging.error(f"Failed to delete {file_path}. Reason: {e}")

# Worker function to process YouTube links
def process_youtube_links():
    while True:
        try:
            chat_id, youtube_url = youtube_links_queue.get()  # Get the next item from the queue

            # Download the video using yt-dlp
            ydl_opts = {
                'format': 'best',
                'outtmpl': VIDEO_DIR + '%(title)s.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegMetadata'
                }]
            }

            # Retry loop in case of download failures
            retries = 0
            while retries < 3:
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info_dict = ydl.extract_info(youtube_url, download=True)
                        video_title = info_dict.get('title', None)
                        break
                except Exception as e:
                    logging.error(f"Failed to download video: {e}")
                    retries += 1
                    if retries < 3:
                        logging.info(f"Retrying download... (Attempt {retries + 1})")
                        sleep_for(RETRY_DELAY)
                    else:
                        logging.error("Max retry attempts reached for video download.")
                        youtube_links_queue.task_done()
                        continue

            # Find the downloaded video file
            video_files = os.listdir(VIDEO_DIR)
            video_file_path = os.path.join(VIDEO_DIR, video_files[0]) if video_files else None

            if not video_file_path:
                logging.error("No video files found after download.")
                youtube_links_queue.task_done()
                continue

            # Retry loop in case of sending failures
            retries = 0
            while retries < 3:
                try:
                    # Send the video
                    sent_message = app.send_video(
                        chat_id=chat_id,
                        video=video_file_path,
                        caption=video_title,
                        supports_streaming=True
                    )
                    # Pin the video message
                    app.pin_chat_message(chat_id=chat_id, message_id=sent_message.id)
                    # Clear the video directory
                    clear_video_directory()
                    break
                except Exception as e:
                    logging.error(f"Failed to send video: {e}")
                    retries += 1
                    if retries < 3:
                        logging.info(f"Retrying to send video... (Attempt {retries + 1})")
                        sleep_for(RETRY_DELAY)
                    else:
                        logging.error("Max retry attempts reached for sending video.")
                        youtube_links_queue.task_done()
                        continue

            youtube_links_queue.task_done()

        except Exception as e:
            logging.error(f"Unexpected error in processing: {e}")

# Function to handle incoming messages
@app.on_message(filters.text & filters.regex(youtube_url_pattern))
def handle_message(client, message):
    chat_id = message.chat.id  # Get the chat_id from the incoming message
    youtube_url_match = re.search(youtube_url_pattern, message.text)
    youtube_url = youtube_url_match.group(0)
    # Delete the YouTube link message immediately
    client.delete_messages(chat_id=chat_id, message_ids=[message.id])
    youtube_links_queue.put((chat_id, youtube_url))  # Add the tuple to the queue

# Create Flask app
flask_app = Flask(__name__)

# Endpoint to check the status of the bot
@flask_app.route('/')
def index():
    return "Bot is running!"

# Start the worker thread and the Pyrogram client
async def start_bot():
    # Delete the session file each time the bot starts (optional)
    if os.path.exists(session_file_path):
        os.remove(session_file_path)
        logging.info(f"Deleted existing session file: {session_file_path}")

    # Start the worker thread
    worker_thread = Thread(target=process_youtube_links)
    worker_thread.start()

    while True:
        try:
            await app.start()
            await app.idle()  # Run the bot until manually stopped
        except Exception as e:
            logging.error(f"Bot encountered an error: {e}. Restarting...")
            await app.stop()
            sleep_for(RETRY_DELAY)  # Wait before restarting the bot

# Start the bot in a separate thread
def run_bot():
    asyncio.run(start_bot())

Thread(target=run_bot).start()

# Run the Flask app
if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=5000)
    
