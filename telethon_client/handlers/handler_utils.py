import logging
import asyncio
from telethon import utils
from database.db_connection import get_channel_category, get_category_users, add_post, get_expired_clusters, \
    get_main_post_for_cluster, get_active_clusters, get_posts_by_cluster, archive_cluster, get_posts_in_active_clusters, \
    update_post_status, get_cluster_id_by_post, update_cluster_status, \
    get_posts_by_cluster_with_reputation, log_cluster_score, get_system_param, recalc_channel_reputation
from AI.Ai_Functions import get_embedding
from AI.clustering import process_post_and_cluster
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram import types
from aiogram.enums import ParseMode

from helpers.ad_helper import compute_ad_score, process_post_for_ad_check
from AI.Ai_Functions import predict_ad_probability, get_embedding
from helpers.helpers import compute_cluster_score, get_users_for_post

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

def process_ai_and_clustering(msg_from_channel_id, message_text, media_urls=None, message_id=None):
    embedding = get_embedding(message_text).tolist()
    post_id = add_post(msg_from_channel_id, message_text, embedding, media_urls, message_id=message_id)
    clustering_result = process_post_and_cluster(msg_from_channel_id, embedding, post_id)
    logger.info(f"Пост ID {post_id} обработан и кластеризован (Cluster ID: {clustering_result['cluster_id']}, Схожесть: {clustering_result['similarity']})")
    # Немедленный запуск фильтра рекламы на свежем посте (опционально)
    try:
        process_post_for_ad_check({'post_id': post_id}, ad_threshold=0.4, model_pred_func=predict_ad_probability)
    except Exception as e:
        logger.error(f"Ad filter immediate check failed for post {post_id}: {e}")


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


async def engagement_publisher_task(bot, interval=30, min_score=0.5):
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
        for cluster_id, main_post_id in active_clusters:
            # A/B: baseline vs improved
            cluster_posts = get_posts_by_cluster(cluster_id)
            improved_posts = get_posts_by_cluster_with_reputation(cluster_id)
            if not cluster_posts:
                logger.info(f"Кластер {cluster_id} пустой, пропускаем")
                continue
            # Baseline score (без репутации)
            baseline_score = compute_cluster_score(cluster_posts, channel_reputation_weight=0.0, diversity_weight=0.2)
            # Improved score (с репутацией)
            improved_score = compute_cluster_score(improved_posts, channel_reputation_weight=0.3, diversity_weight=0.2)
            try:
                log_cluster_score(cluster_id, 'baseline', baseline_score)
                log_cluster_score(cluster_id, 'improved', improved_score)
            except Exception:
                pass
            logger.info(f"Кластер {cluster_id} baseline={baseline_score:.4f} improved={improved_score:.4f}")

            # Выбор алгоритма из системных параметров для A/B и динамический порог публикации
            algo = (get_system_param('cluster_scoring_algo', 'improved') or 'improved').lower()
            try:
                min_score_param = float(get_system_param('cluster_min_score', str(min_score)) or min_score)
            except Exception:
                min_score_param = min_score
            score_to_use = improved_score if algo == 'improved' else baseline_score
            if score_to_use >= min_score_param:
                main_post = get_main_post_for_cluster(cluster_id)
                if not main_post:
                    logger.warning(f"Главный пост {main_post_id} не найден в кластере {cluster_id}")
                    continue
                channel_tg_id = main_post[1]
                users = get_users_for_post(channel_tg_id)
                if not users:
                    logger.info(f"Нет пользователей для поста {main_post_id} канала {main_post['channel_tg_id']}")
                    continue
                await publish_main_post(bot, users, main_post)
                logger.info(f"Кластер {cluster_id} опубликован с score={score_to_use:.4f} (algo={algo}, min={min_score_param:.3f})")
                archive_cluster(cluster_id)
        await asyncio.sleep(interval)


async def ad_filter_task(interval=30, ad_threshold=0.4):
    while True:
        try:
            active_posts = get_posts_in_active_clusters()
            for post in active_posts:
                try:
                    dynamic_threshold = float(get_system_param('ad_threshold', str(ad_threshold)) or ad_threshold)
                except Exception:
                    dynamic_threshold = ad_threshold
                is_ad = process_post_for_ad_check(post, dynamic_threshold)
        except Exception as e:
            logger.error(f"Ошибка в ad_filter_task: {e}")
        await asyncio.sleep(interval)


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
