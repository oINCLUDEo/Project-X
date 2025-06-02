import logging

from database.db_connection import add_user
from aiogram import Router, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart

# Инициализируем роутер уровня модуля
router = Router()
dp = Dispatcher()
logger = logging.getLogger(__name__) # Создание логгера под файл

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_tg_id : int = message.from_user.id
    logger.debug("Запрос на добавление пользователя - ", user_tg_id)
    add_user(user_tg_id)


@router.callback_query(lambda c: c.data.startswith(('like_', 'dislike_')))
async def process_like_dislike(callback_query: CallbackQuery):
    action, post_id = callback_query.data.split('_')  # Разделяем "like_123" → ("like", "123")
    user_id = callback_query.from_user.id
    if action == "like":
        # Логика для лайка (например, +1 в БД)
        await callback_query.answer("Спасибо за лайк! ❤️")
    elif action == "dislike":
        # Логика для дизлайка
        await callback_query.answer("Жаль, что не понравилось... 😢")