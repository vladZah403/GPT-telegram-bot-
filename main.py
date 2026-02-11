import telebot
from telebot import types
from g4f.client import Client
import requests
from io import BytesIO
import threading
import logging
import base64

# ===== Настройка логирования =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ===== Настройки бота =====
BOT_TOKEN = "8094757760:AAHRKESZHJFrDNtAVcWvf56N3FKu0ZSfFmA"
bot = telebot.TeleBot(BOT_TOKEN)
client = Client()

# ===== Установка команд бота (подсказки при вводе /) =====
commands = [
    telebot.types.BotCommand("/start", "Начать работу с ботом"),
    telebot.types.BotCommand("/help", "Показать инструкцию по использованию бота"),
    telebot.types.BotCommand("/model", "Выбрать модель для общения с ИИ"),
    telebot.types.BotCommand("/image", "Сгенерировать изображение по описанию"),
    telebot.types.BotCommand("/analyze", "Анализировать изображение")
]
bot.set_my_commands(commands)

# ===== Модели и пользователи =====
DEFAULT_MODEL = "gpt-4o-mini"
VISION_MODEL = "gpt-4o"  # Модель с поддержкой vision
user_models = {}
user_waiting_for_image = {}  # Отслеживание пользователей, ожидающих фото

AVAILABLE_MODELS = {
    "GPT-4.1": "gpt-4.1",
    "GPT-4": "gpt-4",
    "GPT-4o": "gpt-4o",
    "GPT-4o-mini": "gpt-4o-mini",
    "DeepSeek V3": "deepseek-v3"
}


# ===== КОМАНДА START =====
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Я бот с поддержкой ИИ, генерации и анализа изображений.\n"
        "Используй /help для просмотра всех команд."
    )


# ===== ВЫБОР МОДЕЛИ =====
@bot.message_handler(commands=['model'])
def choose_model(message):
    keyboard = types.InlineKeyboardMarkup()
    current_model = user_models.get(message.from_user.id, DEFAULT_MODEL)

    for name, model_id in AVAILABLE_MODELS.items():
        button_text = f"✅ {name}" if model_id == current_model else name
        keyboard.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"model:{model_id}"
        ))

    bot.send_message(
        message.chat.id,
        f"Текущая модель: *{current_model}*\n\nВыбери новую модель:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("model:"))
def set_model(call):
    model_id = call.data.split(":")[1]
    user_models[call.from_user.id] = model_id

    model_name = next((name for name, mid in AVAILABLE_MODELS.items() if mid == model_id), model_id)

    bot.answer_callback_query(call.id, f"Модель выбрана: {model_name}")
    bot.edit_message_text(
        f"✅ Модель успешно изменена на: *{model_name}*",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown"
    )


# ===== АНАЛИЗ ИЗОБРАЖЕНИЙ =====
@bot.message_handler(commands=['analyze'])
def analyze_command(message):
    user_waiting_for_image[message.from_user.id] = {
        'waiting': True,
        'prompt': None
    }
    bot.send_message(
        message.chat.id,
        "📸 Отправь мне фото для анализа.\n\n"
        "Ты можешь:\n"
        "• Просто отправить фото (я опишу что на нём)\n"
        "• Добавить подпись к фото с вопросом\n\n"
        "Например: 'Что изображено на этом фото?', 'Опиши детально', 'Какие цвета преобладают?'"
    )


def analyze_image_thread(message, photo, user_prompt=None):
    try:
        status_msg = bot.send_message(message.chat.id, "🔍 Анализирую изображение...")
        bot.send_chat_action(message.chat.id, "typing")

        # Получаем файл фото
        file_info = bot.get_file(photo.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Конвертируем в base64
        image_base64 = base64.b64encode(downloaded_file).decode('utf-8')

        # Формируем промпт
        if user_prompt:
            prompt = user_prompt
        else:
            prompt = "Опиши подробно что изображено на этом фото. Укажи основные объекты, цвета, настроение и детали."

        # Отправляем запрос к API с изображением
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
        )

        analysis = response.choices[0].message.content

        # Удаляем статус и отправляем результат
        bot.delete_message(message.chat.id, status_msg.message_id)

        # Разбиваем длинные сообщения
        max_length = 4096
        if len(analysis) > max_length:
            for i in range(0, len(analysis), max_length):
                bot.send_message(message.chat.id, analysis[i:i + max_length])
        else:
            bot.send_message(message.chat.id, f"🔍 *Анализ изображения:*\n\n{analysis}", parse_mode="Markdown")

    except Exception as e:
        logging.error(f"Ошибка анализа изображения: {e}")
        try:
            bot.edit_message_text(
                f"❌ Ошибка при анализе изображения:\n{str(e)[:300]}",
                message.chat.id,
                status_msg.message_id
            )
        except:
            bot.send_message(
                message.chat.id,
                f"❌ Ошибка при анализе изображения:\n{str(e)[:300]}"
            )


# ===== ОБРАБОТКА ФОТО =====
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.from_user.id

    # Берём фото лучшего качества (последнее в списке)
    photo = message.photo[-1]

    # Получаем текст подписи к фото (если есть)
    user_prompt = message.caption if message.caption else None

    # Проверяем, ожидает ли пользователь отправки фото для анализа
    if user_id in user_waiting_for_image and user_waiting_for_image[user_id]['waiting']:
        user_waiting_for_image[user_id]['waiting'] = False
        threading.Thread(
            target=analyze_image_thread,
            args=(message, photo, user_prompt),
            daemon=True
        ).start()
    else:
        # Если пользователь просто отправил фото, предлагаем варианты
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("🔍 Анализировать", callback_data=f"analyze_photo:{photo.file_id}"),
            types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_photo")
        )
        bot.send_message(
            message.chat.id,
            "📸 Что сделать с этим фото?",
            reply_markup=keyboard
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("analyze_photo:"))
def analyze_photo_callback(call):
    file_id = call.data.split(":")[1]
    bot.answer_callback_query(call.id, "Анализирую...")

    # Создаём объект photo для передачи в функцию
    class PhotoObj:
        def __init__(self, file_id):
            self.file_id = file_id

    photo = PhotoObj(file_id)

    threading.Thread(
        target=analyze_image_thread,
        args=(call.message, photo, None),
        daemon=True
    ).start()

    bot.edit_message_text(
        "🔍 Начинаю анализ...",
        call.message.chat.id,
        call.message.message_id
    )


