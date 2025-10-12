import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)


def _insert_native_ad(text: str, ad_snippet: str | None) -> str:
    if not ad_snippet:
        return text
    text = text.strip()
    if not text:
        return ad_snippet
    # Вставляем рекламу в конец текста через отступ одной строкой
    ad_clean = ad_snippet.strip()
    result = text + "\n\n" + ad_clean
    # Безопасное логирование рекламы (без эмодзи)
    safe_ad = ad_clean.encode('ascii', 'ignore').decode('ascii')
    logger.debug(f"[NATIVE_AD] Inserted ad: '{safe_ad}' -> result length: {len(result)}")
    return result


# TODO: Ни о какой уникальности нет речи, оно просто берет готовый пост и вставляет свою плашку.
#  Стоит улучшить работу fallback, либо снести задумку
def generate_unique_content(cluster_posts: List[Dict], native_ad: str | None = None) -> Tuple[str, Dict]:
    """
    Простой пайплайн уникализации:
    1) берем контент главного поста
    2) нативная вставка рекламы

    Возвращает итоговый текст и метаданные процесса
    """
    if not cluster_posts:
        return "", {"model": "empty"}

    # Берем контент первого поста (главного)
    main_post_content = cluster_posts[0].get('content', '') if cluster_posts else ''
    
    # Добавляем рекламу в конец
    final_text = _insert_native_ad(main_post_content, native_ad)

    meta = {
        "model": "main_post"
    }
    return final_text, meta
