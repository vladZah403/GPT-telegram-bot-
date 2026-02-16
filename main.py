import telebot
from telebot import types
from g4f.client import Client
import requests
from io import BytesIO
import threading
import logging
import base64
import re  # Додано для очищення промптів

# ===== Настройка логирования =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ===== Настройки бота =====
BOT_TOKEN = "8094757760:AAHRKESZHJFrDNtAVcWvf56N3FKu0ZSfFmA"
bot = telebot.TeleBot(BOT_TOKEN)
client = Client()

# ===== Установка команд бота =====
commands = [
    telebot.types.BotCommand("/start", "Начать работу с ботом"),
    telebot.types.BotCommand("/help", "Показать инструкцию по использованию бота"),
    telebot.types.BotCommand("/model", "Выбрать модель для общения с ИИ"),
    telebot.types.BotCommand("/image_model", "Выбрать модель для генерации изображений"),
    telebot.types.BotCommand("/image_settings", "Настройки генерации изображений"),
    telebot.types.BotCommand("/image", "Сгенерировать изображение по описанию"),
    telebot.types.BotCommand("/image_raw", "Сгенерировать без автоматического улучшения промпта"),
    telebot.types.BotCommand("/analyze", "Анализировать изображение")
]
bot.set_my_commands(commands)

# ===== Модели и пользователи =====
DEFAULT_MODEL = "gpt-4"
DEFAULT_IMAGE_MODEL = "flux"
VISION_MODEL = "gpt-4"

user_models = {}
user_image_models = {}
user_image_settings = {}
user_waiting_for_image = {}

# Доступные текстовые модели
AVAILABLE_MODELS = {
    "GPT-4.1": "gpt-4.1",
    "GPT-4o": "gpt-4o",
    "GPT-4 (Рекомендуется) ": "gpt-4",
    "GPT-4o-mini": "gpt-4o-mini",
    "DeepSeek V3": "deepseek-v3"
}

# Доступные модели для генерации изображений
AVAILABLE_IMAGE_MODELS = {
    "Flux (Рекомендуется)": "flux",
    "DALL-E 3": "dalle-3",
    "Stable Diffusion XL": "sdxl",
    "Playground v2.5": "playground-v2.5",
    "Midjourney": "midjourney"
}

# Настройки для разных моделей изображений
IMAGE_MODEL_SETTINGS = {
    "flux": {
        "name": "Flux",
        "supports_quality": True,
        "supports_size": True,
        "default_size": "1024x1024",
        "quality": "hd"
    },
    "dalle-3": {
        "name": "DALL-E 3",
        "supports_quality": True,
        "supports_size": True,
        "default_size": "1024x1024",
        "quality": "hd"
    },
    "sdxl": {
        "name": "Stable Diffusion XL",
        "supports_quality": False,
        "supports_size": True,
        "default_size": "1024x1024"
    },
    "playground-v2.5": {
        "name": "Playground v2.5",
        "supports_quality": False,
        "supports_size": True,
        "default_size": "1024x1024"
    },
    "midjourney": {
        "name": "Midjourney",
        "supports_quality": True,
        "supports_size": True,
        "default_size": "1024x1024"
    }
}

# ========== ПОКРАЩЕННЯ ПРОМПТІВ ==========

# 1️⃣ Словники для автоматичного визначення контексту

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

# 2️⃣ Модель-специфічні бустери якості
MODEL_QUALITY_BOOST = {
    "flux": "8k, photorealistic, ultra-detailed, sharp focus, volumetric lighting, HDR",
    "dalle-3": "high quality, detailed, vibrant colors, natural lighting, professional",
    "sdxl": "masterpiece, best quality, highly detailed, intricate details, award-winning",
    "playground-v2.5": "professional, detailed, 8k, artistic, creative composition",
    "midjourney": "award winning, stunning, intricate details, breathtaking --ar 16:9 --style expressive"
}


# 3️⃣ Функції визначення категорій
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
    """Видаляє зайві коми, пробіли, крапки."""
    prompt = re.sub(r',+', ',', prompt)
    prompt = re.sub(r'\s+,', ',', prompt)
    prompt = re.sub(r',\s+', ', ', prompt)
    prompt = re.sub(r'\.+', '.', prompt)
    return prompt.strip().strip(',').strip()


