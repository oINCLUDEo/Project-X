import logging
import time
import asyncio
import datetime
import os
from datetime import timezone
from telethon import utils
import html as _html
from database.db_connection import get_channel_category, get_category_users, add_post, get_expired_clusters, \
    get_main_post_for_cluster, get_active_clusters, get_posts_by_cluster, archive_cluster, get_posts_in_active_clusters, \
    update_post_status, get_cluster_id_by_post, update_cluster_status, \
    get_posts_by_cluster_with_reputation, log_cluster_score, get_system_param, recalc_channel_reputation, \
    get_cluster_metadata, get_latest_cluster_scores, get_recent_clusters, get_cluster_posts_full
from AI.Ai_Functions import get_embedding
from AI.clustering import process_post_and_cluster
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram import types
from aiogram.enums import ParseMode
from aiogram_bot.keyboards import get_feedback_keyboard

from helpers.ad_helper import compute_ad_score, process_post_for_ad_check
from AI.Ai_Functions import predict_ad_probability, get_embedding
from helpers.helpers import compute_cluster_score, get_users_for_post
from AI.content_generator import generate_unique_content
from AI.news_synthesizer import synthesize_news

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
    """Отправляет сообщение всем пользователям. Возвращает True если все отправки успешны."""
    success_count = 0
    total_users = len(users)
    
    for user in users:
        try:
            await send_func(chat_id=user, *args, **kwargs)
            logger.info("Сообщение отправлено пользователю %s", user)
            success_count += 1
        except Exception as e:
            logger.error("Ошибка отправки сообщения пользователю %s: %s", user, str(e))
    
    # Возвращаем True только если отправлено всем пользователям
    return success_count == total_users

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

def process_ai_and_clustering(msg_from_channel_id, message_text, media_urls=None, message_id=None):
    safe_text = message_text or ""
    embedding = get_embedding(safe_text).tolist()
    post_id = add_post(msg_from_channel_id, safe_text, embedding, media_urls, message_id=message_id)
    clustering_result = process_post_and_cluster(msg_from_channel_id, embedding, post_id)
    logger.info(f"Пост ID {post_id} обработан и кластеризован (Cluster ID: {clustering_result['cluster_id']}, Схожесть: {clustering_result['similarity']})")
    # Немедленный запуск фильтра рекламы на свежем посте (опционально)
    try:
        process_post_for_ad_check({'post_id': post_id}, ad_threshold=0.4, model_pred_func=predict_ad_probability)
    except Exception as e:
        logger.error(f"Ad filter immediate check failed for post {post_id}: {e}")


# --- Универсальная публикация главного поста ---
def _sanitize_caption(text: str) -> str:
    """Простая очистка текста для безопасной отправки (убирает HTML-теги только в последней строке)."""
    if not text:
        return ""
    try:
        import re
        
        # Логируем исходный текст для диагностики
        logger.debug(f"[SANITIZE] Input text (first 200 chars): {text[:200].encode('ascii', 'ignore').decode('ascii')}...")
        
        # Разбиваем на строки
        lines = text.split('\n')
        
        if len(lines) > 1:
            # Фильтруем строки, убирая рекламные ссылки
            filtered_lines = []
            for line in lines:
                # Если строка содержит HTML-ссылку, пропускаем её
                if re.search(r'<a\s+href=', line):
                    continue
                # Если строка содержит только эмодзи и рекламные слова, пропускаем
                if re.match(r'^[^\w]*?(подписывайся|подписаться|присылай|новости|инсайд)[^\w]*$', line, re.IGNORECASE):
                    continue
                filtered_lines.append(line)
            
            # Собираем обратно
            text = '\n'.join(filtered_lines)
        else:
            # Если только одна строка, убираем HTML-теги везде
            text = re.sub(r'<[^>]*>', '', text)
            text = re.sub(r'&[a-zA-Z0-9#]+;', '', text)
        
        logger.debug(f"[SANITIZE] Output text (first 200 chars): {text[:200].encode('ascii', 'ignore').decode('ascii')}...")
        
        return text
    except Exception as e:
        logger.error(f"[SANITIZE] Error processing text: {e}", exc_info=True)
        return text


