import telebot
from telebot import types
from g4f.client import Client
import requests
from io import BytesIO
import threading
import logging
import base64
import re
import signal
import sys

# Импортируем конфигурацию
from config import Config

# ===== Настройка логирования =====
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ===== Инициализация бота =====
try:
    bot = telebot.TeleBot(Config.BOT_TOKEN)
    client = Client()
    logging.info("✅ Бот успешно инициализирован")
except Exception as e:
    logging.error(f"❌ Ошибка инициализации бота: {e}")
    sys.exit(1)


# ===== Установка команд бота =====
commands = [
    telebot.types.BotCommand("/start", "Начать работу с ботом"),
    telebot.types.BotCommand("/help", "Показать инструкцию по использованию бота"),
    telebot.types.BotCommand("/model", "Выбрать модель для общения с ИИ"),
    telebot.types.BotCommand("/image_model", "Выбрать модель для генерации изображений"),
    telebot.types.BotCommand("/image_settings", "Настройки генерации изображений"),
    telebot.types.BotCommand("/image", "Сгенерировать изображение по описанию"),
    telebot.types.BotCommand("/image_raw", "Сгенерировать без автоматического улучшения промпта"),
    telebot.types.BotCommand("/analyze", "Анализировать изображение"),
    telebot.types.BotCommand("/stats", "Показать статистику использования")
]
bot.set_my_commands(commands)

# ===== Пользовательские данные =====
user_models = {}
user_image_models = {}
user_image_settings = {}
user_waiting_for_image = {}

# Статистика использования
from collections import defaultdict

user_stats = defaultdict(lambda: {
    'messages': 0,
    'images_generated': 0,
    'images_analyzed': 0
})


def update_stats(user_id, action):
    """Обновление статистики пользователя"""
    user_stats[user_id][action] += 1


# ========== УЛУЧШЕНИЕ ПРОМПТОВ ==========

TOPIC_KEYWORDS = {
    "nature": "lush vegetation, realistic textures, depth of field",
    "city": "urban landscape, detailed architecture, bustling atmosphere",
    "portrait": "professional portrait, sharp focus on face, natural skin texture",
    "fantasy": "magical atmosphere, ethereal, otherworldly",
    "sci-fi": "futuristic, high-tech, sleek design",
    "food": "appetizing, vibrant colors, soft lighting, macro shot",
    "animal": "detailed fur/feathers, realistic anatomy, dynamic pose",
    "space": "cosmic, stars, nebula, galaxy, deep space",
    "underwater": "underwater scene, coral reef, marine life, light rays",
    "steampunk": "steampunk aesthetic, brass gears, Victorian, industrial",
    "cyberpunk": "cyberpunk, neon lights, rainy, high contrast, futuristic city",
    "anime": "anime style, cel-shaded, vibrant colors, Japanese animation",
    "watercolor": "watercolor painting, soft edges, artistic, textured paper",
    "oil painting": "oil painting, thick brush strokes, impasto, canvas texture",
    "minimalist": "minimalist, simple background, clean lines, less is more"
}

STYLE_KEYWORDS = {
    "anime": "anime style, cel-shaded, vibrant colors, Japanese animation",
    "watercolor": "watercolor painting, soft edges, artistic, textured paper",
    "oil painting": "oil painting, thick brush strokes, impasto, canvas texture",
    "cyberpunk": "cyberpunk aesthetic, neon lights, rainy, high contrast",
    "steampunk": "steampunk style, brass gears, Victorian, industrial",
    "minimalist": "minimalist, simple background, clean lines, less is more",
    "photorealistic": "photorealistic, hyper-realistic, DSLR, 8k, highly detailed",
    "cartoon": "cartoon style, vibrant, exaggerated features",
    "3d render": "3D render, octane render, blender, c4d, detailed textures"
}

LIGHTING_KEYWORDS = {
    "cinematic": "cinematic lighting, volumetric light, moody atmosphere",
    "golden hour": "golden hour, warm sunlight, long shadows, sunset glow",
    "studio": "studio lighting, softbox, well-lit, no harsh shadows",
    "neon": "neon lighting, vibrant glow, dark background, reflective surfaces",
    "dramatic": "dramatic lighting, chiaroscuro, high contrast, spotlight",
    "natural": "natural lighting, soft diffused light, daylight",
    "moody": "moody atmosphere, dim light, shadows, mysterious"
}