@bot.callback_query_handler(func=lambda call: call.data == "cancel_photo")
def cancel_photo(call):
    bot.answer_callback_query(call.id, "Отменено")
    bot.delete_message(call.message.chat.id, call.message.message_id)


# ===== ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ =====
def generate_image_thread(message):
    prompt = message.text.replace("/image", "").strip()
    if not prompt:
        bot.reply_to(message, "❌ Напиши описание после команды /image\n\nПример: /image красивый закат на море")
        return

    status_msg = bot.send_message(message.chat.id, "🎨 Генерирую изображение...")
    bot.send_chat_action(message.chat.id, "upload_photo")

    models_to_try = ["flux", "dalle-3", "sdxl", "playground-v2"]

    for model in models_to_try:
        try:
            logging.info(f"Пробую модель: {model}")

            response = client.images.generate(
                model=model,
                prompt=prompt
            )

            logging.info(f"Ответ от {model}: {type(response)}")

            image_data = None

            if isinstance(response, str):
                if response.startswith("http"):
                    img_response = requests.get(response, timeout=30)
                    img_response.raise_for_status()
                    image_data = img_response.content
                else:
                    image_data = base64.b64decode(response)

            elif hasattr(response, "data") and len(response.data) > 0:
                first = response.data[0]
                if hasattr(first, "url"):
                    img_response = requests.get(first.url, timeout=30)
                    img_response.raise_for_status()
                    image_data = img_response.content
                elif hasattr(first, "b64_json"):
                    image_data = base64.b64decode(first.b64_json)

            elif isinstance(response, list) and len(response) > 0:
                first = response[0]
                if isinstance(first, str):
                    if first.startswith("http"):
                        img_response = requests.get(first, timeout=30)
                        img_response.raise_for_status()
                        image_data = img_response.content
                    else:
                        image_data = base64.b64decode(first)

            if image_data:
                image_bytes = BytesIO(image_data)
                image_bytes.name = "image.png"
                bot.delete_message(message.chat.id, status_msg.message_id)
                bot.send_photo(message.chat.id, image_bytes, caption=f"🎨 {prompt}\n📷 Модель: {model}")
                return

        except Exception as e:
            logging.error(f"Ошибка с моделью {model}: {e}")
            continue

    bot.edit_message_text(
        "❌ К сожалению, не удалось сгенерировать изображение.\n\n"
        "💡 Попробуйте:\n"
        "- Изменить описание\n"
        "- Использовать английский язык\n"
        "- Попробовать позже",
        message.chat.id,
        status_msg.message_id
    )


@bot.message_handler(commands=['image'])
def handle_image(message):
    threading.Thread(target=generate_image_thread, args=(message,), daemon=True).start()


# ===== ОБЩЕНИЕ С ИИ =====
def chat_thread(message):
    model = user_models.get(message.from_user.id, DEFAULT_MODEL)

    bot.send_chat_action(message.chat.id, "typing")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": message.text}],
            web_search=False
        )
        text = response.choices[0].message.content

        max_length = 4096
        if len(text) > max_length:
            for i in range(0, len(text), max_length):
                bot.send_message(message.chat.id, text[i:i + max_length])
        else:
            bot.send_message(message.chat.id, text)

    except Exception as e:
        logging.error(f"Ошибка генерации текста: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка при обработке запроса:\n{str(e)[:200]}")


# ===== ОБРАБОТКА ТЕКСТА =====
@bot.message_handler(func=lambda message: not message.text.startswith("/"), content_types=['text'])
def handle_text(message):
    threading.Thread(target=chat_thread, args=(message,), daemon=True).start()


# ===== ИНСТРУКЦИЯ =====
@bot.message_handler(commands=['help'])
def show_help(message):
    current_model = user_models.get(message.from_user.id, DEFAULT_MODEL)
    help_text = f"""
📖 *Инструкция по использованию бота*

🤖 Я бот с поддержкой ИИ, генерации и анализа изображений.

*Доступные команды:*

1️⃣ *Выбор модели:*
   /model - выбрать модель для общения

   Доступные модели:
   • GPT-4.1
   • GPT-4
   • GPT-4o
   • GPT-4o-mini
   • DeepSeek V3

2️⃣ *Генерация текста:*
   Просто напиши мне любое сообщение, и я отвечу с помощью выбранной модели.

3️⃣ *Генерация изображений:*
   /image <описание> - сгенерировать картинку

   Пример: `/image красивый лес на закате`

4️⃣ *Анализ изображений:*
   /analyze - активировать режим анализа фото

   Или просто отправь фото с подписью-вопросом!

   Примеры вопросов:
   • "Что на этом фото?"
   • "Опиши детально"
   • "Какие эмоции передаёт изображение?"
   • "Есть ли на фото текст?"

5️⃣ *Помощь:*
   /help - показать это сообщение

✅ Текущая модель: `{current_model}`

💡 Каждый пользователь может выбрать свою модель, настройки сохраняются.
"""
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")


# ===== ЗАПУСК БОТА =====
if __name__ == "__main__":
    logging.info("Бот запущен и готов к работе!")
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")