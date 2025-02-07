import asyncio
import logging.config
import yaml
from config.config import load_config
from database.db_connection import *
from telethon_client.handlers.parser import set_bot
from telethon_client.start_telethon import setup_handlers
from aiogram_bot.handlers import user_handlers

from aiogram import Bot, Dispatcher
from telethon import TelegramClient

config = load_config()  # Загрузка config.py

bot = Bot(token=config.aiogram_bot.token)
dp = Dispatcher()

async def start_telethon():
    # Инициализация Telethon Клиента
    client = TelegramClient(
        session='news_parser',
        device_model="iPhone 13 Pro Max",
        system_version="14.8.1",
        app_version="8.4",
        api_id=config.telethon_client.api_id,
        api_hash=config.telethon_client.api_hash
    )
    client.parse_mode = 'html'
    channels = get_channels() # Загрузка каналов для прослушивания

    set_bot(bot)

    # Загрузка обработчиков
    setup_handlers(client, channels)

    logger.info("Авторизация в аккаунт")
    client.start(password=config.telethon_client.password)

    logger.info("Авторизация успешна")
    logger.info("Парсер новостных каналов успешно запущен")
    await client.run_until_disconnected()


async def start_aiogram():
    # Создание бота, диспетчера и клиента
    dp.include_router(user_handlers.router)
    await bot.delete_webhook(drop_pending_updates=True) # Дроп накопившихся за время отсутствия бота в сети, апдейты
    logger.info("Бот успешно запущен")
    await dp.start_polling(bot)



async def main():
    await asyncio.gather(start_telethon(), start_aiogram()) # Запуск Бота и Телеграм Парсера асинхронно


# TODO: Надо расстащить куски аиограм и телетон в два модуля оставив тут мейн
if __name__ == '__main__':
    # Подключаем словарь конфигурации логирования
    with open('config/logs_settings.yaml', 'rt') as f:
        log_config = yaml.safe_load(f.read())
    logging.config.dictConfig(log_config)
    logger = logging.getLogger(__name__)
    try:
        # Создание цикла событий
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Запуск основной функции в текущем цикле событий
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Выполнение скрипта прервано пользователем.")
    finally:
        logger.info("Завершение работы скрипта.")