COMPOSITION_KEYWORDS = {
    "close-up": "close-up shot, detailed, shallow depth of field, macro",
    "wide": "wide angle, panoramic, expansive view, landscape",
    "aerial": "aerial view, drone shot, bird's eye perspective, top-down",
    "low angle": "low angle shot, dramatic perspective, heroic, upward view",
    "portrait": "portrait composition, rule of thirds, centered subject",
    "symmetrical": "symmetrical composition, balanced, geometric"
}

MODEL_QUALITY_BOOST = {
    "flux": "8k, photorealistic, ultra-detailed, sharp focus, volumetric lighting, HDR",
    "dalle-3": "high quality, detailed, vibrant colors, natural lighting, professional",
    "sdxl": "masterpiece, best quality, highly detailed, intricate details, award-winning",
    "playground-v2.5": "professional, detailed, 8k, artistic, creative composition",
    "midjourney": "award winning, stunning, intricate details, breathtaking --ar 16:9 --style expressive"
}


def detect_topic(prompt):
    prompt_lower = prompt.lower()
    detected = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if topic in prompt_lower:
            detected.append(keywords)
    return ", ".join(detected) if detected else ""


def detect_style(prompt):
    prompt_lower = prompt.lower()
    detected = []
    for style, keywords in STYLE_KEYWORDS.items():
        if style in prompt_lower:
            detected.append(keywords)
    return ", ".join(detected) if detected else ""


def detect_lighting(prompt):
    prompt_lower = prompt.lower()
    detected = []
    for lighting, keywords in LIGHTING_KEYWORDS.items():
        if lighting in prompt_lower:
            detected.append(keywords)
    return ", ".join(detected) if detected else ""


def detect_composition(prompt):
    prompt_lower = prompt.lower()
    detected = []
    for comp, keywords in COMPOSITION_KEYWORDS.items():
        if comp in prompt_lower:
            detected.append(keywords)
    return ", ".join(detected) if detected else ""


def clean_prompt(prompt):
    """Очистка промпта от лишних символов"""
    prompt = re.sub(r',+', ',', prompt)
    prompt = re.sub(r'\s+,', ',', prompt)
    prompt = re.sub(r',\s+', ', ', prompt)
    prompt = re.sub(r'\.+', '.', prompt)
    return prompt.strip().strip(',').strip()


def improve_prompt(user_prompt, model):
    """Улучшение промпта для генерации изображений"""
    user_prompt = user_prompt.strip().rstrip(',.')

    topics = detect_topic(user_prompt)
    style = detect_style(user_prompt)
    lighting = detect_lighting(user_prompt)
    composition = detect_composition(user_prompt)

    if not lighting:
        lighting = LIGHTING_KEYWORDS.get("cinematic", "cinematic lighting")
    if not composition:
        composition = COMPOSITION_KEYWORDS.get("wide", "professional composition, rule of thirds")

    enhanced_parts = [user_prompt]
    if topics:
        enhanced_parts.append(topics)
    if style:
        enhanced_parts.append(style)
    if lighting:
        enhanced_parts.append(lighting)
    if composition:
        enhanced_parts.append(composition)

    quality_boost = MODEL_QUALITY_BOOST.get(model, "high quality, detailed")
    enhanced_parts.append(quality_boost)

    final_prompt = ", ".join(enhanced_parts)
    final_prompt = clean_prompt(final_prompt)

    return final_prompt


# ===== КОМАНДА START =====
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "🤖 Я многофункциональный ИИ-бот с поддержкой:\n"
        "✨ Генерации текста (несколько моделей)\n"
        "🎨 Генерации изображений (5 моделей, автоматическое улучшение промптов)\n"
        "🔍 Анализа изображений\n\n"
        "📖 Используй /help для просмотра всех команд и возможностей!"
    )


# ===== СТАТИСТИКА =====
@bot.message_handler(commands=['stats'])
def show_stats(message):
    user_id = message.from_user.id
    stats = user_stats.get(user_id, {'messages': 0, 'images_generated': 0, 'images_analyzed': 0})

    bot.send_message(
        message.chat.id,
        f"📊 *Ваша статистика использования*\n\n"
        f"💬 Сообщений отправлено: {stats['messages']}\n"
        f"🎨 Изображений сгенерировано: {stats['images_generated']}\n"
        f"🔍 Изображений проанализировано: {stats['images_analyzed']}\n\n"
        f"Продолжай в том же духе! 🚀",
        parse_mode="Markdown"
    )


