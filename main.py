import os
import telebot
from telebot.handler_backends import State, StatesGroup
from telebot.storage import StateMemoryStorage
from telebot import types
import google.generativeai as genai
from PIL import Image
import io
import requests
import sqlite3
from datetime import datetime, time
import schedule
import threading
import time as time_module

# Configure API keys from Replit secrets
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']

# Validate that we have our required environment variables
if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("Missing required secrets. Please check Replit secrets.")

# Rest of your code remains the same...

# Initialize bot with state storage
state_storage = StateMemoryStorage()
bot = telebot.TeleBot(TELEGRAM_TOKEN, state_storage=state_storage)

# Register states with bot
bot.add_custom_filter(telebot.custom_filters.StateFilter(bot))

# Initialize Gemini
genai.configure(api_key=GEMINI_API_KEY)
vision_model = genai.GenerativeModel('gemini-1.5-flash')
text_model = genai.GenerativeModel('gemini-1.5-flash')

# States for food diary
class UserState(StatesGroup):
    language = State()
    awaiting_calories = State()

# Dictionary to store user language preferences
user_languages = {}

# Messages dictionary
messages = {
    'en': {
        'welcome': """
👋 Welcome to the Food Recognition Bot!

Send me a photo of any food and I'll:
1. 🔍 Identify what's in the image
2. 📊 Estimate its nutritional value

Just send a photo to get started!
""",
        'analyzing': "🔍 Analyzing your food image...",
        'food_analysis': "🍽️ Food Analysis:\n",
        'nutritional_values': "📊 Estimated Nutritional Values:\n",
        'approximate_note': "\n\n⚠️ Note: These are approximate values.",
        'error': "❌ Sorry, an error occurred: ",
        'send_photo': "Please send a food photo for analysis! 📸",
        'choose_language': "Please choose your preferred language / Пожалуйста, выберите язык:",
        'language_set': "Language set to English! You can now send food photos for analysis.",
        'save_calories': """Would you like to save the calories into your food diary?
If this is a large portion and full-fat ingredients have been used, type in the upper value from the range I gave you.
If it's a small portion and low-fat ingredients have been used, type in the lower value.""",
        'calories_saved': "✅ Calories saved to your food diary!",
        'invalid_calories': "❌ Please enter a valid number for calories.",
        'daily_summary': "📊 Your daily calorie intake summary:\n",
        'no_entries': "No food entries recorded today."
    },
    'ru': {
        'welcome': """
👋 Добро пожаловать в бот распознавания еды!

Отправьте мне фотографию любого блюда, и я:
1. 🔍 Определю, что на фотографии
2. 📊 Оценю пищевую ценность

Просто отправьте фото, чтобы начать!
""",
        'analyzing': "🔍 Анализирую ваше фото...",
        'food_analysis': "🍽️ Анализ блюда:\n",
        'nutritional_values': "📊 Примерная пищевая ценность:\n",
        'approximate_note': "\n\n⚠️ Примечание: Это приблизительные значения.",
        'error': "❌ Извините, произошла ошибка: ",
        'send_photo': "Пожалуйста, отправьте фотографию еды для анализа! 📸",
        'choose_language': "Please choose your preferred language / Пожалуйста, выберите язык:",
        'language_set': "Язык установлен на русский! Теперь вы можете отправлять фотографии еды для анализа.",
        'save_calories': """Хотите сохранить калории в дневник питания?
Если это большая порция и использовались жирные ингредиенты, введите верхнее значение из указанного диапазона.
Если порция маленькая и использовались низкокалорийные ингредиенты, введите нижнее значение.""",
        'calories_saved': "✅ Калории сохранены в ваш дневник!",
        'invalid_calories': "❌ Пожалуйста, введите корректное число калорий.",
        'daily_summary': "📊 Итоги вашего дневного потребления калорий:\n",
        'no_entries': "Сегодня нет записей о приёме пищи."
    }
}
# Gemini prompts
prompts = {
    'en': {
        'food': """
        Analyze this food image and provide:
        1. What food items are present
        2. Brief description of the dish
        Keep the response concise and clear.
        """,
        'nutrition': """
        Based on the food identified ({}), provide an estimation of:
        1. Calories (kcal)
        2. Protein (g)
        3. Carbohydrates (g)
        4. Fat (g)

        Format as a clear list with approximate values. Consider this an estimation only.
        """
    },
    'ru': {
        'food': """
        Проанализируй это изображение еды и укажи:
        1. Какие продукты присутствуют
        2. Краткое описание блюда
        Дай краткий и четкий ответ на русском языке.
        """,
        'nutrition': """
        На основе определенных продуктов ({}), предоставь оценку:
        1. Калории (ккал)
        2. Белки (г)
        3. Углеводы (г)
        4. Жиры (г)

        Оформи в виде четкого списка с примерными значениями на русском языке.
        Учти, что это приблизительная оценка.
        """
    }
}

