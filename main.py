import os
import telebot
from telebot.handler_backends import State, StatesGroup
from telebot.storage import StateMemoryStorage
from telebot import types
import google.generativeai as genai
from PIL import Image
import io
import requests
from datetime import datetime, time
import schedule
import threading
import time as time_module
import logging
from database_handler import init_database, db
import psycopg2

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add startup banner
logger.info("=" * 50)
logger.info("Starting NutriBot")
logger.info("=" * 50)

# States for food diary
class UserState(StatesGroup):
    language = State()
    awaiting_calories = State()
    awaiting_food_text = State()

# Initialize core components
try:
    logger.info("Checking environment variables...")
    required_vars = ['TELEGRAM_TOKEN', 'GEMINI_API_KEY', 'DATABASE_URL']
    for var in required_vars:
        value = os.environ.get(var)
        if not value:
            raise ValueError(f"Missing required environment variable: {var}")
        logger.info(f"{var} is set")

    # Enable middleware
    telebot.apihelper.ENABLE_MIDDLEWARE = True

    # Initialize bot
    state_storage = StateMemoryStorage()
    bot = telebot.TeleBot(os.environ['TELEGRAM_TOKEN'], state_storage=state_storage)
    bot.add_custom_filter(telebot.custom_filters.StateFilter(bot))
    logger.info("Bot initialized successfully")

    # Initialize Gemini
    genai.configure(api_key=os.environ['GEMINI_API_KEY'])
    vision_model = genai.GenerativeModel('gemini-1.5-flash')
    text_model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("Gemini initialized successfully")
except Exception as e:
    logger.error(f"Initialization error: {str(e)}", exc_info=True)
    raise