# ===== ВЫБОР ТЕКСТОВОЙ МОДЕЛИ =====
@bot.message_handler(commands=['model'])
def choose_model(message):
    keyboard = types.InlineKeyboardMarkup()
    current_model = user_models.get(message.from_user.id, Config.DEFAULT_MODEL)

    for name, model_id in Config.AVAILABLE_MODELS.items():
        button_text = f"✅ {name}" if model_id == current_model else name
        keyboard.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"model:{model_id}"
        ))

    bot.send_message(
        message.chat.id,
        f"🤖 *Выбор модели для текста*\n\n"
        f"Текущая модель: *{current_model}*\n\n"
        f"Выбери новую модель:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("model:"))
def set_model(call):
    model_id = call.data.split(":")[1]
    user_models[call.from_user.id] = model_id

    model_name = next((name for name, mid in Config.AVAILABLE_MODELS.items() if mid == model_id), model_id)

    bot.answer_callback_query(call.id, f"Модель выбрана: {model_name}")
    bot.edit_message_text(
        f"✅ Модель для текста успешно изменена на:\n*{model_name}*",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown"
    )


# ===== ВЫБОР МОДЕЛИ ДЛЯ ИЗОБРАЖЕНИЙ =====
@bot.message_handler(commands=['image_model'])
def choose_image_model(message):
    keyboard = types.InlineKeyboardMarkup()
    current_model = user_image_models.get(message.from_user.id, Config.DEFAULT_IMAGE_MODEL)

    for name, model_id in Config.AVAILABLE_IMAGE_MODELS.items():
        button_text = f"✅ {name}" if model_id == current_model else name
        keyboard.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"img_model:{model_id}"
        ))

    bot.send_message(
        message.chat.id,
        f"🎨 *Выбор модели для генерации изображений*\n\n"
        f"Текущая модель: *{current_model}*\n\n"
        f"Выбери новую модель:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("img_model:"))
def set_image_model(call):
    model_id = call.data.split(":")[1]
    user_image_models[call.from_user.id] = model_id

    model_name = next((name for name, mid in Config.AVAILABLE_IMAGE_MODELS.items() if mid == model_id), model_id)

    bot.answer_callback_query(call.id, f"Модель изображений выбрана: {model_name}")
    bot.edit_message_text(
        f"✅ Модель для изображений успешно изменена на:\n*{model_name}*",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown"
    )


# ===== НАСТРОЙКИ ГЕНЕРАЦИИ ИЗОБРАЖЕНИЙ =====
@bot.message_handler(commands=['image_settings'])
def image_settings_command(message):
    user_id = message.from_user.id
    current_model = user_image_models.get(user_id, Config.DEFAULT_IMAGE_MODEL)
    settings = Config.IMAGE_MODEL_SETTINGS.get(current_model)
    current_size = user_image_settings.get(user_id, {}).get('size', settings['default_size'])

    keyboard = types.InlineKeyboardMarkup()

    sizes = ["1024x1024", "1024x1792", "1792x1024", "512x512"]
    for size in sizes:
        button_text = f"✅ {size}" if size == current_size else f"📐 {size}"
        keyboard.add(types.InlineKeyboardButton(
            button_text,
            callback_data=f"set_size:{size}"
        ))

    bot.send_message(
        message.chat.id,
        f"⚙️ *Настройки генерации изображений*\n\n"
        f"Текущая модель: *{settings['name']}*\n"
        f"Текущий размер: *{current_size}*\n\n"
        f"Выбери размер изображения:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("set_size:"))
def set_image_size(call):
    size = call.data.replace("set_size:", "")
    user_id = call.from_user.id

    if user_id not in user_image_settings:
        user_image_settings[user_id] = {}

    user_image_settings[user_id]['size'] = size

    bot.answer_callback_query(call.id, f"Размер установлен: {size}")
    bot.edit_message_text(
        f"✅ Размер изображения изменен на: *{size}*\n\n"
        f"Теперь все изображения будут генерироваться в этом размере.",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown"
    )


# ===== ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ =====
def generate_image_thread(message, raw_mode=False):
    prompt = message.text.replace("/image", "").replace("/image_raw", "").strip()

    if prompt.endswith("--raw"):
        raw_mode = True
        prompt = prompt.replace("--raw", "").strip()

    if not prompt:
        bot.reply_to(
            message,
            "❌ Напиши описание после команды\n\n"
            "📝 Пример: `/image красивый закат на море`\n"
            "📝 Пример без улучшений: `/image_raw sunset` или `/image sunset --raw`",
            parse_mode="Markdown"
        )
        return

    user_id = message.from_user.id
    model = user_image_models.get(user_id, Config.DEFAULT_IMAGE_MODEL)
    settings = Config.IMAGE_MODEL_SETTINGS.get(model, Config.IMAGE_MODEL_SETTINGS["flux"])
    user_size = user_image_settings.get(user_id, {}).get('size', settings.get('default_size', '1024x1024'))

    if raw_mode:
        final_prompt = prompt
        logging.info(f"Raw mode: {final_prompt}")
    else:
        final_prompt = improve_prompt(prompt, model)
        logging.info(f"Original: {prompt} -> Enhanced: {final_prompt}")

    status_msg = bot.send_message(
        message.chat.id,
        f"🎨 Генерирую изображение...\n"
        f"📷 Модель: *{settings['name']}*\n"
        f"📐 Размер: *{user_size}*",
        parse_mode="Markdown"
    )
    bot.send_chat_action(message.chat.id, "upload_photo")

    try:
        generation_params = {
            "model": model,
            "prompt": final_prompt,
            "response_format": "url"
        }

        if settings.get("supports_size"):
            generation_params["size"] = user_size
        if settings.get("supports_quality"):
            generation_params["quality"] = settings.get("quality", "hd")

        logging.info(f"Generation params: {generation_params}")

        response = client.images.generate(**generation_params)
        image_url = response.data[0].url

        bot.edit_message_text(
            f"📥 Скачиваю изображение...",
            message.chat.id,
            status_msg.message_id
        )

        img_response = requests.get(image_url, timeout=Config.REQUEST_TIMEOUT)
        img_response.raise_for_status()
        image_bytes = BytesIO(img_response.content)
        image_bytes.name = "image.png"

        bot.delete_message(message.chat.id, status_msg.message_id)

        caption = (
            f"🎨 *Промпт:* {prompt}\n"
            f"📷 *Модель:* {settings['name']}\n"
            f"📐 *Размер:* {generation_params.get('size', 'авто')}"
        )
        if not raw_mode:
            caption += "\n✨ *Автоулучшение:* включено"

        bot.send_photo(message.chat.id, image_bytes, caption=caption, parse_mode="Markdown")

        # Обновляем статистику
        update_stats(user_id, 'images_generated')

        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(
            types.InlineKeyboardButton("🔄 Регенерировать", callback_data=f"regen:{prompt}:{raw_mode}"),
            types.InlineKeyboardButton("🎨 Сменить модель", callback_data="quick_model_change")
        )
        bot.send_message(message.chat.id, "💡 Что дальше?", reply_markup=keyboard)

    except Exception as e:
        logging.error(f"Ошибка генерации ({model}): {e}")

        fallback_models = ["flux", "dalle-3", "sdxl", "playground-v2.5"]
        fallback_models = [m for m in fallback_models if m != model]

        for fallback in fallback_models:
            try:
                logging.info(f"Trying fallback: {fallback}")
                fallback_settings = Config.IMAGE_MODEL_SETTINGS.get(fallback)

                bot.edit_message_text(
                    f"⚠️ Пробую резервную модель: {fallback_settings['name']}...",
                    message.chat.id,
                    status_msg.message_id
                )

                fallback_prompt = prompt if raw_mode else improve_prompt(prompt, fallback)
                fallback_params = {
                    "model": fallback,
                    "prompt": fallback_prompt,
                    "response_format": "url"
                }

                if fallback_settings.get("supports_size"):
                    fallback_params["size"] = user_size
                if fallback_settings.get("supports_quality"):
                    fallback_params["quality"] = fallback_settings.get("quality")

                response = client.images.generate(**fallback_params)
                image_url = response.data[0].url

                img_response = requests.get(image_url, timeout=Config.REQUEST_TIMEOUT)
                img_response.raise_for_status()
                image_bytes = BytesIO(img_response.content)
                image_bytes.name = "image.png"

                bot.delete_message(message.chat.id, status_msg.message_id)

                caption = (
                    f"🎨 *Промпт:* {prompt}\n"
                    f"📷 *Модель:* {fallback_settings['name']} (резервная)\n"
                    f"📐 *Размер:* {fallback_params.get('size', 'авто')}"
                )

                bot.send_photo(message.chat.id, image_bytes, caption=caption, parse_mode="Markdown")
                update_stats(user_id, 'images_generated')
                return

            except Exception as fallback_error:
                logging.error(f"Fallback {fallback} failed: {fallback_error}")
                continue

        try:
            bot.edit_message_text(
                "❌ Ошибка генерации изображения\n\n"
                "Все модели недоступны. Попробуйте:\n"
                "• Сменить модель через /image_model\n"
                "• Попробовать позже\n"
                "• Упростить описание",
                message.chat.id,
                status_msg.message_id
            )
        except:
            bot.send_message(
                message.chat.id,
                "❌ Ошибка генерации. Попробуйте позже."
            )


@bot.message_handler(commands=['image'])
def handle_image(message):
    threading.Thread(target=generate_image_thread, args=(message, False), daemon=True).start()


@bot.message_handler(commands=['image_raw'])
def handle_image_raw(message):
    threading.Thread(target=generate_image_thread, args=(message, True), daemon=True).start()


@bot.callback_query_handler(func=lambda call: call.data.startswith("regen:"))
def regenerate_image(call):
    data = call.data.replace("regen:", "").split(":", 1)
    prompt = data[0]
    raw_mode = data[1].lower() == "true" if len(data) == 2 else False

    bot.answer_callback_query(call.id, "🔄 Регенерирую...")

    class FakeMessage:
        def __init__(self, chat_id, text, user):
            self.chat = type('obj', (object,), {'id': chat_id})
            self.text = f"/image {text}"
            self.from_user = user

    fake_msg = FakeMessage(call.message.chat.id, prompt, call.from_user)
    threading.Thread(target=generate_image_thread, args=(fake_msg, raw_mode), daemon=True).start()


@bot.callback_query_handler(func=lambda call: call.data == "quick_model_change")
def quick_model_change(call):
    bot.answer_callback_query(call.id)
    choose_image_model(call.message)


# ===== АНАЛИЗ ИЗОБРАЖЕНИЙ =====
@bot.message_handler(commands=['analyze'])
def analyze_command(message):
    user_waiting_for_image[message.from_user.id] = {'waiting': True, 'prompt': None}
    bot.send_message(
        message.chat.id,
        "📸 *Режим анализа активирован*\n\n"
        "Отправь мне фото для анализа.",
        parse_mode="Markdown"
    )


def analyze_image_thread(message, photo, user_prompt=None):
    try:
        status_msg = bot.send_message(message.chat.id, "🔍 Анализирую изображение...")
        bot.send_chat_action(message.chat.id, "typing")

        file_info = bot.get_file(photo.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        image_base64 = base64.b64encode(downloaded_file).decode('utf-8')

        prompt = user_prompt or "Опиши подробно что изображено на этом фото."

        response = client.chat.completions.create(
            model=Config.VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                        }
                    ]
                }
            ],
        )

        analysis = response.choices[0].message.content
        bot.delete_message(message.chat.id, status_msg.message_id)

        max_length = Config.MAX_MESSAGE_LENGTH
        if len(analysis) > max_length:
            for i in range(0, len(analysis), max_length):
                bot.send_message(message.chat.id, analysis[i:i + max_length])
        else:
            bot.send_message(
                message.chat.id,
                f"🔍 *Анализ изображения:*\n\n{analysis}",
                parse_mode="Markdown"
            )

        # Обновляем статистику
        update_stats(message.from_user.id, 'images_analyzed')

    except Exception as e:
        logging.error(f"Ошибка анализа: {e}")
        try:
            bot.edit_message_text(
                f"❌ Ошибка при анализе изображения. Попробуйте ещё раз.",
                message.chat.id,
                status_msg.message_id
            )
        except:
            bot.send_message(message.chat.id, "❌ Ошибка при анализе изображения.")


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.from_user.id
    photo = message.photo[-1]
    user_prompt = message.caption if message.caption else None

    if user_id in user_waiting_for_image and user_waiting_for_image[user_id]['waiting']:
        user_waiting_for_image[user_id]['waiting'] = False
        threading.Thread(
            target=analyze_image_thread,
            args=(message, photo, user_prompt),
            daemon=True
        ).start()
    else:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("🔍 Анализировать", callback_data=f"analyze_photo:{photo.file_id}"),
            types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_photo")
        )
        bot.send_message(message.chat.id, "📸 Что сделать с этим фото?", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith("analyze_photo:"))
