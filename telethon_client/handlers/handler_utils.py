import logging
from telethon import utils
from database.db_connection import get_channel_category, get_category_users, add_post, get_expired_clusters, get_main_post_for_cluster, delete_cluster
from AI.Ai_Functions import get_embedding
from AI.clustering import process_post_and_cluster
import asyncio

logger = logging.getLogger(__name__)

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
                # main_post: (post_id, channel_tg_id, content, embedding, media_urls, published_at, created_at, is_hot, views_count)
                channel_tg_id = main_post[1]
                content = main_post[2]
                # Получаем пользователей для рассылки (можно доработать под ваши нужды)
                users = get_users_for_post(channel_tg_id)
                if users:
                    await send_to_users(bot, users, send_func, text=content)
                    logger.info(f"Главная новость кластера {cluster_id} отправлена {len(users)} пользователям")
            delete_cluster(cluster_id)
            logger.info(f"Кластер {cluster_id} удалён после публикации")
        await asyncio.sleep(interval) 