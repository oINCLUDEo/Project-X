import logging
from aiogram import types
from aiogram.enums import ParseMode
from aiogram.utils.media_group import MediaGroupBuilder
from telethon import utils
from helpers.helpers import remove_file
from aiogram_bot.keyboards import get_feedback_keyboard
from handler_utils import send_to_users, validate_post

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
        await send_to_users(
            bot, target_users, bot.send_media_group,
            media=media_group.build()
        )
    except Exception as e:
        logger.error("Ошибка отправки альбома: %s", str(e))
    finally:
        remove_file(filename_list) 