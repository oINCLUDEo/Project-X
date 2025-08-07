import logging
from telethon import utils
from database.db_connection import get_channel_category, get_category_users, add_post, get_expired_clusters, get_main_post_for_cluster, delete_cluster
from AI.Ai_Functions import get_embedding
from AI.clustering import process_post_and_cluster
import asyncio
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram import types
from aiogram.enums import ParseMode

logger = logging.getLogger(__name__)


def get_media_type_by_path(path: str) -> str:
    if utils.is_video(path):
        return "video"
    elif utils.is_image(path):
        return "image"
    elif utils.is_gif(path):
        return "gif"
    else:
        return "unknown"

async def send_to_users(bot, users, send_func, *args, **kwargs):
    for user in users:
        try:
            await send_func(chat_id=user, *args, **kwargs)
            logger.info("Сообщение отправлено пользователю %s", user)
        except Exception as e:
            logger.error("Ошибка отправки сообщения пользователю %s: %s", user, str(e))

def validate_post(event, type):
    if type == "album":
        msg_from_channel_id = event.messages[0].peer_id.channel_id
    else:
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

def process_ai_and_clustering(msg_from_channel_id, message_text, media_urls=None):
    embedding = get_embedding(message_text)
    post_id = add_post(msg_from_channel_id, message_text, embedding.tolist(), media_urls)
    clustering_result = process_post_and_cluster(msg_from_channel_id, message_text, post_id)
    logger.info(f"Пост ID {post_id} обработан и кластеризован (Cluster ID: {clustering_result['cluster_id']}, Схожесть: {clustering_result['similarity']})")


# --- Универсальная публикация главного поста ---
async def publish_main_post(bot, users, post_row):
    content = post_row[2]
    media_urls = post_row[3] or []
    if isinstance(media_urls, str):
        import ast
        media_urls = ast.literal_eval(media_urls)
    if len(media_urls) > 1:
        # Альбом: фото и видео
        media_group = MediaGroupBuilder(caption=content)
        for url in media_urls:
            mtype = get_media_type_by_path(url)
            if mtype == 'video':
                media_group.add(type='video', media=types.FSInputFile(path=url), parse_mode=ParseMode.HTML)
            elif mtype == 'image':
                media_group.add(type='photo', media=types.FSInputFile(path=url), parse_mode=ParseMode.HTML)
        await send_to_users(bot, users, bot.send_media_group, media=media_group.build())
    elif len(media_urls) == 1:
        url = media_urls[0]
        mtype = get_media_type_by_path(url)
        if mtype == 'video':
            await send_to_users(
                bot, users, bot.send_video,
                video=types.FSInputFile(path=url),
                caption=content,
                parse_mode=ParseMode.HTML
            )
        elif mtype == 'image':
            await send_to_users(
                bot, users, bot.send_photo,
                photo=types.FSInputFile(path=url),
                caption=content,
                parse_mode=ParseMode.HTML
            )
        elif mtype == 'gif':
            await send_to_users(
                bot, users, bot.send_animation,
                animation=types.FSInputFile(path=url),
                caption=content,
                parse_mode=ParseMode.HTML
            )
        else:
            await send_to_users(
                bot, users, bot.send_message,
                text=content,
                parse_mode=ParseMode.HTML
            )
    else:
        # Только текст
        await send_to_users(
            bot, users, bot.send_message,
            text=content,
            parse_mode=ParseMode.HTML
        )

# --- Фоновый таск публикации главных новостей кластеров ---
async def cluster_publisher_task(bot, send_func, get_users_for_post, interval=30):
    """
    Периодически ищет истёкшие кластеры, отправляет главный пост пользователям и удаляет кластер.
    :param bot: объект бота
    :param send_func: функция отправки (например, bot.send_message)
    :param get_users_for_post: функция, возвращающая список пользователей для поста
    :param interval: интервал проверки в секундах
    """
    while True:
        expired_clusters = get_expired_clusters()
        for cluster_id, main_post_id in expired_clusters:
            main_post = get_main_post_for_cluster(cluster_id)
            if main_post:
                channel_tg_id = main_post[1]
                users = get_users_for_post(channel_tg_id)
                if users:
                    await publish_main_post(bot, users, main_post)
                    logger.info(f"Главная новость кластера {cluster_id} отправлена {len(users)} пользователям")
            delete_cluster(cluster_id)
            logger.info(f"Кластер {cluster_id} удалён после публикации")
        await asyncio.sleep(interval) 