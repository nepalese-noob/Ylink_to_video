import logging
import os
import re
import yt_dlp
from pyrogram import Client, filters
from threading import Thread
from queue import Queue
import time
import shutil
from flask import Flask, request

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize the Pyrogram client with environment variables
api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

app = Client("my_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# Define the directory where videos are saved
VIDEO_DIR = "/tmp/sentvideo_in_telegram/"

# Create the directory if it doesn't exist
if not os.path.exists(VIDEO_DIR):
    os.makedirs(VIDEO_DIR)

# Define YouTube URL pattern
youtube_url_pattern = r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+'

# Queue to hold tuples of (chat_id, YouTube link)
youtube_links_queue = Queue()

# Retry delay in seconds
RETRY_DELAY = 5

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
            logging.info(f"Processing YouTube URL: {youtube_url} for chat_id: {chat_id}")

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

            logging.info(f"Downloaded video file: {video_file_path}")

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
                    logging.info(f"Sent video to chat_id: {chat_id}, message_id: {sent_message.id}")
                    # Pin the video message
                    app.pin_chat_message(chat_id=chat_id, message_id=sent_message.id)
                    logging.info(f"Pinned video message: {sent_message.id} in chat_id: {chat_id}")
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
    logging.info(f"Received YouTube URL: {youtube_url} from chat_id: {chat_id}")
    # Delete the YouTube link message immediately
    client.delete_messages(chat_id=chat_id, message_ids=[message.id])
    youtube_links_queue.put((chat_id, youtube_url))  # Add the tuple to the queue

# Flask app setup
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "Telegram Bot is running."

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    logging.info(f"Received update: {update}")
    app.process_update(update)
    return "ok", 200

if __name__ == "__main__":
    # Delete the session file each time the bot starts (optional)
    session_file_path = "my_bot.session"
    if os.path.exists(session_file_path):
        os.remove(session_file_path)
        logging.info(f"Deleted existing session file: {session_file_path}")

    # Start the worker thread
    worker_thread = Thread(target=process_youtube_links)
    worker_thread.start()

    # Start the Flask app
    flask_app.run(host='0.0.0.0', port=5000)
