import logging
import os
import re
import yt_dlp
from pyrogram import Client, filters
from threading import Thread
from queue import Queue
import time
import requests
import ntplib
from datetime import datetime
from flask import Flask

# Configure logging
logging.basicConfig(level=logging.INFO)

# Define the path to the session file
session_file_path = "my_bot.session"

# Initialize the Pyrogram client
api_id = os.environ["API_ID"]
api_hash = os.environ["API_HASH"]
bot_token = os.environ["BOT_TOKEN"]

app = Client("my_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# Define the directory where videos are saved
VIDEO_DIR = "sent_video_in_telegram/"
# Define YouTube URL pattern
youtube_url_pattern = r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+'

# Queue to hold tuples of (chat_id, YouTube link)
youtube_links_queue = Queue()

# Retry delay in seconds
RETRY_DELAY = 5

# Flask app to keep the web service alive
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "Telegram Bot is running!"

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

# Function to synchronize time
def synchronize_time():
    try:
        # Try to get time from the system
        system_time = datetime.utcnow()
        logging.info(f"System time: {system_time}")
        return system_time
    except Exception as e:
        logging.error(f"Failed to get system time: {e}")

    try:
        # Try to get time from NTP servers
        client = ntplib.NTPClient()
        response = client.request('pool.ntp.org')
        ntp_time = datetime.utcfromtimestamp(response.tx_time)
        logging.info(f"NTP time: {ntp_time}")
        return ntp_time
    except Exception as e:
        logging.error(f"Failed to get NTP time: {e}")

    try:
        # Try to get time from websites
        response = requests.get('http://worldtimeapi.org/api/timezone/Etc/UTC')
        website_time = datetime.fromisoformat(response.json()['datetime'])
        logging.info(f"Website time (worldtimeapi): {website_time}")
        return website_time
    except Exception as e:
        logging.error(f"Failed to get time from worldtimeapi: {e}")

    try:
        response = requests.get('http://worldclockapi.com/api/json/utc/now')
        website_time = datetime.fromisoformat(response.json()['currentDateTime'])
        logging.info(f"Website time (worldclockapi): {website_time}")
        return website_time
    except Exception as e:
        logging.error(f"Failed to get time from worldclockapi: {e}")

    try:
        response = requests.get('https://timeapi.io/api/Time/current/zone?timeZone=UTC')
        website_time = datetime.fromisoformat(response.json()['dateTime'])
        logging.info(f"Website time (timeapi.io): {website_time}")
        return website_time
    except Exception as e:
        logging.error(f"Failed to get time from timeapi.io: {e}")

    # If all methods fail, raise an exception
    raise Exception("Failed to synchronize time from all sources")

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
                        time.sleep(RETRY_DELAY)
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
                        time.sleep(RETRY_DELAY)
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

if __name__ == "__main__":
    # Start Flask app in a separate thread
    flask_thread = Thread(target=lambda: flask_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000))))
    flask_thread.start()

    # Synchronize time before starting the Pyrogram client
    try:
        synchronized_time = synchronize_time()
        logging.info(f"Synchronized time: {synchronized_time}")
    except Exception as e:
        logging.error(f"Time synchronization failed: {e}")
        exit(1)  # Exit if time synchronization fails

    # Start the Pyrogram client
    app.start()

    # Start the worker thread
    worker_thread = Thread(target=process_youtube_links)
    worker_thread.start()

    # Keep the client running
    app.idle()
