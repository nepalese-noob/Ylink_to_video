import telebot
import requests
from deep_translator import GoogleTranslator
import feedparser
import logging
import threading
import time
import random
from flask import Flask, request

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize Flask app
app = Flask(__name__)

# Replace with environment variables for safety
API_KEY = os.getenv('NEWS_API_KEY')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROUP_CHAT_ID = os.getenv('GROUP_CHAT_ID')

API_URL = f'https://newsdata.io/api/1/news?apikey={API_KEY}&country=np&language=en'
FEED_URL = 'https://www.onlinekhabar.com/feed'

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

@app.route('/')
def home():
    return "News Bot is running."

@app.route('/start')
def start_services():
    logging.info("Starting background services...")
    threading.Thread(target=send_onlinekhabar_news, daemon=True).start()
    threading.Thread(target=send_viral_news, daemon=True).start()
    return "Background services started."

@bot.message_handler(commands=['news'])
def send_random_news(message):
    try:
        if random.choice([True, False]):
            news_items = fetch_news()
            if news_items:
                item = random.choice(news_items)
                bot.send_message(message.chat.id, f"{item.title} - {item.link}")
                logging.info(f"Sent RSS feed news on command: {item.title} - {item.link}")
            else:
                bot.send_message(message.chat.id, "No news found from Online Khabar.")
        else:
            news_items = fetch_viral_news()
            most_viral_news = get_most_viral_news(news_items)
            if most_viral_news:
                title_nepali = translate_to_nepali(most_viral_news['title'])
                description_nepali = translate_to_nepali(most_viral_news['description'])
                message_text = f"{title_nepali} - {description_nepali}"
                bot.send_message(message.chat.id, message_text)
                logging.info(f"Sent viral news on command: {message_text}")
            else:
                bot.send_message(message.chat.id, "No viral news found.")
    except Exception as e:
        logging.error(f"An error occurred in send_random_news: {e}")
        bot.send_message(message.chat.id, "An error occurred while fetching the news.")

if __name__ == '__main__':
    # Start the Flask app
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000))), daemon=True).start()
    
    # Start the bot polling
    bot.polling(none_stop=True)
