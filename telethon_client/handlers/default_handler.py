import logging

from telethon_client.handlers.handler_utils import validate_post, process_ai_and_clustering
from config.config import load_config
import os

logger = logging.getLogger(__name__)

async def default_handler(event):
    if event.grouped_id:
        return
    logger.info("Получено новое сообщение")
    media_urls = []
    message_text = event.message.text or ""

    msg_from_channel_id, channel_categories, target_users = validate_post(event, "default message")
    if not target_users:
        return

    if event.media:
        cfg = load_config()
        media_dir = cfg.storage.media_dir
        os.makedirs(media_dir, exist_ok=True)
        filename = await event.download_media(file=media_dir)
        media_urls.append(filename)

    try:
        process_ai_and_clustering(msg_from_channel_id, message_text, media_urls, message_id=event.id)
    except Exception as e:
        logger.error(f"Ошибка при обработке AI/кластеризации: {str(e)}")