def improve_prompt(user_prompt, model):
    """
    Головна функція покращення промпта.
    Визначає тему, стиль, освітлення, композицію та додає модель-специфічний буст.
    """
    user_prompt = user_prompt.strip().rstrip(',.')

    # 1. Визначаємо категорії
    topics = detect_topic(user_prompt)
    style = detect_style(user_prompt)
    lighting = detect_lighting(user_prompt)
    composition = detect_composition(user_prompt)

    # 2. Базові дескриптори (якщо щось не знайдено – додаємо розумне замовчування)
    if not lighting:
        lighting = LIGHTING_KEYWORDS.get("cinematic", "cinematic lighting")
    if not composition:
        composition = COMPOSITION_KEYWORDS.get("wide", "professional composition, rule of thirds")

    # 3. Збираємо фінальний промпт
    enhanced_parts = [user_prompt]
    if topics:
        enhanced_parts.append(topics)
    if style:
        enhanced_parts.append(style)
    if lighting:
        enhanced_parts.append(lighting)
    if composition:
        enhanced_parts.append(composition)

    # 4. Додаємо модель-специфічний буст
    quality_boost = MODEL_QUALITY_BOOST.get(model, "high quality, detailed")
    enhanced_parts.append(quality_boost)

    # 5. Об'єднуємо через кому та очищаємо
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


