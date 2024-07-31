import logging
import os
import re
import yt_dlp
from pyrogram import Client, filters, errors
from threading import Thread
from queue import Queue
from flask import Flask
import shutil
import time

# Configure logging
logging.basicConfig(level=logging.INFO)

# Define paths
session_file_path = "my_bot.session"
VIDEO_DIR = "./sentvideo_in_telegram/"
OTP_USER_ID = "NEPALESEN00B"  # Replace with the actual user ID

# Create the video directory if it doesn't exist
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
            logging.info("Worker thread: Waiting for next YouTube link...")
            chat_id, youtube_url = youtube_links_queue.get()  # Get the next item from the queue
            logging.info(f"Worker thread: Processing link {youtube_url} for chat_id {chat_id}")

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

            logging.info(f"Video downloaded successfully: {video_file_path}")

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
                    logging.info(f"Video sent successfully: {video_file_path}")
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
    logging.info(f"Received message from chat_id {chat_id}: {message.text}")
    youtube_url_match = re.search(youtube_url_pattern, message.text)
    youtube_url = youtube_url_match.group(0)
    logging.info(f"Detected YouTube URL: {youtube_url}")
    # Delete the YouTube link message immediately
    client.delete_messages(chat_id=chat_id, message_ids=[message.id])
    logging.info(f"Deleted message with YouTube URL from chat_id {chat_id}")
    youtube_links_queue.put((chat_id, youtube_url))  # Add the tuple to the queue

# Function to create a new session
def create_session(client):
    # Start the client to get the OTP
    client.start()
    logging.info("Bot started. Please send the OTP to the bot.")

    # Wait for OTP
    @client.on_message(filters.text)
    def handle_otp(client, message):
        if message.from_user.username == OTP_USER_ID:
            otp = message.text
            logging.info(f"Received OTP: {otp}")
            # Authenticate with the OTP
            client.sign_in(phone_number=api_id, phone_code=otp)
            logging.info("OTP verified successfully.")
            client.send_message(OTP_USER_ID, "Nice, now I am running well.")
            client.stop()
            logging.info("Session created and verified. Bot is now running.")

    client.idle()  # Keep the bot running to receive OTP

# Start the Pyrogram client and the worker thread
if __name__ == "__main__":
    # Initialize the Pyrogram client
    app = Client("my_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)
    
    # If the session file exists, start the bot directly
    if os.path.exists(session_file_path):
        logging.info("Session file found. Starting bot...")
        app.start()
        worker_thread = Thread(target=process_youtube_links)
        worker_thread.start()
    else:
        # Create a new session if the file does not exist
        logging.info("No session file found. Creating new session...")
        create_session(app)

    # Initialize Flask app
    flask_app = Flask(__name__)

    @flask_app.route('/')
    def home():
        return "Bot is running."

    # Start Flask app
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
            
