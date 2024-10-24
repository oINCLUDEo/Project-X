import logging


async def start_aiogram():
    logger = logging.getLogger(__name__)
    logger.info("Бот успешно запущен")

    await dp.start_polling(bot)
