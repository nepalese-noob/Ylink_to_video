import telebot
import re
import threading
import time
import random
from flask import Flask

# Initialize the bot with your token
API_TOKEN = '7081682015:AAEhCpMwxPbUj_il87hCI3cdCdijanyeHNg'
bot = telebot.TeleBot(API_TOKEN, parse_mode='MarkdownV2')

# File to save Q&A
QA_FILE = 'qa.txt'
chat_id = -1001597616235  # Your group chat ID

# Initialize Flask app
app = Flask(__name__)

# Function to escape MarkdownV2 reserved characters
def escape_markdown_v2(text):
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

# Function to read Q&A pairs from file
def read_qa_pairs():
    qa_pairs = []
    try:
        with open(QA_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if '=' in line:
                    question, answer = line.split('=', 1)
                    qa_pairs.append((question.strip(), answer.strip()))
    except FileNotFoundError:
        pass
    return qa_pairs

# Function to parse Q&A messages
def parse_qa_message(message):
    lines = message.split('\n')
    qa_pairs = []
    qa_pattern = re.compile(r'(.+?)[👉=⇒→÷>](.+)')

    for line in lines:
        match = qa_pattern.search(line)
        if match:
            question, answer = match.groups()
            question = question.strip()
            answer = answer.strip()
            qa_pairs.append((question, answer))

    return qa_pairs

# Handler to save Q&A pairs
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    qa_pairs = parse_qa_message(message.text)
    if qa_pairs:
        with open(QA_FILE, 'a', encoding='utf-8') as f:
            for question, answer in qa_pairs:
                f.write(f'{question} = {answer}\n')
        bot.reply_to(message, escape_markdown_v2("Q&A pairs saved."))
    else:
        bot.reply_to(message, escape_markdown_v2(""))

# Function to send random Q&A pairs every minute
def send_qa_pairs():
    while True:
        qa_pairs = read_qa_pairs()
        if qa_pairs:
            question, answer = random.choice(qa_pairs)
            if chat_id:
                escaped_question = escape_markdown_v2(question)
                escaped_answer = escape_markdown_v2(answer)
                bot.send_message(chat_id, f'{escaped_question} 👉 ||{escaped_answer}||')
        time.sleep(1200)

# Start the Q&A sending thread
threading.Thread(target=send_qa_pairs).start()

@bot.message_handler(commands=['1', '2', '3', '4', '5', '6', '7', '8', '9', '10'])
def handle_command(message):
    qa_pairs = read_qa_pairs()
    num_pairs = int(message.text[1:])
    response = ""

    # Get random sample of Q&A pairs
    random_qa_pairs = random.sample(qa_pairs, min(num_pairs, len(qa_pairs)))

    for question, answer in random_qa_pairs:
        escaped_question = escape_markdown_v2(question)
        escaped_answer = escape_markdown_v2(answer)
        response += f'{escaped_question} 👉 ||{escaped_answer}||\n'

    bot.reply_to(message, response)

# Function to handle bot polling with reconnection
def run_bot():
    while True:
        try:
            bot.polling()
        except Exception as e:
            print(f"Error occurred: {e}. Restarting bot in 5 seconds...")
            time.sleep(5)

# Start the bot polling in a separate thread
threading.Thread(target=run_bot).start()

# Define a simple Flask route to keep the app running
@app.route('/')
def index():
    return 'Bot is running', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
    
