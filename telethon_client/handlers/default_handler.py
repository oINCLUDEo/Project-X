import logging
from aiogram import types
from aiogram.enums import ParseMode
from helpers.helpers import remove_file
from aiogram_bot.keyboards import get_feedback_keyboard
from handler_utils import send_to_users, validate_post, download_and_identify_media, process_ai_and_clustering

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
            if media_type == 'video':
                await send_to_users(
                    bot, target_users, bot.send_video,
                    video=types.FSInputFile(path=filename),
                    caption=f'{event.text}',
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_feedback_keyboard(event.id)
                )
            elif media_type == 'image':
                await send_to_users(
                    bot, target_users, bot.send_photo,
                    photo=types.FSInputFile(path=filename),
                    caption=f'{event.text}',
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_feedback_keyboard(event.id)
                )
            elif media_type == 'gif':
                await send_to_users(
                    bot, target_users, bot.send_animation,
                    animation=types.FSInputFile(path=filename),
                    caption=f'{event.text}',
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_feedback_keyboard(event.id)
                )
            else:
                logger.warning(f"Неизвестный тип медиа: {filename}")
        except Exception as e:
            logger.error("Ошибка отправки медиафайла: %s", str(e))
        finally:
            remove_file(filename)
    else:
        await send_to_users(
            bot, target_users, bot.send_message,
            text=f'{event.text}',
            parse_mode=ParseMode.HTML,
            reply_markup=get_feedback_keyboard(event.id)
        )

    try:
        process_ai_and_clustering(msg_from_channel_id, message_text)
    except Exception as e:
        logger.error(f"Ошибка при обработке AI/кластеризации: {str(e)}") 