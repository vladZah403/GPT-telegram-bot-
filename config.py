"""
Конфигурация для Telegram AI Bot
Управление переменными окружения и настройками
"""

import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()


class Config:
    """Класс конфигурации бота"""
    
    # ===== ОБЯЗАТЕЛЬНЫЕ ПАРАМЕТРЫ =====
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    # ===== МОДЕЛИ ПО УМОЛЧАНИЮ =====
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4")
    DEFAULT_IMAGE_MODEL = os.getenv("DEFAULT_IMAGE_MODEL", "flux")
    VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4")
    
    # ===== НАСТРОЙКИ ЛОГИРОВАНИЯ =====
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # ===== НАСТРОЙКИ СООБЩЕНИЙ =====
    MAX_MESSAGE_LENGTH = int(os.getenv("MAX_MESSAGE_LENGTH", "4096"))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))
    
    # ===== ДОСТУПНЫЕ МОДЕЛИ =====
    AVAILABLE_MODELS = {
        "GPT-4.1": "gpt-4.1",
        "GPT-4o": "gpt-4o",
        "GPT-4 (Рекомендуется)": "gpt-4",
        "GPT-4o-mini": "gpt-4o-mini",
        "DeepSeek V3": "deepseek-v3"
    }
    
    AVAILABLE_IMAGE_MODELS = {
        "Flux (Рекомендуется)": "flux",
        "DALL-E 3": "dalle-3",
        "Stable Diffusion XL": "sdxl",
        "Playground v2.5": "playground-v2.5",
        "Midjourney": "midjourney"
    }
    
    # ===== НАСТРОЙКИ ДЛЯ МОДЕЛЕЙ ИЗОБРАЖЕНИЙ =====
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
    
    @classmethod
    def validate(cls):
        """Проверка обязательных параметров конфигурации"""
        if not cls.BOT_TOKEN:
            raise ValueError(
                "\n❌ BOT_TOKEN не найден!\n"
                "📝 Создайте файл .env на основе .env.example\n"
                "🔑 Получите токен от @BotFather в Telegram\n"
                "💡 Добавьте в .env: BOT_TOKEN=ваш_токен_здесь\n"
            )
        
        if cls.BOT_TOKEN == "your_bot_token_here":
            raise ValueError(
                "\n❌ BOT_TOKEN не настроен!\n"
                "🔑 Замените 'your_bot_token_here' на реальный токен от @BotFather\n"
            )
        
        print("✅ Конфигурация успешно загружена")
        print(f"🤖 Модель для текста: {cls.DEFAULT_MODEL}")
        print(f"🎨 Модель для изображений: {cls.DEFAULT_IMAGE_MODEL}")
        print(f"📊 Уровень логирования: {cls.LOG_LEVEL}")
        
        return True


# Автоматическая валидация при импорте
if __name__ != "__main__":
    try:
        Config.validate()
    except ValueError as e:
        print(e)
        exit(1)
