import asyncio
import logging.config
import yaml
from config.config import load_config
from database.db_connection import *
from telethon_client.start_telethon import setup_handlers, update_engagement_for_active_cluster_posts
from aiogram_bot.handlers import user_handlers
from telethon_client.handlers.handler_utils import engagement_publisher_task, ad_filter_task

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
        app_version="10.1",
        api_id=config.telethon_client.api_id,
        api_hash=config.telethon_client.api_hash
    )
    client.parse_mode = 'html'
    channels = get_channels() # Загрузка каналов для прослушивания
    logger.debug("Список каналов: %s", channels)

    # Загрузка обработчиков
    setup_handlers(client, channels, bot)
    logger.info("Авторизация в аккаунт")
    await client.start(password=config.telethon_client.password)
    logger.info("Авторизация успешна")
    logger.info("Парсер новостных каналов успешно запущен")
    # Запуск таска обновления просмотров
    engagement_task = asyncio.create_task(update_engagement_for_active_cluster_posts(client))
    ad_task = asyncio.create_task(ad_filter_task())
    await client.run_until_disconnected()
    # Остановить таск при отключении клиента
    engagement_task.cancel()
    ad_task.cancel()


async def start_aiogram():
    # Создание бота, диспетчера и клиента
    dp.include_router(user_handlers.router)
    await bot.delete_webhook(drop_pending_updates=True) # Дроп накопившихся за время отсутствия бота в сети, апдейты
    logger.info("Бот успешно запущен")
    await dp.start_polling(bot)



async def main():
    publisher = asyncio.create_task(engagement_publisher_task(bot))
    await asyncio.gather(start_telethon(), start_aiogram(), publisher) # Запуск Бота, Телеграм Парсера и публикации кластеров асинхронно


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
