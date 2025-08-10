from telethon import events
import os
from config.config import load_config

from helpers.helpers import compute_heat_score
from telethon_client.handlers.album_handler import album_handler
from telethon_client.handlers.default_handler import default_handler
from database.db_connection import get_posts_in_active_clusters, update_post_engagement
import logging

logger = logging.getLogger(__name__)

async def update_engagement_for_active_cluster_posts(client, interval=30):
    """
    Обновляет engagement-показатели (views, reactions, comments, forwards, score) для всех постов в активных кластерах.
    Корректно обрабатывает альбомы (grouped_id) путём суммирования engagement по группе сообщений.
    """
    import asyncio
    while True:
        try:
            posts = get_posts_in_active_clusters()
            logger.info(f'[ENGAGEMENT] Активных постов в кластерах: {len(posts)}')

            for post in posts:
                channel_id = post['channel_tg_id']
                message_id = post['message_id']
                post_id = post['post_id']
                logger.info(
                    f'[ENGAGEMENT] Проверка поста: post_id={post_id}, channel_id={channel_id}, message_id={message_id}')
                try:
                    msg_raw = await client.get_messages(channel_id, ids=message_id)
                    msg = msg_raw[0] if isinstance(msg_raw, list) or hasattr(msg_raw, '__iter__') else msg_raw
                    if msg.grouped_id:
                        # Обрабатываем как альбом
                        logger.info(f'[ENGAGEMENT] Обнаружен grouped_id={msg.grouped_id}, ищем сообщения в альбоме...')
                        recent_msgs = await client.get_messages(channel_id, limit=20)
                        group = [m for m in recent_msgs if m.grouped_id == msg.grouped_id]
                        logger.info(f'[ENGAGEMENT] Найдено {len(group)} сообщений в альбоме.')
                    else:
                        group = [msg]
                        logger.info(f'[ENGAGEMENT] Одиночное сообщение.')

                    # Сбор статистики
                    total_views = sum(m.views or 0 for m in group)
                    total_forwards = sum(m.forwards or 0 for m in group)
                    total_comments = sum(m.replies.replies if m.replies else 0 for m in group)
                    total_reactions = sum(
                        sum(r.count for r in m.reactions.results) if m.reactions and m.reactions.results else 0
                        for m in group
                    )
                    score = compute_heat_score(
                        total_views, total_reactions, total_comments, total_forwards
                    )
                    update_post_engagement(post_id, total_views, total_reactions, total_comments, total_forwards, score)
                    logger.info(
                        f'[ENGAGEMENT] Обновлён post_id={post_id} | views={total_views}, reactions={total_reactions}, '
                        f'comments={total_comments}, forwards={total_forwards}, score={score:.4f}'
                    )
                except Exception as e:
                    logger.error(f'[ENGAGEMENT] Ошибка при обработке post_id={post_id}: {e}', exc_info=True)
        except Exception as e:
            logger.error(f'[ENGAGEMENT] Ошибка в основном цикле: {e}', exc_info=True)
        await asyncio.sleep(interval)

def setup_handlers(client, channels, bot):
    # Ensure media directory exists at startup
    cfg = load_config()
    os.makedirs(cfg.storage.media_dir, exist_ok=True)
    client.add_event_handler(lambda event: album_handler(event, bot), events.Album(chats=channels))
    client.add_event_handler(lambda event: default_handler(event, bot), events.NewMessage(chats=channels))
