import logging

from AI.Ai_Functions import get_embedding
from AI.clustering import process_post_and_cluster
from aiogram_bot.keyboards import get_feedback_keyboard
from database.db_connection import get_channel_category, get_category_users, add_post
from helpers.helpers import remove_file

from aiogram import types
from telethon import utils
from aiogram.enums import ParseMode
from aiogram.utils.media_group import MediaGroupBuilder

logger = logging.getLogger(__name__)

# --- Универсальная функция отправки ---
async def send_to_users(bot, users, send_func, *args, **kwargs):
    for user in users:
        try:
            await send_func(chat_id=user, *args, **kwargs)
            logger.info("Сообщение отправлено пользователю %s", user)
        except Exception as e:
            logger.error("Ошибка отправки сообщения пользователю %s: %s", user, str(e))

def validate_post(event):
    msg_from_channel_id = event.peer_id.channel_id
    channel_categories = get_channel_category(msg_from_channel_id)
    if not channel_categories:
        logger.warning("Канал %s не имеет категорий", msg_from_channel_id)
        return None, None, None
    target_users = get_category_users(tuple(channel_categories))
    if not target_users:
        logger.info("Нет пользователей для отправки сообщения")
        return None, None, None
    return msg_from_channel_id, channel_categories, target_users

async def download_and_identify_media(event):
    filename = await event.download_media()
    if utils.is_video(filename):
        media_type = 'video'
    elif utils.is_image(filename):
        media_type = 'image'
    elif utils.is_gif(filename):
        media_type = 'gif'
    else:
        media_type = 'unknown'
    return filename, media_type

def process_ai_and_clustering(msg_from_channel_id, message_text):
    embedding = get_embedding(message_text)
    post_id = add_post(msg_from_channel_id, message_text, embedding.tolist())
    clustering_result = process_post_and_cluster(msg_from_channel_id, message_text, post_id)
    logger.info(f"Пост ID {post_id} обработан и кластеризован (Cluster ID: {clustering_result['cluster_id']}, Схожесть: {clustering_result['similarity']})")

# --- Обработчики ---
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