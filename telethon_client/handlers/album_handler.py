import logging

from telethon_client.handlers.handler_utils import validate_post, process_ai_and_clustering
from config.config import load_config
import os

logger = logging.getLogger(__name__)

async def album_handler(event, bot):
    logger.info("Получен альбом из канала")
    media_urls = []
    message_text = event.text or ""

    msg_from_channel_id, channel_categories, target_users = validate_post(event, "album")
    if not target_users:
        return

    cfg = load_config()
    media_dir = cfg.storage.media_dir
    os.makedirs(media_dir, exist_ok=True)

    captions = []
    for file in event.messages:
        filename = await file.download_media(file=media_dir)
        media_urls.append(filename)
        if len(media_urls) >= 10:
            break
        # Собираем подписи к элементам альбома
        try:
            cap = (getattr(file, 'message', None) or getattr(file, 'text', None) or "").strip()
            if cap:
                captions.append(cap)
        except Exception:
            pass

    # Если общий текст альбома пустой, используем объединённые подписи элементов
    if not message_text:
        if captions:
            # Удалим дубликаты, сохраняя порядок
            seen = set()
            unique_caps = []
            for c in captions:
                if c not in seen:
                    seen.add(c)
                    unique_caps.append(c)
            message_text = "\n".join(unique_caps)
        else:
            # Фолбэк: краткое описание альбома
            message_text = f"Альбом: {len(media_urls)} файл(ов)"

    try:
        process_ai_and_clustering(msg_from_channel_id, message_text, media_urls)
        pass
    except Exception as e:
        logger.error("Ошибка обработки альбома: %s", str(e))