async def publish_main_post(bot, users, post_row):
    """Публикует главный пост. Возвращает True если отправка успешна всем пользователям."""
    # Сначала санитизируем основной контент
    content = _sanitize_caption(post_row[2])
    
    # Затем добавляем рекламу, если она есть
    try:
        native_ad = get_system_param('native_ad_snippet', None)
        if native_ad and native_ad.strip():
            content = content.strip() + "\n\n" + native_ad.strip()
            # Безопасное логирование рекламы (без эмодзи)
            safe_ad = native_ad.strip().encode('ascii', 'ignore').decode('ascii')
            logger.debug(f"[PUBLISH] Added native ad: '{safe_ad}'")
    except Exception as e:
        logger.warning(f"[PUBLISH] Failed to add native ad: {e}")

    # TODO: Странный участок кода нужна проверка
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
        # Aiogram ограничивает группу 2-10 элементами
        built = media_group.build()
        if len(built) > 10:
            built = built[:10]
        return await send_to_users(bot, users, bot.send_media_group, media=built)
    elif len(media_urls) == 1:
        url = media_urls[0]
        mtype = get_media_type_by_path(url)
        if mtype == 'video':
            return await send_to_users(
                bot, users, bot.send_video,
                video=types.FSInputFile(path=url),
                caption=content,
                parse_mode=ParseMode.HTML,
                reply_markup=get_feedback_keyboard(post_row[0])
            )
        elif mtype == 'image':
            return await send_to_users(
                bot, users, bot.send_photo,
                photo=types.FSInputFile(path=url),
                caption=content,
                parse_mode=ParseMode.HTML,
                reply_markup=get_feedback_keyboard(post_row[0])
            )
        elif mtype == 'gif':
            return await send_to_users(
                bot, users, bot.send_animation,
                animation=types.FSInputFile(path=url),
                caption=content,
                parse_mode=ParseMode.HTML,
                reply_markup=get_feedback_keyboard(post_row[0])
            )
        else:
            return await send_to_users(
                bot, users, bot.send_message,
                text=content,
                parse_mode=ParseMode.HTML,
                reply_markup=get_feedback_keyboard(post_row[0])
            )
    else:
        # Только текст
        return await send_to_users(
            bot, users, bot.send_message,
            text=content,
            parse_mode=ParseMode.HTML,
            reply_markup=get_feedback_keyboard(post_row[0])
        )


