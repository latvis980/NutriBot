    import os
    from threading import Thread
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
    import logging

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    # Helper function to convert markdown to HTML
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
                # Replace markdown bullet with • and add HTML formatting
                line = f"• {line[1:].strip()}"

            # Handle italic text
            if '_' in line:
                parts = line.split('_')
                for i in range(len(parts)):
                    if i % 2 == 1:  # Odd indexes are inside _ _
                        parts[i] = f'<i>{parts[i]}</i>'
                line = ''.join(parts)

            formatted_lines.append(line)

        return '\n'.join(formatted_lines)
    # Configure API keys
    TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
    GEMINI_API_KEY = os.environ['GEMINI_API_KEY']

    # Validate that we have our required environment variables
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        raise ValueError("Missing required secrets. Please check Replit secrets.")

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
        awaiting_food_text = State()


    # Dictionary to store user language preferences
    user_languages = {}

    # Messages dictionary with HTML formatting
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
            'choose_language':
            "Please choose your preferred language 🔵 Пожалуйста, выберите язык:",
            'language_set':
            "Language set to English! You can now track your food 🕺🏻",
            'save_calories':
            """<b>Would you like to save the calories into your food diary?</b>

    🧈 <i>If this is a large portion and full-fat ingredients have been used, type in the upper value from the range I gave you.</i>

    🌿 <i>If it's a small portion and low-fat ingredients have been used, type in the lower value.</i>""",
            'calories_saved': "✔️ <b>Calories saved to your food diary!</b>",
            'invalid_calories': "❌ Please enter a valid number for calories.",
            'daily_summary': "📊 <b>Your daily calorie intake summary:</b>\n",
            'no_entries': "<i>No food entries recorded today.</i>",
            'text_input':
            "Please describe your food in detail (e.g., '<i>grilled chicken breast with rice and vegetables</i>')",
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
            'approximate_note':
            "🔮 <i>Примечание: Это приблизительные значения.</i>",
            'error': "❌ <b>Извините, произошла ошибка:</b> ",
            'send_photo': "Пожалуйста, отправьте фотографию еды для анализа! 📸",
            'choose_language':
            "Please choose your preferred language / Пожалуйста, выберите язык:",
            'language_set': "<b>Давайте начнём вести дневник калорий</b> 🕺🏻",
            'save_calories': """<b>Хотите сохранить калории в дневник питания?</b>

    🧈 <i>Если это большая порция и использовались жирные ингредиенты, введите верхнее значение из указанного диапазона.</i>

    🌿 <i>Если порция маленькая и использовались низкокалорийные ингредиенты, введите нижнее значение.</i>""",
            'calories_saved': "✔️ <b>Калории сохранены в ваш дневник!</b>",
            'invalid_calories': "❌ Пожалуйста, введите корректное число калорий.",
            'daily_summary':
            "📊 <b>Итоги вашего дневного потребления калорий:</b>\n",
            'no_entries': "<i>Сегодня нет записей о приёме пищи.</i>",
            'text_input':
            "Пожалуйста, опишите вашу еду подробно (например, '<i>куриная грудка на гриле с рисом и овощами</i>')",
            'analyzing_text': "🔍 <i>Анализирую описание вашей еды...</i>"
        }
    }
    # Gemini prompts
    prompts = {
        'en': {
            'food':
            """
            Analyze this food image and provide:
            1. What food items are present
            2. Brief description of the dish
            Keep the response concise and clear.
            """,
            'nutrition':
            """
            Based on the food identified ({}), provide an estimation of:
            1. Calories (kcal)
            2. Protein (g)
            3. Carbohydrates (g)
            4. Fat (g)

            Format as a clear list with approximate values. Consider this an estimation only.
            """
        },
        'ru': {
            'food':
            """
            Проанализируй это изображение еды и укажи:
            1. Какие продукты присутствуют
            2. Краткое описание блюда
            Дай краткий и четкий ответ на русском языке.
            """,
            'nutrition':
            """
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
        try:
            logger.info("Starting database initialization...")
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
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise


    def schedule_checker():
        while True:
            schedule.run_pending()
            time_module.sleep(60)


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
            c.execute(
                '''SELECT SUM(calories) FROM food_diary 
                        WHERE user_id = ? AND date = ?''', (user_id, current_date))
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
                    bot.send_message(user_id,
                                     messages[lang]['daily_summary'] + summary)
                except Exception as e:
                    logger.info(f"Error sending summary to user {user_id}: {e}")
            else:
                try:
                    bot.send_message(user_id, messages[lang]['no_entries'])
                except Exception as e:
                    logger.info(
                        f"Error sending no entries message to user {user_id}: {e}")

        conn.close()


    @bot.message_handler(commands=['start', 'language'])
    def send_welcome(message):
        # First show language selection
        markup = types.InlineKeyboardMarkup()
        btn_en = types.InlineKeyboardButton("English", callback_data='lang_en')
        btn_ru = types.InlineKeyboardButton("Русский", callback_data='lang_ru')
        markup.add(btn_en, btn_ru)
        bot.reply_to(message,
                     messages['en']['choose_language'],
                     parse_mode='HTML',
                     reply_markup=markup)


    @bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
    def callback_language(call):
        lang = call.data.split('_')[1]
        user_languages[call.message.chat.id] = lang
        bot.answer_callback_query(call.id)

        # Send welcome message
        bot.send_message(call.message.chat.id,
                         messages[lang]['language_set'],
                         parse_mode='HTML')

        # Create keyboard with input method buttons
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if lang == 'en':
            markup.add("📸 Add photo", "⌨️ Add as text")
        else:
            markup.add("📸 Добавить фото", "⌨️ Добавить текстом")

        bot.send_message(call.message.chat.id,
                         messages[lang]['welcome'],
                         parse_mode='HTML',
                         reply_markup=markup)


    @bot.message_handler(
        func=lambda message: message.content_type == 'text' and not message.text.
        startswith('/') and not message.text in [
            "📸 Add photo", "📸 Добавить фото", "⌨️ Add as text",
            "⌨️ Добавить текстом"
        ] and not bot.get_state(message.from_user.id, message.chat.id))
    def echo_all(message):
        lang = user_languages.get(message.chat.id, 'en')
        bot.reply_to(message, messages[lang]['send_photo'])


    @bot.message_handler(func=lambda message: message.text in [
        "📸 Add photo", "📸 Добавить фото", "⌨️ Add as text", "⌨️ Добавить текстом"
    ])
    def handle_input_choice(message):
        lang = user_languages.get(message.chat.id, 'en')
        if message.text in ["📸 Add photo", "📸 Добавить фото"]:
            bot.delete_state(message.from_user.id,
                             message.chat.id)  # Clear any existing state
            bot.reply_to(message, messages[lang]['send_photo'])
        else:
            # Set state before sending message
            bot.set_state(message.from_user.id, UserState.awaiting_food_text,
                          message.chat.id)
            bot.reply_to(message, messages[lang]['text_input'])

    # Update both handlers to use the formatting function
    @bot.message_handler(content_types=['photo'])
    def handle_photo(message):
        try:
            lang = user_languages.get(message.chat.id, 'en')
            bot.reply_to(message, messages[lang]['analyzing'], parse_mode='HTML')

            # Get photo file and process image...
            file_info = bot.get_file(message.photo[-1].file_id)
            photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
            response = requests.get(photo_url)
            image = Image.open(io.BytesIO(response.content))

            vision_response = vision_model.generate_content([prompts[lang]['food'], image])
            food_description = vision_response.text

            # Format food description
            formatted_food = format_nutrition_response(food_description)
            bot.reply_to(message, messages[lang]['food_analysis'] + formatted_food, parse_mode='HTML')

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
            bot.reply_to(message, messages[lang]['error'] + str(e), parse_mode='HTML')


    @bot.message_handler(state=UserState.awaiting_food_text)
    def handle_food_text(message):
        try:
            lang = user_languages.get(message.chat.id, 'en')
            bot.reply_to(message, messages[lang]['analyzing_text'], parse_mode='HTML')

            nutrition_response = text_model.generate_content(prompts[lang]['nutrition'].format(message.text))
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
            bot.delete_state(message.from_user.id, message.chat.id)
            bot.reply_to(message, messages[lang]['error'] + str(e), parse_mode='HTML')

    @bot.message_handler(state=UserState.awaiting_calories)
    def handle_calories(message):
        try:
            logger.info(
                f"Received calorie input: {message.text}")  # Logging calorie input
            calories = int(message.text)
            user_id = message.from_user.id
            current_date = datetime.now().strftime('%Y-%m-%d')
            current_time = datetime.now().strftime('%H:%M:%S')
            lang = user_languages.get(message.chat.id, 'en')
            logger.info(f"Processing calories for user {user_id}")

            conn = sqlite3.connect('food_diary.db')
            c = conn.cursor()

            # Insert new calories
            c.execute(
                '''INSERT INTO food_diary (user_id, calories, date, time)
                        VALUES (?, ?, ?, ?)''',
                (user_id, calories, current_date, current_time))
            logger.info("Inserted calories into database")

            # Get total calories for today
            c.execute(
                '''SELECT SUM(calories) FROM food_diary 
                        WHERE user_id = ? AND date = ?''', (user_id, current_date))
            total_calories = c.fetchone()[0] or 0
            logger.info(f"Total calories for today: {total_calories}")

            conn.commit()
            conn.close()

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
            # Send the response as a reply
            bot.reply_to(message, response, parse_mode='HTML')
            logger.info("Response sent")

            # Clear the state
            bot.delete_state(message.from_user.id, message.chat.id)
            logger.info("State cleared")

        except ValueError as e:
            logger.info(f"ValueError occurred: {e}")
            lang = user_languages.get(message.chat.id, 'en')
            bot.reply_to(message, messages[lang]['invalid_calories'])
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            lang = user_languages.get(message.chat.id, 'en')
            bot.reply_to(message, f"❌ An error occurred: {str(e)}")


    def main():
        try:
            logger.info("Starting bot initialization...")

            init_db()
            logger.info("Database initialized")

            # Schedule daily summary at 22:00
            schedule.every().day.at("22:00").do(send_daily_summary)
            logger.info("Scheduled daily summary")

            # Start scheduler in a separate thread
            scheduler_thread = threading.Thread(target=schedule_checker)
            scheduler_thread.daemon = True
            scheduler_thread.start()
            logger.info("Scheduler thread started")

            logger.info("🤖 Bot is running... / Бот запущен...")

            # Add more detailed error handling for polling
            try:
                logger.info("Starting bot polling...")
                bot.infinity_polling(timeout=60, long_polling_timeout=5)
            except Exception as polling_error:
                logger.error(f"Polling error: {polling_error}")
                raise

        except Exception as e:
            logger.error(f"Main loop error: {e}")
            time_module.sleep(10)
            main()


    if __name__ == "__main__":
        logger.info("Script started")
        main()