# Database initialization
def init_db():
    conn = sqlite3.connect('food_diary.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, language TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS food_diary
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  calories INTEGER,
                  date TEXT,
                  time TEXT)''')
    conn.commit()
    conn.close()

@bot.message_handler(commands=['start', 'language'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup()
    btn_en = types.InlineKeyboardButton("English 🇬🇧", callback_data='lang_en')
    btn_ru = types.InlineKeyboardButton("Русский 🇷🇺", callback_data='lang_ru')
    markup.add(btn_en, btn_ru)
    bot.reply_to(message, messages['en']['choose_language'], reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
def callback_language(call):
    lang = call.data.split('_')[1]
    user_languages[call.message.chat.id] = lang
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, messages[lang]['language_set'])
    bot.send_message(call.message.chat.id, messages[lang]['welcome'])

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        lang = user_languages.get(message.chat.id, 'en')

        # Send processing message
        bot.reply_to(message, messages[lang]['analyzing'])

        # Get photo file
        file_info = bot.get_file(message.photo[-1].file_id)
        photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"

        # Download and process image
        response = requests.get(photo_url)
        image = Image.open(io.BytesIO(response.content))

        # Analyze food using Gemini Vision
        vision_response = vision_model.generate_content([prompts[lang]['food'], image])
        food_description = vision_response.text

        bot.reply_to(message, messages[lang]['food_analysis'] + food_description)

        # Get nutritional estimation
        nutrition_response = text_model.generate_content(prompts[lang]['nutrition'].format(food_description))
        nutrition_info = nutrition_response.text

        bot.reply_to(message, 
                    messages[lang]['nutritional_values'] + 
                    nutrition_info + 
                    messages[lang]['approximate_note'])

        # Ask about saving calories
        bot.reply_to(message, messages[lang]['save_calories'])
        bot.set_state(message.from_user.id, UserState.awaiting_calories, message.chat.id)

    except Exception as e:
        bot.reply_to(message, messages[lang]['error'] + str(e))

@bot.message_handler(state=UserState.awaiting_calories)    
def handle_calories(message):
    try:
            print(f"Received calorie input: {message.text}")  # Debug print
            calories = int(message.text)
            user_id = message.from_user.id
            current_date = datetime.now().strftime('%Y-%m-%d')
            current_time = datetime.now().strftime('%H:%M:%S')
            lang = user_languages.get(message.chat.id, 'en')

            print(f"Processing calories for user {user_id}")  # Debug print

            conn = sqlite3.connect('food_diary.db')
            c = conn.cursor()

            # Insert new calories
            c.execute('''INSERT INTO food_diary (user_id, calories, date, time)
                        VALUES (?, ?, ?, ?)''', (user_id, calories, current_date, current_time))

            print(f"Inserted calories into database")  # Debug print

            # Get total calories for today
            c.execute('''SELECT SUM(calories) FROM food_diary 
                        WHERE user_id = ? AND date = ?''', 
                        (user_id, current_date))
            total_calories = c.fetchone()[0] or 0

            print(f"Total calories for today: {total_calories}")  # Debug print

            conn.commit()
            conn.close()

            # Prepare response message
            if lang == 'en':
                response = (f"✅ {calories} calories added to your food diary!\n\n"
                           f"📊 Your total calories today: {total_calories} kcal")
            else:
                response = (f"✅ {calories} калорий добавлено в ваш дневник!\n\n"
                           f"📊 Всего калорий за сегодня: {total_calories} ккал")

            print(f"Sending response: {response}")  # Debug print
            # Send the response as a reply
            bot.reply_to(message, response)
            print("Response sent")  # Debug print

            # Clear the state
            bot.delete_state(message.from_user.id, message.chat.id)
            print("State cleared")  # Debug print

    except ValueError as e:
            print(f"ValueError occurred: {e}")  # Debug print
            lang = user_languages.get(message.chat.id, 'en')
            bot.reply_to(message, messages[lang]['invalid_calories'])
    except Exception as e:
            print(f"Unexpected error: {e}")  # Debug print
            lang = user_languages.get(message.chat.id, 'en')
            bot.reply_to(message, f"❌ An error occurred: {str(e)}")

# Modify the default handler to only respond to text messages that aren't commands
@bot.message_handler(func=lambda message: message.content_type == 'text' and not message.text.startswith('/'))
def echo_all(message):
    # Only prompt for photo if not in any state
    if not bot.get_state(message.from_user.id, message.chat.id):
        lang = user_languages.get(message.chat.id, 'en')
        bot.reply_to(message, messages[lang]['send_photo'])

def send_daily_summary():
    conn = sqlite3.connect('food_diary.db')
    c = conn.cursor()

    # Get all users
    c.execute('SELECT DISTINCT user_id FROM food_diary')
    users = c.fetchall()

    current_date = datetime.now().strftime('%Y-%m-%d')

    for user in users:
        user_id = user[0]
        lang = user_languages.get(user_id, 'en')

        # Get daily calories using string date
        c.execute('''SELECT SUM(calories) FROM food_diary 
                    WHERE user_id = ? AND date = ?''', 
                    (user_id, current_date))
        total_calories = c.fetchone()[0] or 0

        if total_calories:
            prompt = f"""Generate a friendly daily calorie intake summary in {'Russian' if lang == 'ru' else 'English'} for:
            Total calories: {total_calories}
            Include:
            1. The approximate nature of the calculations
            2. A reasonable error margin (±10-15%)
            3. A brief comment on whether this is within typical daily requirements
            Keep it concise and friendly."""

            response = text_model.generate_content(prompt)
            summary = response.text

            try:
                bot.send_message(user_id, messages[lang]['daily_summary'] + summary)
            except Exception as e:
                print(f"Error sending summary to user {user_id}: {e}")
        else:
            try:
                bot.send_message(user_id, messages[lang]['no_entries'])
            except Exception as e:
                print(f"Error sending no entries message to user {user_id}: {e}")

    conn.close()

def schedule_checker():
    while True:
        schedule.run_pending()
        time_module.sleep(60)

def main():
    init_db()

    # Schedule daily summary at 22:00
    schedule.every().day.at("22:00").do(send_daily_summary)

    # Start scheduler in a separate thread
    scheduler_thread = threading.Thread(target=schedule_checker)
    scheduler_thread.daemon = True
    scheduler_thread.start()

    print("🤖 Bot is running... / Бот запущен...")
    bot.infinity_polling()

if __name__ == "__main__":
    main()