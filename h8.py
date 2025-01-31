import logging
import os
import re
import yt_dlp
from flask import Flask
from pyrogram import Client, filters
from threading import Thread
from queue import Queue
import time
import shutil
import sqlite3

# Flask web server for Render keep-alive
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running on Render!"

# Configure logging
logging.basicConfig(level=logging.INFO)

# Environment Variables (Set these in Render Dashboard)
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Initialize the Pyrogram client
bot = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Define the directory where videos are saved
VIDEO_DIR = "downloads/"
if not os.path.exists(VIDEO_DIR):
    os.makedirs(VIDEO_DIR)

# Define YouTube URL pattern
youtube_url_pattern = r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+'

# Queue to hold tuples of (chat_id, YouTube link)
youtube_links_queue = Queue()

# Retry delay in seconds
RETRY_DELAY = 5

# Function to reset the database (optional)
def reset_database():
    try:
        connection = sqlite3.connect('database.db')
        cursor = connection.cursor()
        cursor.execute("DELETE FROM downloads")  # Modify as per DB schema
        connection.commit()
        logging.info("Database reset successfully.")
    except Exception as e:
        logging.error(f"Error resetting database: {e}")
    finally:
        connection.close()

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
            chat_id, youtube_url = youtube_links_queue.get()

            # Download the video using yt-dlp
            ydl_opts = {
                'format': 'bestvideo+bestaudio/best',
                'outtmpl': VIDEO_DIR + '%(title)s.%(ext)s',
                'postprocessors': [{'key': 'FFmpegMetadata'}],
                'noplaylist': True,
                'nocheckcertificate': True
            }

            retries = 0
            video_file_path = None
            while retries < 3:
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info_dict = ydl.extract_info(youtube_url, download=True)
                        video_title = info_dict.get('title', None)
                        video_file_path = ydl.prepare_filename(info_dict)
                    break
                except yt_dlp.utils.DownloadError as e:
                    logging.error(f"Download error: {e}")
                    retries += 1
                    time.sleep(RETRY_DELAY)

            if not video_file_path or not os.path.exists(video_file_path):
                logging.error("No video files found after download.")
                youtube_links_queue.task_done()
                continue

            retries = 0
            while retries < 3:
                try:
                    # Send the video
                    sent_message = bot.send_video(
                        chat_id=chat_id,
                        video=video_file_path,
                        caption=video_title,
                        supports_streaming=True
                    )
                    bot.pin_chat_message(chat_id=chat_id, message_id=sent_message.id)
                    clear_video_directory()
                    break
                except Exception as e:
                    logging.error(f"Failed to send video: {e}")
                    retries += 1
                    time.sleep(RETRY_DELAY)

            youtube_links_queue.task_done()

        except Exception as e:
            logging.error(f"Unexpected error in processing: {e}")

# Function to handle incoming messages
@bot.on_message(filters.text & filters.regex(youtube_url_pattern))
def handle_message(client, message):
    chat_id = message.chat.id
    youtube_url_match = re.search(youtube_url_pattern, message.text)
    youtube_url = youtube_url_match.group(0)
    client.delete_messages(chat_id=chat_id, message_ids=[message.id])
    youtube_links_queue.put((chat_id, youtube_url))

# Setup function
def setup():
    reset_database()
    clear_video_directory()

# Start bot and worker
def start_bot():
    setup()
    worker_thread = Thread(target=process_youtube_links)
    worker_thread.start()
    bot.run()

# Run Flask and bot
if __name__ == "__main__":
    Thread(target=start_bot).start()
    app.run(host="0.0.0.0", port=8080)
    
