import logging

from database.db_connection import add_user, insert_ad_label, record_user_feedback
from aiogram import Router, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command

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
    try:
        post_id_int = int(post_id)
    except ValueError:
        await callback_query.answer("Некорректный ID поста", show_alert=True)
        return
    try:
        if action in ("like", "dislike"):
            record_user_feedback(user_id, post_id_int, action)
            if action == "like":
                await callback_query.answer("Спасибо за лайк! ❤️")
            else:
                await callback_query.answer("Учтём ваш дизлайк", show_alert=False)
        else:
            await callback_query.answer("Неизвестное действие", show_alert=True)
    except Exception as e:
        logger.error("Ошибка сохранения фидбека: %s", str(e))
        await callback_query.answer("Ошибка, попробуйте позже", show_alert=True)


@router.message(Command("label"))
async def cmd_label(message: Message):
    """
    Ручная разметка постов как реклама/не реклама.
    Использование: /label <post_id> <ad|not_ad|ambiguous> [notes]
    """
    try:
        parts = (message.text or "").split(maxsplit=3)
        if len(parts) < 3:
            await message.reply("Использование: /label <post_id> <ad|not_ad|ambiguous> [notes]")
            return
        _, post_id_str, label = parts[:3]
        notes = parts[3] if len(parts) > 3 else None
        post_id = int(post_id_str)
        if label not in ("ad", "not_ad", "ambiguous"):
            await message.reply("label должен быть ad|not_ad|ambiguous")
            return
        insert_ad_label(post_id, label, reviewer_tg_id=message.from_user.id, notes=notes, source='admin')
        await message.reply(f"OK: пост {post_id} размечен как {label}")
    except Exception as e:
        logger.error("Ошибка ручной разметки: %s", str(e))
        await message.reply("Ошибка обработки команды")