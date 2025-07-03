import logging
from aiogram import types
from aiogram.enums import ParseMode
from aiogram.utils.media_group import MediaGroupBuilder
from telethon import utils
from helpers.helpers import remove_file
from aiogram_bot.keyboards import get_feedback_keyboard
from telethon_client.handlers.handler_utils import validate_post

logger = logging.getLogger(__name__)

async def album_handler(event, bot):
    logger.info("Получен альбом из канала")
    filename_list = []
    media_group = MediaGroupBuilder(caption=f'{event.text}')

    msg_from_channel_id, channel_categories, target_users = validate_post(event)
    if not target_users:
        return

    for file in event.messages:
        filename = await file.download_media()
        filename_list.append(filename)
        if utils.is_video(filename):
            media_group.add(type='video',
                            media=types.FSInputFile(path=filename),
                            parse_mode=ParseMode.HTML)
        elif utils.is_image(filename):
            media_group.add(type='photo',
                            media=types.FSInputFile(path=filename),
                            parse_mode=ParseMode.HTML)
    try:
        # Здесь можно добавить сохранение информации о медиа-альбоме в БД, если нужно
        pass  # Не отправляем пользователям!
    except Exception as e:
        logger.error("Ошибка обработки альбома: %s", str(e))
    finally:
        remove_file(filename_list) 