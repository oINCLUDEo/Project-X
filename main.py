import asyncio
import logging.config
import yaml
from config.config import load_config
from database.db_connection import *
from telethon_client.start_telethon import setup_handlers, update_engagement_for_active_cluster_posts
from aiogram_bot.handlers import user_handlers
from telethon_client.handlers.handler_utils import engagement_publisher_task, reputation_refresher_task

from aiogram import Bot, Dispatcher
from telethon import TelegramClient

config = load_config()  # Загрузка config.py

bot = Bot(token=config.aiogram_bot.token)
dp = Dispatcher()


async def start_telethon():
    # Используем контекстный менеджер для автоматического управления соединением
    async with TelegramClient(
            session='news_parser',
            device_model="iPhone 13 Pro Max",
            system_version="14.8.1",
            app_version="10.1",
            api_id=config.telethon_client.api_id,
            api_hash=config.telethon_client.api_hash
    ) as client:
        client.parse_mode = 'html'
        channels = get_channels()
        logger.debug("Список каналов: %s", channels)

        # Загрузка обработчиков
        setup_handlers(client, channels)
        logger.info("Авторизация в аккаунт")
        await client.start(password=config.telethon_client.password)
        logger.info("Авторизация успешна")
        logger.info("Парсер новостных каналов успешно запущен")
        # Запуск таска обновления просмотров
        engagement_task = asyncio.create_task(update_engagement_for_active_cluster_posts(client))

        try:
            # Просто ждем отключения
            await client.disconnected
        finally:
            engagement_task.cancel()
            try:
                await engagement_task
            except asyncio.CancelledError:
                pass

# TODO: Что то намудренное с перезапусками, скорее всего нужно удалить/изменить
async def start_aiogram():
    # Создание бота, диспетчера и клиента
    dp.include_router(user_handlers.router)
    # Удаление вебхука с перезапусками, чтобы сетевые сбои не валили запуск
    import asyncio as _asyncio
    from aiogram.exceptions import TelegramNetworkError as _TgNetErr
    for attempt in range(5):
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            break
        except _TgNetErr as e:
            wait_s = min(10 * (attempt + 1), 60)
            logger.warning(f"Не удалось удалить вебхук (попытка {attempt+1}/5): {e}. Повтор через {wait_s}s")
            await _asyncio.sleep(wait_s)
        except Exception as e:
            logger.warning(f"Удаление вебхука пропущено: {e}")
            break
    logger.info("Бот успешно запущен")
    await dp.start_polling(bot)



async def _run_with_restarts(name, coro_func, base_delay=5, max_delay=60):
    """Бесконечный перезапуск задачи при ошибках с экспоненциальной паузой."""
    delay = base_delay
    while True:
        try:
            logger.info(f"[SUPERVISOR] Запуск задачи: {name}")
            await coro_func()
            logger.info(f"[SUPERVISOR] Задача {name} завершилась без ошибок")
            return
        except Exception as e:
            logger.error(f"[SUPERVISOR] Задача {name} упала: {e}. Перезапуск через {delay}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)


async def main():
    publisher = asyncio.create_task(engagement_publisher_task(bot))
    reputation = asyncio.create_task(reputation_refresher_task())
    # Оборачиваем критические задачи перезапуском
    telethon_task = asyncio.create_task(_run_with_restarts("telethon", start_telethon))
    aiogram_task = asyncio.create_task(_run_with_restarts("aiogram", start_aiogram))
    await asyncio.gather(telethon_task, aiogram_task, publisher, reputation)


# TODO: Надо растащить куски aiogram и telethon в два модуля оставив тут main
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