def analyze_photo_callback(call):
    file_id = call.data.split(":")[1]
    bot.answer_callback_query(call.id, "🔍 Анализирую...")

    class PhotoObj:
        def __init__(self, file_id):
            self.file_id = file_id

    photo = PhotoObj(file_id)
    threading.Thread(target=analyze_image_thread, args=(call.message, photo, None), daemon=True).start()
    bot.edit_message_text("🔍 Начинаю анализ...", call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda call: call.data == "cancel_photo")
def cancel_photo(call):
    bot.answer_callback_query(call.id, "❌ Отменено")
    bot.delete_message(call.message.chat.id, call.message.message_id)


# ===== ОБЩЕНИЕ С ИИ =====
def chat_thread(message):
    model = user_models.get(message.from_user.id, Config.DEFAULT_MODEL)
    bot.send_chat_action(message.chat.id, "typing")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": message.text}],
            web_search=False
        )
        text = response.choices[0].message.content

        # Обновляем статистику
        update_stats(message.from_user.id, 'messages')

        max_length = Config.MAX_MESSAGE_LENGTH
        if len(text) > max_length:
            for i in range(0, len(text), max_length):
                bot.send_message(message.chat.id, text[i:i + max_length])
        else:
            bot.send_message(message.chat.id, text)

    except Exception as e:
        logging.error(f"Ошибка генерации текста: {e}")
        bot.send_message(
            message.chat.id,
            f"❌ Ошибка при обработке запроса. Попробуйте позже или смените модель через /model"
        )


