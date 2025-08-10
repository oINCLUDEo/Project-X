import logging

from telethon_client.handlers.handler_utils import validate_post, process_ai_and_clustering

logger = logging.getLogger(__name__)

async def default_handler(event, bot):
    if event.grouped_id:
        return
    logger.info("Получено новое сообщение")
    filename = ""
    media_urls = []
    message_text = event.message.text

    msg_from_channel_id, channel_categories, target_users = validate_post(event, "default message")
    if not target_users:
        return

    if event.media:
        filename = await event.download_media()
        media_urls.append(filename)

    try:
        process_ai_and_clustering(msg_from_channel_id, message_text, media_urls, message_id=event.id)
    except Exception as e:
        logger.error(f"Ошибка при обработке AI/кластеризации: {str(e)}")