# Messages dictionary
messages = {
    'en': {
        'welcome': """
✨ <b>Hey there!</b>

I can help you track your food and calculate calories.

<i>Choose how you want to add your food:</i>
""",
        'analyzing': "🧪 <i>Analyzing your food image...</i>",
        'food_analysis': "🍽️ <b>Food Analysis:</b>\n",
        'nutritional_values': "📊 <b>Estimated Nutritional Values:</b>\n",
        'approximate_note': "🔮 <i>Note: These are approximate values.</i>",
        'error': "❌ <b>Sorry, an error occurred:</b> ",
        'send_photo': "Please send a food photo for analysis! 📸",
        'choose_language': "Please choose your preferred language | Пожалуйста, выберите язык:",
        'language_set': "Language set to English! You can now track your food 🕺🏻",
        'save_calories': """<b>Would you like to save the calories into your food diary?</b>

🧈 <i>If this is a large portion and full-fat ingredients have been used, type in the upper value from the range I gave you.</i>

🌿 <i>If it's a small portion and low-fat ingredients have been used, type in the lower value.</i>""",
        'calories_saved': "✔️ <b>Calories saved to your food diary!</b>",
        'invalid_calories': "❌ Please enter a valid number for calories.",
        'daily_summary': "📊 <b>Your daily calorie intake summary:</b>\n",
        'no_entries': "<i>No food entries recorded today.</i>",
        'text_input': "Please describe your food in detail (e.g., '<i>grilled chicken breast with rice and vegetables</i>')",
        'analyzing_text': "🔍 <i>Analyzing your food description...</i>"
    },
    'ru': {
        'welcome': """
✨ <b>Привет!</b>

Я помогу вам отслеживать питание и считать калории.

<i>Выберите, как вы хотите добавить еду:</i>
""",
        'analyzing': "🧪 <i>Анализирую ваше фото...</i>",
        'food_analysis': "🍽️ <b>Анализ блюда:</b>\n",
        'nutritional_values': "📊 <b>Примерная пищевая ценность:</b>\n",
        'approximate_note': "🔮 <i>Примечание: Это приблизительные значения.</i>",
        'error': "❌ <b>Извините, произошла ошибка:</b> ",
        'send_photo': "Пожалуйста, отправьте фотографию еды для анализа! 📸",
        'choose_language': "Please choose your preferred language / Пожалуйста, выберите язык:",
        'language_set': "<b>Давайте начнём вести дневник калорий</b> 🕺🏻",
        'save_calories': """<b>Хотите сохранить калории в дневник питания?</b>

🧈 <i>Если это большая порция и использовались жирные ингредиенты, введите верхнее значение из указанного диапазона.</i>

🌿 <i>Если порция маленькая и использовались низкокалорийные ингредиенты, введите нижнее значение.</i>""",
        'calories_saved': "✔️ <b>Калории сохранены в ваш дневник!</b>",
        'invalid_calories': "❌ Пожалуйста, введите корректное число калорий.",
        'daily_summary': "📊 <b>Итоги вашего дневного потребления калорий:</b>\n",
        'no_entries': "<i>Сегодня нет записей о приёме пищи.</i>",
        'text_input': "Пожалуйста, опишите вашу еду подробно (например, '<i>куриная грудка на гриле с рисом и овощами</i>')",
        'analyzing_text': "🔍 <i>Анализирую описание вашей еды...</i>"
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

# Helper functions
def get_user_language_safe(chat_id):
    try:
        return db.get_user_language(chat_id)
    except Exception as e:
        logger.error(f"Error getting user language: {e}")
        return 'en'

def format_nutrition_response(text):
    # First handle bold markdown
    parts = text.split('**')
    for i in range(len(parts)):
        if i % 2 == 1:  # Odd indexes are inside ** **
            parts[i] = f'<b>{parts[i]}</b>'
    text = ''.join(parts)

    # Replace bullet points and ensure proper formatting
    lines = text.split('\n')
    formatted_lines = []
    for line in lines:
        line = line.strip()
        if line.startswith('*') or line.startswith('-'):
            line = f"• {line[1:].strip()}"

        if '_' in line:
            parts = line.split('_')
            for i in range(len(parts)):
                if i % 2 == 1:
                    parts[i] = f'<i>{parts[i]}</i>'
            line = ''.join(parts)

        formatted_lines.append(line)

    return '\n'.join(formatted_lines)

def schedule_checker():
    try:
        while True:
            schedule.run_pending()
            time_module.sleep(60)
    except Exception as e:
        logger.error(f"Schedule checker error: {e}")

def send_daily_summary():
    try:
        daily_summaries = db.get_all_daily_summaries()
        for user_id, total_calories in daily_summaries:
            try:
                lang = get_user_language_safe(user_id)
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

                    bot.send_message(user_id,
                                    messages[lang]['daily_summary'] + summary,
                                    parse_mode='HTML')
                else:
                    bot.send_message(user_id, 
                                    messages[lang]['no_entries'],
                                    parse_mode='HTML')
            except Exception as e:
                logger.error(f"Error sending summary to user {user_id}: {e}")
    except Exception as e:
        logger.error(f"Error in send_daily_summary: {e}")

# Message handlers
@bot.message_handler(commands=['start', 'language'])
def send_welcome(message):
    try:
        markup = types.InlineKeyboardMarkup()
        btn_en = types.InlineKeyboardButton("English", callback_data='lang_en')
        btn_ru = types.InlineKeyboardButton("Русский", callback_data='lang_ru')
        markup.add(btn_en, btn_ru)
        bot.reply_to(message,
                     messages['en']['choose_language'],
                     parse_mode='HTML',
                     reply_markup=markup)
    except Exception as e:
        logger.error(f"Error in send_welcome: {e}")
        bot.reply_to(message, "An error occurred. Please try again.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
def callback_language(call):
    try:
        lang = call.data.split('_')[1]
        db.save_user_language(call.message.chat.id, lang)
        bot.answer_callback_query(call.id)

        bot.send_message(call.message.chat.id,
                         messages[lang]['language_set'],
                         parse_mode='HTML')

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if lang == 'en':
            markup.add("📸 Add photo", "⌨️ Add as text")
        else:
            markup.add("📸 Добавить фото", "⌨️ Добавить текстом")

        bot.send_message(call.message.chat.id,
                         messages[lang]['welcome'],
                         parse_mode='HTML',
                         reply_markup=markup)
    except Exception as e:
        logger.error(f"Error in callback_language: {e}")
        bot.answer_callback_query(call.id, "An error occurred. Please try again.")

@bot.message_handler(
    func=lambda message: message.content_type == 'text' and 
    not message.text.startswith('/') and 
    not message.text in [
        "📸 Add photo", "📸 Добавить фото", 
        "⌨️ Add as text", "⌨️ Добавить текстом"
    ] and 
    not bot.get_state(message.from_user.id, message.chat.id)
)
def echo_all(message):
    try:
        lang = get_user_language_safe(message.chat.id)
        bot.reply_to(message, messages[lang]['send_photo'])
    except Exception as e:
        logger.error(f"Error in echo_all: {e}")

@bot.message_handler(func=lambda message: message.text in [
    "📸 Add photo", "📸 Добавить фото", 
    "⌨️ Add as text", "⌨️ Добавить текстом"
])
def handle_input_choice(message):
    try:
        lang = get_user_language_safe(message.chat.id)
        if message.text in ["📸 Add photo", "📸 Добавить фото"]:
            bot.delete_state(message.from_user.id, message.chat.id)
            bot.reply_to(message, messages[lang]['send_photo'])
        else:
            bot.set_state(message.from_user.id, 
                          UserState.awaiting_food_text,
                          message.chat.id)
            bot.reply_to(message, messages[lang]['text_input'])
    except Exception as e:
        logger.error(f"Error in handle_input_choice: {e}")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        lang = get_user_language_safe(message.chat.id)
        bot.reply_to(message, messages[lang]['analyzing'], parse_mode='HTML')

        file_info = bot.get_file(message.photo[-1].file_id)
        photo_url = f"https://api.telegram.org/file/bot{os.environ['TELEGRAM_TOKEN']}/{file_info.file_path}"
        response = requests.get(photo_url)
        image = Image.open(io.BytesIO(response.content))

        vision_response = vision_model.generate_content([prompts[lang]['food'], image])
        food_description = vision_response.text

        formatted_food = format_nutrition_response(food_description)
        bot.reply_to(message, 
                     messages[lang]['food_analysis'] + formatted_food, 
                     parse_mode='HTML')

        # Get and format nutritional info
        nutrition_response = text_model.generate_content(prompts[lang]['nutrition'].format(food_description))
        nutrition_info = format_nutrition_response(nutrition_response.text)

        formatted_response = (
                    messages[lang]['nutritional_values'] + 
                    '\n' + nutrition_info + 
                    messages[lang]['approximate_note']
                )

        bot.reply_to(message, formatted_response, parse_mode='HTML')
        bot.reply_to(message, messages[lang]['save_calories'], parse_mode='HTML')
        bot.set_state(message.from_user.id, UserState.awaiting_calories, message.chat.id)

    except Exception as e:
        logger.error(f"Error in handle_photo: {e}")
        lang = get_user_language_safe(message.chat.id)
        
        bot.reply_to(message, messages[lang]['error'] + str(e), parse_mode='HTML')

@bot.message_handler(state=UserState.awaiting_food_text)
def handle_food_text(message):
    try:
        lang = get_user_language_safe(message.chat.id)
        bot.reply_to(message, messages[lang]['analyzing_text'], parse_mode='HTML')

        nutrition_response = text_model.generate_content(prompts[lang]
            ['nutrition'].format(message.text))
        nutrition_info = format_nutrition_response(nutrition_response.text)

        formatted_response = (
            messages[lang]['nutritional_values'] + 
            '\n' + nutrition_info + 
            messages[lang]['approximate_note']
        )

        bot.reply_to(message, formatted_response, parse_mode='HTML')
        bot.reply_to(message, messages[lang]['save_calories'], parse_mode='HTML')
        bot.set_state(message.from_user.id, UserState.awaiting_calories, message.chat.id)

    except Exception as e:
        logger.error(f"Error in handle_food_text: {e}")
        bot.delete_state(message.from_user.id, message.chat.id)
        lang = get_user_language_safe(message.chat.id)
        bot.reply_to(message, messages[lang]['error'] + str(e), parse_mode='HTML')

@bot.message_handler(state=UserState.awaiting_calories)
def handle_calories(message):
    try:
        logger.info(f"Received calorie input: {message.text}")
        calories = int(message.text)
        user_id = message.from_user.id
        lang = get_user_language_safe(message.chat.id)
        logger.info(f"Processing calories for user {user_id}")

        # Save the food entry
        db.save_food_entry(user_id, calories)
        logger.info("Calories saved to database")

        # Get daily summary entries
        daily_entries = db.get_daily_summary(user_id)
        total_calories = sum(entry[0] for entry in daily_entries)
        logger.info(f"Total calories for today: {total_calories}")

        # Prepare response message
        if lang == 'en':
            response = (
                 f"<b>✅ {calories} calories added to your food diary!</b>\n\n"
                f"📊 Your total calories today: <b>{total_calories} kcal</b>")
        else:
            response = (
                f"<b>✅ {calories} калорий добавлено в ваш дневник!</b>\n\n"
                f"📊 Всего калорий за сегодня: <b>{total_calories} ккал</b>")

        logger.info(f"Sending response: {response}")
        bot.reply_to(message, response, parse_mode='HTML')
        logger.info("Response sent")

        # Clear the state
        bot.delete_state(message.from_user.id, message.chat.id)
        logger.info("State cleared")

    except ValueError as e:
        logger.error(f"ValueError occurred: {e}")
        lang = get_user_language_safe(message.chat.id)
        bot.reply_to(message, messages[lang]['invalid_calories'])
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        lang = get_user_language_safe(message.chat.id)
        bot.reply_to(message, f"❌ An error occurred: {str(e)}")

...

# Update the error handler function
@bot.middleware_handler(update_types=['update'])
def error_handler(bot_instance, update):
    if isinstance(update, Exception):
        logger.error(f"Telegram error: {update}")

def main():
    try:
        logger.info("Starting main function")

        # Initialize database
        logger.info("Initializing database...")
        init_database()
        logger.info("Database initialized successfully")

        # Schedule daily summary
        schedule.every().day.at("22:00").do(send_daily_summary)

        # Start scheduler thread
        scheduler_thread = threading.Thread(target=schedule_checker)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        logger.info("Scheduler started")

        # Start bot
        logger.info("Starting bot polling...")
        bot.infinity_polling(timeout=60, long_polling_timeout=5)

    except Exception as e:
        logger.error(f"Main loop error: {str(e)}", exc_info=True)
        time_module.sleep(10)
        main()
    finally:
        if db:
            logger.info("Closing database connection...")
            db.close()

if __name__ == "__main__":
    main()