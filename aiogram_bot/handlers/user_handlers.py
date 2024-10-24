import logging

from database.db_connection import add_user
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart

# Инициализируем роутер уровня модуля
router = Router()
logger = logging.getLogger(__name__) # Создание логгера под файл

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_tg_id : int = message.from_user.id
    logger.debug("Запрос на добавление пользователя - ", user_tg_id)
    add_user(user_tg_id)