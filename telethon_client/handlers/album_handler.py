import logging

from telethon_client.handlers.handler_utils import validate_post, process_ai_and_clustering

logger = logging.getLogger(__name__)

async def album_handler(event, bot):
    logger.info("Получен альбом из канала")
    media_urls = []
    message_text = event.text or ""

    msg_from_channel_id, channel_categories, target_users = validate_post(event, "album")
    if not target_users:
        return

    for file in event.messages:
        filename = await file.download_media()
        media_urls.append(filename)

    try:
        process_ai_and_clustering(msg_from_channel_id, message_text, media_urls)
        pass
    except Exception as e:
        logger.error("Ошибка обработки альбома: %s", str(e))