@bot.message_handler(func=lambda message: not message.text.startswith("/"), content_types=['text'])
def handle_text(message):
    threading.Thread(target=chat_thread, args=(message,), daemon=True).start()


# ===== ИНСТРУКЦИЯ =====
@bot.message_handler(commands=['help'])
def show_help(message):
    current_model = user_models.get(message.from_user.id, Config.DEFAULT_MODEL)
    current_image_model = user_image_models.get(message.from_user.id, Config.DEFAULT_IMAGE_MODEL)
    current_image_model_name = Config.IMAGE_MODEL_SETTINGS.get(current_image_model, {}).get('name', current_image_model)
    current_size = user_image_settings.get(message.from_user.id, {}).get('size', '1024x1024')

    help_text = f"""
📖 *ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ*

🤖 Многофункциональный ИИ-бот

━━━━━━━━━━━━━━━━━━━━━━

🗨️ *ГЕНЕРАЦИЯ ТЕКСТА*
/model - выбрать модель

*Доступные модели:*
• GPT-4.1 - самая продвинутая
• GPT-4o - быстрая и умная
• GPT-4 - классическая
• GPT-4o-mini - быстрые ответы
• DeepSeek V3 - альтернатива

━━━━━━━━━━━━━━━━━━━━━━

🎨 *ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ*
/image_model - выбрать модель
/image_settings - настроить размер
/image <описание> - сгенерировать
/image_raw <описание> - без улучшений

*Модели:*
• Flux (рекомендуется)
• DALL-E 3
• Stable Diffusion XL
• Playground v2.5
• Midjourney

━━━━━━━━━━━━━━━━━━━━━━

🔍 *АНАЛИЗ ИЗОБРАЖЕНИЙ*
/analyze - анализировать фото

━━━━━━━━━━━━━━━━━━━━━━

📊 *СТАТИСТИКА*
/stats - показать статистику

━━━━━━━━━━━━━━━━━━━━━━

⚙️ *ТЕКУЩИЕ НАСТРОЙКИ*
✅ Текст: `{current_model}`
🎨 Изображения: `{current_image_model_name}`
📐 Размер: `{current_size}`

━━━━━━━━━━━━━━━━━━━━━━

💡 Просто напиши мне сообщение!
"""
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")


# ===== GRACEFUL SHUTDOWN =====
def signal_handler(sig, frame):
    """Обработка сигналов завершения"""
    logging.info("🛑 Получен сигнал остановки")
    logging.info("👋 Бот завершает работу...")
    bot.stop_polling()
    sys.exit(0)


# ===== ЗАПУСК БОТА =====
if __name__ == "__main__":
    # Регистрация обработчиков сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logging.info("=" * 50)
    logging.info("🤖 Бот запущен и готов к работе!")
    logging.info("📋 Команды загружены")
    logging.info("✅ Система улучшения промптов активна")
    logging.info("=" * 50)

    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except KeyboardInterrupt:
        logging.info("Бот остановлен пользователем")
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")