async def engagement_publisher_task(bot, interval=300, min_score=0.5):
    """
    Периодически проверяет engagement кластеров и публикует, если score >= min_score.

    :param bot: объект бота
    :param get_posts_by_cluster: функция, возвращающая список постов кластера по cluster_id
    :param get_users_for_post: функция, возвращающая список пользователей для поста
    :param interval: интервал проверки в секундах
    :param min_score: минимальное значение score для публикации
    """
    while True:
        active_clusters = get_active_clusters()  # [(cluster_id, main_post_id), ...]
        logger.info(f"[PUBLISH] Активных кластеров: {len(active_clusters)}; interval={interval}s, base_min_score={min_score}")
        for cluster_id, main_post_id in active_clusters:
            # A/B: baseline vs improved
            cluster_posts = get_posts_by_cluster(cluster_id)
            improved_posts = get_posts_by_cluster_with_reputation(cluster_id)
            if not cluster_posts:
                logger.info(f"Кластер {cluster_id} пустой, пропускаем")
                continue
            # Baseline score (без репутации)
            baseline_score = compute_cluster_score(cluster_posts, channel_reputation_weight=0.0)
            # Improved score (с репутацией)
            improved_score = compute_cluster_score(improved_posts, channel_reputation_weight=0.35)
            try:
                log_cluster_score(cluster_id, 'baseline', baseline_score)
                log_cluster_score(cluster_id, 'improved', improved_score)
            except Exception as e:
                logger.error(f"[PUBLISH] Ошибка логирования cluster_scores для cluster={cluster_id}: {e}")
            logger.info(f"[PUBLISH] Кластер {cluster_id}: posts={len(cluster_posts)}, posts_w_rep={len(improved_posts)}, baseline={baseline_score:.4f}, improved={improved_score:.4f}")

            # Выбор алгоритма из системных параметров для A/B
            algo = (get_system_param('cluster_scoring_algo', 'improved') or 'improved').lower()
            try:
                min_score_param = float(get_system_param('cluster_min_score', str(min_score)) or min_score)
            except Exception:
                min_score_param = min_score
            score_to_use = improved_score if algo == 'improved' else baseline_score
            # Ужесточаем базовый порог
            effective_threshold = max(0.65, min_score_param)
            logger.debug(f"[PUBLISH] Кластер {cluster_id}: algo={algo}, min_score_param={min_score_param}, effective_threshold={effective_threshold:.3f}")
            # Гибкая задержка публикации: учитываем относительность в сравнении с другими кластерами в окне времени
            try:
                min_age_minutes = int(get_system_param('cluster_min_age_minutes', '10') or '10')
            except Exception:
                min_age_minutes = 10
            try:
                min_posts_in_cluster = int(get_system_param('cluster_min_posts', '3') or '3')
            except Exception:
                min_posts_in_cluster = 3

            meta = get_cluster_metadata(cluster_id) or {}
            meets_age = False
            try:
                created_at = meta.get('created_at')
                if created_at:
                    age_minutes = (datetime.datetime.now() - created_at).total_seconds() / 60.0
                    meets_age = age_minutes >= min_age_minutes
                    logger.debug(f"[PUBLISH] Кластер {cluster_id}: age_minutes={age_minutes:.1f}, min_age={min_age_minutes}")
            except Exception:
                meets_age = False
            meets_volume = (meta.get('post_count') or 0) >= min_posts_in_cluster
            logger.debug(f"[PUBLISH] Кластер {cluster_id}: created_at={meta.get('created_at')}, age_ok={meets_age} (min_age={min_age_minutes}m), volume_ok={meets_volume} (count={meta.get('post_count')}, min={min_posts_in_cluster})")

            # Дополнительно: динамический «перцентильный» фильтр по скору в окне времени
            # Публикуем только кластеры из топ-квантили (например, 70-й перцентиль) текущего окна
            try:
                percentile_str = get_system_param('cluster_min_percentile', '0.7') or '0.7'
                min_percentile = max(0.5, min(0.95, float(percentile_str)))
            except Exception:
                min_percentile = 0.7
            try:
                window_minutes = int(get_system_param('cluster_percentile_window_minutes', '120') or '120')
            except Exception:
                window_minutes = 120
            # Получаем свежие скоринги по выбранному алгоритму
            recent_scores = get_latest_cluster_scores(algo, window_minutes)
            if recent_scores:
                sorted_scores = sorted(recent_scores.values())
                idx = int(max(0, min(len(sorted_scores)-1, round(min_percentile * (len(sorted_scores)-1)))))
                percentile_cutoff = sorted_scores[idx]
            else:
                percentile_cutoff = effective_threshold
            dynamic_cutoff = max(effective_threshold, percentile_cutoff)
            logger.info(f"[PUBLISH] Кластер {cluster_id}: window={window_minutes}m, percentile={min_percentile:.2f}, cutoff={dynamic_cutoff:.3f}, score={score_to_use:.4f}")

            # Опциональный обход возрастного порога при очень высоком score (включается системным параметром)
            try:
                bypass_margin = float(get_system_param('cluster_age_bypass_margin', '0') or '0')
            except Exception:
                bypass_margin = 0.0
            bypass_age = (bypass_margin > 0) and (score_to_use >= (dynamic_cutoff + bypass_margin)) and meets_volume

            if (score_to_use >= dynamic_cutoff and meets_age and meets_volume) or bypass_age:
                main_post = get_main_post_for_cluster(cluster_id)
                if not main_post:
                    logger.warning(f"Главный пост {main_post_id} не найден в кластере {cluster_id}")
                    continue
                channel_tg_id = main_post[1]
                users = get_users_for_post(channel_tg_id)
                if not users:
                    logger.info(f"Нет пользователей для поста {main_post_id} канала {channel_tg_id}")
                    continue
                # Генерация уникального/синтезированного контента на основе всего кластера (включается системным параметром)
                try:
                    gen_enabled_raw = (get_system_param('content_generation_enabled', '1') or '1').lower()
                    gen_enabled = gen_enabled_raw in ('1', 'true', 'yes', 'on')
                except Exception:
                    gen_enabled = True
                if gen_enabled:
                    try:
                        t0 = time.perf_counter()
                        full_posts = get_cluster_posts_full(cluster_id)
                        logger.info(f"[CONTENT] Начало генерации: cluster={cluster_id}, posts={len(full_posts)}")
                        # Выбор режима синтеза: 'A' (anchor+details) | 'B' (facts->write)
                        mode = (get_system_param('content_generation_mode', 'A') or 'A').upper()
                        if mode in ('A', 'B'):
                            logger.info(f"[CONTENT] Используем генератор")
                            # Определяем наличие медиа в главном посте
                            main_post_media_urls = main_post[3] or []
                            if isinstance(main_post_media_urls, str):
                                import ast
                                main_post_media_urls = ast.literal_eval(main_post_media_urls)
                            has_media = len(main_post_media_urls) > 0
                            
                            unique_text, meta = synthesize_news(full_posts, mode=mode, has_media=has_media)
                            try:
                                logger.info(
                                    f"[CONTENT] meta: model={meta.get('model')} prompt_len={meta.get('prompt_len')} posts={meta.get('posts')} has_media={meta.get('has_media')}"
                                )
                            except Exception:
                                pass
                        else:
                            logger.info(f"[CONTENT] Используем простой старый генератор")
                            # Фолбэк: прежний простой генератор
                            unique_text, meta = generate_unique_content(full_posts, method='auto')
                        dt = (time.perf_counter() - t0) * 1000
                        logger.info(f"[CONTENT] Генерация завершена: cluster={cluster_id}, mode={mode}, ms={dt:.0f}, length={len(unique_text or '')}")
                        if unique_text and unique_text.strip():
                            # Подменяем контент главного поста
                            as_list = list(main_post)
                            as_list[2] = unique_text
                            main_post = tuple(as_list)
                    except Exception as e:
                        logger.error(f"[CONTENT] Ошибка генерации уникального контента для кластера {cluster_id}: {e}", exc_info=True)
                else:
                    logger.info(f"[CONTENT] Генерация уникального контента отключена системным параметром для cluster={cluster_id}")
                # Атомарная отправка: архивируем только при успешной отправке всем пользователям
                publish_success = await publish_main_post(bot, users, main_post)
                if publish_success:
                    if bypass_age:
                        logger.info(f"Кластер {cluster_id} опубликован (bypass age) score={score_to_use:.4f} (algo={algo}, cutoff={dynamic_cutoff:.3f}, bypass_margin={bypass_margin:.3f}, posts>={min_posts_in_cluster})")
                    else:
                        logger.info(f"Кластер {cluster_id} опубликован score={score_to_use:.4f} (algo={algo}, cutoff={dynamic_cutoff:.3f}, age>={min_age_minutes}m, posts>={min_posts_in_cluster})")
                    archive_cluster(cluster_id)
                else:
                    logger.error(f"Кластер {cluster_id} НЕ опубликован из-за ошибок отправки - статус не изменён")
            else:
                reasons = []
                if score_to_use < dynamic_cutoff:
                    reasons.append(f"score {score_to_use:.3f} < cutoff {dynamic_cutoff:.3f}")
                if not meets_age:
                    reasons.append(f"age<min ({min_age_minutes}m)")
                if not meets_volume:
                    reasons.append(f"posts<count_min ({min_posts_in_cluster})")
                logger.info(f"[PUBLISH] Кластер {cluster_id} не опубликован: {', '.join(reasons)}")
        await asyncio.sleep(interval)


# Удалён периодический ad_filter_task: проверка рекламы выполняется только при получении поста


async def reputation_refresher_task(interval_seconds: int = 21600):
    """
    Периодически пересчитывает репутацию каналов, встречающихся в активных кластерах.
    По умолчанию каждые 6 часов.
    """
    while True:
        try:
            posts = get_posts_in_active_clusters()
            channel_ids = sorted({p['channel_tg_id'] for p in posts})
            for ch_id in channel_ids:
                try:
                    recalc_channel_reputation(ch_id)
                except Exception as e:
                    logger.error(f"Ошибка пересчёта репутации канала {ch_id}: {e}")
        except Exception as e:
            logger.error(f"Ошибка в reputation_refresher_task: {e}")
        await asyncio.sleep(interval_seconds)
