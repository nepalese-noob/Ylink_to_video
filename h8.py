import os
import telebot
import requests
from deep_translator import GoogleTranslator
import feedparser
import logging
import threading
import time
import random
from flask import Flask, request, jsonify

# Configure logging
logging.basicConfig(level=logging.INFO)

# Fetch sensitive data from environment variables
API_KEY = os.getenv('NEWS_API_KEY')
API_URL = f'https://newsdata.io/api/1/news?apikey={API_KEY}&country=np&language=en'
FEED_URL = 'https://www.onlinekhabar.com/feed'
BOT_TOKEN = os.getenv('BOT_TOKEN')
GROUP_CHAT_ID = os.getenv('GROUP_CHAT_ID')

# Initialize Flask app
app = Flask(__name__)

# Initialize the bot with the token from environment variables
bot = telebot.TeleBot(BOT_TOKEN)

def fetch_viral_news():
    response = requests.get(API_URL)
    if response.status_code == 200:
        news_items = response.json().get('results', [])
        viral_news = [item for item in news_items if is_viral(item)]
        return viral_news
    else:
        return []

def get_most_viral_news(news_items):
    sorted_news = sorted(news_items, key=lambda x: x.get('shares', 0), reverse=True)
    if sorted_news:
        return sorted_news[0]
    else:
        return None

def is_viral(news_item):
    return True  # Placeholder condition

def translate_to_nepali(text):
    if text:
        if len(text) <= 5000:
            translated_text = GoogleTranslator(source='en', target='ne').translate(text)
            return translated_text
        else:
            last_full_stop_index = text.rfind('.', 0, 5000)
            if last_full_stop_index == -1:
                logging.info("No full stop found within the first 5000 characters. Truncating the text.")
                truncated_text = text[:5000]
            else:
                logging.info("Truncating text at the last full stop within the first 5000 characters.")
                truncated_text = text[:last_full_stop_index + 1]
            translated_text = GoogleTranslator(source='en', target='ne').translate(truncated_text)
            return translated_text
    else:
        logging.info("Input text is empty.")
    return ''

def fetch_news():
    feed = feedparser.parse(FEED_URL)
    return feed.entries

@app.route('/send_news', methods=['POST'])
def send_news():
    data = request.json
    command = data.get('command')
    
    if command == 'news':
        if random.choice([True, False]):
            news_items = fetch_news()
            if news_items:
                item = random.choice(news_items)
                bot.send_message(GROUP_CHAT_ID, f"{item.title} - {item.link}")
                logging.info(f"Sent RSS feed news: {item.title} - {item.link}")
                return jsonify({'status': 'success', 'message': f"Sent RSS feed news: {item.title} - {item.link}"}), 200
            else:
                return jsonify({'status': 'error', 'message': 'No news found from Online Khabar.'}), 404
        else:
            news_items = fetch_viral_news()
            most_viral_news = get_most_viral_news(news_items)
            if most_viral_news:
                title_nepali = translate_to_nepali(most_viral_news['title'])
                description_nepali = translate_to_nepali(most_viral_news['description'])
                message_text = f"{title_nepali} - {description_nepali}"
                bot.send_message(GROUP_CHAT_ID, message_text)
                logging.info(f"Sent viral news: {message_text}")
                return jsonify({'status': 'success', 'message': f"Sent viral news: {message_text}"}), 200
            else:
                return jsonify({'status': 'error', 'message': 'No viral news found.'}), 404
    else:
        return jsonify({'status': 'error', 'message': 'Invalid command.'}), 400

def send_onlinekhabar_news():
    sent_news = set()  # Set to store already sent news titles

    while True:
        try:
            news_items = fetch_news()
            for item in news_items:
                if item.title not in sent_news:
                    message = f"{item.title} - {item.link}"
                    bot.send_message(GROUP_CHAT_ID, message)
                    sent_news.add(item.title)
                    logging.info(f"Sent RSS feed news: {message}")
                    break
            time.sleep(10000)  # Sleep for over 1 hour before fetching news again
        except Exception as e:
            logging.error(f"An error occurred in send_onlinekhabar_news: {e}")
            time.sleep(300)  # Sleep for 5 minutes before retrying

def send_viral_news():
    sent_news = set()  # Set to store already sent news titles

    while True:
        try:
            news_items = fetch_viral_news()
            most_viral_news = get_most_viral_news(news_items)
            if most_viral_news:
                title_nepali = translate_to_nepali(most_viral_news['title'])
                description_nepali = translate_to_nepali(most_viral_news['description'])
                message = f"{title_nepali} - {description_nepali}"
                if message not in sent_news:
                    bot.send_message(GROUP_CHAT_ID, message)
                    sent_news.add(message)
                    logging.info(f"Sent viral news: {message}")
            time.sleep(10000)  # Sleep for over 1 hour and 15 minutes before fetching news again
        except Exception as e:
            logging.error(f"An error occurred in send_viral_news: {e}")
            time.sleep(300)  # Sleep for 5 minutes before retrying

if __name__ == '__main__':
    # Start the two functions in separate threads
    threading.Thread(target=send_onlinekhabar_news).start()
    threading.Thread(target=send_viral_news).start()
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=8000)
                
