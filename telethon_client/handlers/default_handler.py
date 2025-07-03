import logging
from aiogram import types
from aiogram.enums import ParseMode
from helpers.helpers import remove_file
from aiogram_bot.keyboards import get_feedback_keyboard
from telethon_client.handlers.handler_utils import validate_post, download_and_identify_media, process_ai_and_clustering

logger = logging.getLogger(__name__)

async def default_handler(event, bot):
    logger.info("Получено новое сообщение")
    message_text = event.message.text

    msg_from_channel_id, channel_categories, target_users = validate_post(event)
    if not target_users:
        return

    if event.media:
        filename, media_type = await download_and_identify_media(event)
        try:
            # Здесь можно добавить сохранение информации о медиа в БД, если нужно
            pass  # Не отправляем пользователям!
        except Exception as e:
            logger.error("Ошибка обработки медиафайла: %s", str(e))
        finally:
            remove_file(filename)
    # else:  # Текстовые сообщения тоже не отправляем
    #     pass

    try:
        process_ai_and_clustering(msg_from_channel_id, message_text)
    except Exception as e:
        logger.error(f"Ошибка при обработке AI/кластеризации: {str(e)}") 