# ===== ВЫБОР ТЕКСТОВОЙ МОДЕЛИ =====
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

    model_name = next((name for name, mid in AVAILABLE_MODELS.items() if mid == model_id), model_id)

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
    current_model = user_image_models.get(message.from_user.id, DEFAULT_IMAGE_MODEL)

    for name, model_id in AVAILABLE_IMAGE_MODELS.items():
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

    model_name = next((name for name, mid in AVAILABLE_IMAGE_MODELS.items() if mid == model_id), model_id)

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
    current_model = user_image_models.get(user_id, DEFAULT_IMAGE_MODEL)
    settings = IMAGE_MODEL_SETTINGS.get(current_model)
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
    # Видаляємо команду /image або /image_raw
    prompt = message.text.replace("/image", "").replace("/image_raw", "").strip()

    # Перевіряємо, чи користувач додав --raw в кінці (навіть для /image)
    if prompt.endswith("--raw"):
        raw_mode = True
        prompt = prompt.replace("--raw", "").strip()

    if not prompt:
        bot.reply_to(
            message,
            "❌ Напиши описание после команды\n\n"
            "📝 Пример: `/image красивый закат на море`\n"
            "📝 Пример без улучшений: `/image_raw sunset` або `/image sunset --raw`\n\n"
            "💡 *Советы для лучшего результата:*\n"
            "• Используй описательные прилагательные\n"
            "• Укажи стиль (реалистичный, аниме, акварель)\n"
            "• Добавь детали освещения и настроения\n"
            "• Пиши на английском для лучшего результата\n\n"
            "🎨 Примеры хороших промптов:\n"
            "`/image a serene mountain landscape at sunset, photorealistic`\n"
            "`/image anime girl with blue hair, studio ghibli style`\n"
            "`/image futuristic city with neon lights, cyberpunk`",
            parse_mode= None
        )
        return

    user_id = message.from_user.id
    model = user_image_models.get(user_id, DEFAULT_IMAGE_MODEL)
    settings = IMAGE_MODEL_SETTINGS.get(model, IMAGE_MODEL_SETTINGS["flux"])

    user_size = user_image_settings.get(user_id, {}).get('size', settings.get('default_size', '1024x1024'))

    # --- ПОКРАЩЕННЯ ПРОМПТУ ---
    if raw_mode:
        final_prompt = prompt
        logging.info(f"Raw mode: промпт без изменений: {final_prompt}")
    else:
        final_prompt = improve_prompt(prompt, model)
        logging.info(f"Оригинальный промпт: {prompt}")
        logging.info(f"Улучшенный промпт: {final_prompt}")

    status_msg = bot.send_message(
        message.chat.id,
        f"🎨 Генерирую изображение...\n"
        f"📷 Модель: *{settings['name']}*\n"
        f"📐 Размер: *{user_size}*\n"
        f"✨ {'Промпт улучшен' if not raw_mode else 'Без улучшений'}...",
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

        # Тут можна додати negative_prompt, якщо модель підтримує
        # generation_params["negative_prompt"] = "ugly, deformed, blurry, low quality"

        logging.info(f"Параметры генерации: {generation_params}")

        response = client.images.generate(**generation_params)
        image_url = response.data[0].url
        logging.info(f"Image URL: {image_url}")

        bot.edit_message_text(
            f"🎨 Генерация завершена!\n📥 Скачиваю изображение...",
            message.chat.id,
            status_msg.message_id
        )

        img_response = requests.get(image_url, timeout=60)
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
        if generation_params.get('quality'):
            caption += f"\n💎 *Качество:* {generation_params['quality']}"

        bot.send_photo(
            message.chat.id,
            image_bytes,
            caption=caption,
            parse_mode="Markdown"
        )

        # Кнопки действий
        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(
            types.InlineKeyboardButton("🔄 Регенерировать", callback_data=f"regen:{prompt}:{raw_mode}"),
            types.InlineKeyboardButton("✏️ Изменить промпт", callback_data="edit_prompt")
        )
        keyboard.row(
            types.InlineKeyboardButton("🎨 Сменить модель", callback_data="quick_model_change")
        )
        bot.send_message(
            message.chat.id,
            "💡 Что дальше?",
            reply_markup=keyboard
        )

    except Exception as e:
        logging.error(f"Ошибка генерации изображения ({model}): {e}")
        # ... (тут залишаємо твою логіку fallback, вона не змінилась)
        fallback_models = ["flux", "dalle-3", "sdxl", "playground-v2.5"]
        fallback_models = [m for m in fallback_models if m != model]

        for fallback in fallback_models:
            try:
                logging.info(f"Пробую запасную модель: {fallback}")
                fallback_settings = IMAGE_MODEL_SETTINGS.get(fallback)

                bot.edit_message_text(
                    f"⚠️ Основная модель недоступна\n"
                    f"🔄 Пробую: {fallback_settings['name']}...",
                    message.chat.id,
                    status_msg.message_id
                )

                # Для fallback теж застосовуємо покращення, якщо не raw_mode
                if raw_mode:
                    fallback_prompt = prompt
                else:
                    fallback_prompt = improve_prompt(prompt, fallback)

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

                img_response = requests.get(image_url, timeout=60)
                img_response.raise_for_status()
                image_bytes = BytesIO(img_response.content)
                image_bytes.name = "image.png"

                bot.delete_message(message.chat.id, status_msg.message_id)

                caption = (
                    f"🎨 *Промпт:* {prompt}\n"
                    f"📷 *Модель:* {fallback_settings['name']} (запасная)\n"
                    f"📐 *Размер:* {fallback_params.get('size', 'авто')}"
                )
                if not raw_mode:
                    caption += "\n✨ *Автоулучшение:* включено"

                bot.send_photo(
                    message.chat.id,
                    image_bytes,
                    caption=caption,
                    parse_mode="Markdown"
                )

                keyboard = types.InlineKeyboardMarkup()
                keyboard.row(
                    types.InlineKeyboardButton("🔄 Регенерировать", callback_data=f"regen:{prompt}:{raw_mode}"),
                    types.InlineKeyboardButton("🎨 Сменить модель", callback_data="quick_model_change")
                )
                bot.send_message(
                    message.chat.id,
                    "💡 Что дальше?",
                    reply_markup=keyboard
                )
                return

            except Exception as fallback_error:
                logging.error(f"Запасная модель {fallback} не сработала: {fallback_error}")
                continue

        # Если все модели не сработали
        bot.edit_message_text(
            f"❌ *Ошибка генерации изображения*\n\n"
            f"Причина: {str(e)[:200]}\n\n"
            f"💡 *Попробуйте:*\n"
            f"• Переформулировать описание\n"
            f"• Использовать английский язык\n"
            f"• Сменить модель через /image_model\n"
            f"• Упростить запрос\n"
            f"• Попробовать позже",
            message.chat.id,
            status_msg.message_id,
            parse_mode="Markdown"
        )


@bot.message_handler(commands=['image'])
def handle_image(message):
    threading.Thread(target=generate_image_thread, args=(message, False), daemon=True).start()


@bot.message_handler(commands=['image_raw'])
def handle_image_raw(message):
    threading.Thread(target=generate_image_thread, args=(message, True), daemon=True).start()


# ===== CALLBACK ДЛЯ РЕГЕНЕРАЦИИ =====
@bot.callback_query_handler(func=lambda call: call.data.startswith("regen:"))
def regenerate_image(call):
    data = call.data.replace("regen:", "").split(":", 1)
    if len(data) == 2:
        prompt, raw_mode_str = data
        raw_mode = raw_mode_str.lower() == "true"
    else:
        prompt = data[0]
        raw_mode = False

    bot.answer_callback_query(call.id, "🔄 Регенерирую изображение...")

    class FakeMessage:
        def __init__(self, chat_id, text, user):
            self.chat = type('obj', (object,), {'id': chat_id})
            self.text = f"/image {text}"
            self.from_user = user

    fake_msg = FakeMessage(call.message.chat.id, prompt, call.from_user)
    threading.Thread(target=generate_image_thread, args=(fake_msg, raw_mode), daemon=True).start()


@bot.callback_query_handler(func=lambda call: call.data == "edit_prompt")
def edit_prompt_callback(call):
    bot.answer_callback_query(call.id, "✏️ Отправь новый промпт")
    bot.send_message(
        call.message.chat.id,
        "✏️ Отправь новое описание для генерации изображения:\n\n"
        "Используй формат: `/image описание` или `/image_raw описание`",
        parse_mode="Markdown"
    )


@bot.callback_query_handler(func=lambda call: call.data == "quick_model_change")
def quick_model_change(call):
    bot.answer_callback_query(call.id)
    choose_image_model(call.message)


# ===== АНАЛИЗ ИЗОБРАЖЕНИЙ =====
@bot.message_handler(commands=['analyze'])
def analyze_command(message):
    user_waiting_for_image[message.from_user.id] = {
        'waiting': True,
        'prompt': None
    }
    bot.send_message(
        message.chat.id,
        "📸 *Режим анализа изображений активирован*\n\n"
        "Отправь мне фото для анализа.\n\n"
        "🔍 *Варианты использования:*\n"
        "• Просто отправь фото (я опишу что на нём)\n"
        "• Добавь подпись к фото с вопросом\n\n"
        "💡 *Примеры вопросов:*\n"
        "• Что изображено на этом фото?\n"
        "• Опиши детально\n"
        "• Какие эмоции передаёт изображение?\n"
        "• Есть ли на фото текст?\n"
        "• Определи породу животного\n"
        "• Что это за место?",
        parse_mode="Markdown"
    )


def analyze_image_thread(message, photo, user_prompt=None):
    try:
        status_msg = bot.send_message(message.chat.id, "🔍 Анализирую изображение...")
        bot.send_chat_action(message.chat.id, "typing")

        file_info = bot.get_file(photo.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        image_base64 = base64.b64encode(downloaded_file).decode('utf-8')

        if user_prompt:
            prompt = user_prompt
        else:
            prompt = "Опиши подробно что изображено на этом фото. Укажи основные объекты, цвета, настроение и детали."

        response = client.chat.completions.create(
            model=VISION_MODEL,
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

        bot.delete_message(message.chat.id, status_msg.message_id)

        max_length = 4096
        if len(analysis) > max_length:
            for i in range(0, len(analysis), max_length):
                bot.send_message(message.chat.id, analysis[i:i + max_length])
        else:
            bot.send_message(
                message.chat.id,
                f"🔍 *Анализ изображения:*\n\n{analysis}",
                parse_mode="Markdown"
            )

    except Exception as e:
        logging.error(f"Ошибка анализа изображения: {e}")
        try:
            bot.edit_message_text(
                f"❌ Ошибка при анализе изображения:\n{str(e)[:300]}\n\n"
                f"💡 Попробуйте отправить фото ещё раз или используйте другое изображение.",
                message.chat.id,
                status_msg.message_id
            )
        except:
            bot.send_message(
                message.chat.id,
                f"❌ Ошибка при анализе изображения:\n{str(e)[:300]}"
            )


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
        bot.send_message(
            message.chat.id,
            "📸 Что сделать с этим фото?",
            reply_markup=keyboard
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("analyze_photo:"))
def analyze_photo_callback(call):
    file_id = call.data.split(":")[1]
    bot.answer_callback_query(call.id, "🔍 Анализирую...")

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
        "🔍 Начинаю анализ изображения...",
        call.message.chat.id,
        call.message.message_id
    )


@bot.callback_query_handler(func=lambda call: call.data == "cancel_photo")
def cancel_photo(call):
    bot.answer_callback_query(call.id, "❌ Отменено")
    bot.delete_message(call.message.chat.id, call.message.message_id)


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
        bot.send_message(
            message.chat.id,
            f"❌ Ошибка при обработке запроса:\n{str(e)[:200]}\n\n"
            f"💡 Попробуйте переформулировать вопрос или выбрать другую модель через /model"
        )


@bot.message_handler(func=lambda message: not message.text.startswith("/"), content_types=['text'])
def handle_text(message):
    threading.Thread(target=chat_thread, args=(message,), daemon=True).start()


# ===== ИНСТРУКЦИЯ =====
@bot.message_handler(commands=['help'])
def show_help(message):
    current_model = user_models.get(message.from_user.id, DEFAULT_MODEL)
    current_image_model = user_image_models.get(message.from_user.id, DEFAULT_IMAGE_MODEL)
    current_image_model_name = IMAGE_MODEL_SETTINGS.get(current_image_model, {}).get('name', current_image_model)
    current_size = user_image_settings.get(message.from_user.id, {}).get('size', '1024x1024')

    help_text = f"""
📖 *ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ БОТА*

🤖 Я многофункциональный ИИ-бот с расширенными возможностями.

━━━━━━━━━━━━━━━━━━━━━━

🗨️ *ГЕНЕРАЦИЯ ТЕКСТА*

/model - выбрать модель для общения

*Доступные модели:*
- GPT-4.1 - самая продвинутая модель
- GPT-4o - быстрая и умная
- GPT-4 - классическая версия
- GPT-4o-mini - быстрые ответы
- DeepSeek V3 - альтернативная модель

*Использование:*
Просто напиши любое сообщение, и я отвечу!

━━━━━━━━━━━━━━━━━━━━━━

🎨 *ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ*

/image_model - выбрать модель для изображений
/image_settings - настроить размер и качество
/image <описание> - сгенерировать картинку (автоулучшение)
/image_raw <описание> - сгенерировать без автоулучшения
(также можно добавить `--raw` в конец обычного /image)

*Доступные модели:*
- Flux (рекомендуется) - высокое качество
- DALL-E 3 - от OpenAI
- Stable Diffusion XL - детализация
- Playground v2.5 - креативность
- Midjourney - художественный стиль

*Доступные размеры:*
- 1024x1024 (квадрат)
- 1024x1792 (вертикаль)
- 1792x1024 (горизонталь)
- 512x512 (маленький)

*Примеры:*
`/image beautiful sunset over ocean`
`/image_raw beautiful sunset over ocean` (без улучшений)

*💡 Советы для лучшего результата:*
- Пиши на английском
- Добавляй детали и стиль
- Укажи освещение и настроение
- Будь конкретным

━━━━━━━━━━━━━━━━━━━━━━

🔍 *АНАЛИЗ ИЗОБРАЖЕНИЙ*

/analyze - активировать режим анализа

*Использование:*
1. Отправь команду /analyze
2. Отправь фото
3. Или добавь подпись с вопросом

*Примеры вопросов:*
- Что на этом фото?
- Опиши детально
- Какой это стиль?
- Есть ли текст на изображении?
- Определи породу животного

━━━━━━━━━━━━━━━━━━━━━━

⚙️ *ТЕКУЩИЕ НАСТРОЙКИ*

✅ Модель для текста: `{current_model}`
🎨 Модель для изображений: `{current_image_model_name}`
📐 Размер изображений: `{current_size}`

━━━━━━━━━━━━━━━━━━━━━━

💡 *ДОПОЛНИТЕЛЬНЫЕ ВОЗМОЖНОСТИ*

- Автоматическое улучшение промптов
- Интеллектуальное определение темы, стиля, освещения, композиции
- Режим "сырого" промпта (`--raw` или `/image_raw`)
- Fallback на другие модели при ошибке
- Кнопки быстрых действий
- Регенерация изображений
- История настроек для каждого пользователя

━━━━━━━━━━━━━━━━━━━━━━

❓ Есть вопросы? Просто напиши мне!
"""
    bot.send_message(message.chat.id, help_text, parse_mode=None)


# ===== ЗАПУСК БОТА =====
if __name__ == "__main__":
    logging.info("=" * 50)
    logging.info("🤖 Бот запущен и готов к работе! ")
    logging.info("📋 Доступные команды загружены ")
    logging.info("✅ Система улучшения промптов активирована")
    logging.info("=" * 50)
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except KeyboardInterrupt:
        logging.info("Бот остановлен пользователем")
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")