import psycopg2
from psycopg2.extras import Json
import logging
from config.config import load_config
import time
from typing import Dict, Tuple, List

__all__ = ['get_channels', 'get_category_users', 'get_channel_category', 'add_user', 'add_channel', 'update_channel_info',
           'add_post', 'create_new_cluster', 'add_post_to_cluster', 'get_recent_clusters_with_embeddings',
           'get_expired_clusters', 'get_main_post_for_cluster', 'delete_cluster',
           'get_posts_in_active_clusters', 'update_post_engagement', 'get_posts_by_cluster', 'archive_cluster',
           'update_post_status', 'update_cluster_status', 'get_cluster_id_by_post',
           'get_engagement_score_score_by_post_id', 'get_post_content_by_id',
           'insert_ad_decision', 'insert_ad_label', 'get_ad_label_for_post', 'increment_pattern_cache',
           'get_top_patterns', 'get_recent_ad_decisions', 'upsert_model_version',
           'get_system_param', 'set_system_param', 'log_cluster_score',
           'get_channel_tg_id_for_post', 'recalc_channel_reputation', 'get_post_prev_metrics',
           'get_channel_reputation', 'get_channel_reputation_by_post_id', 'get_cluster_metadata',
           'get_posts_by_cluster_with_reputation', 'get_recent_clusters', 'get_latest_cluster_scores', 'find_nearest_active_cluster',
           'record_user_feedback', 'get_cluster_posts_full',
           'put_generated_article', 'get_generated_article_cluster_id_by_text_prefix',
           'get_generated_articles_by_date', 'get_active_clusters', 'user_exists', 'get_user_id',
           'get_user_categories', 'get_user_stats', 'update_user_bio', 'get_expired_active_clusters',
           'transition_cluster_to_cooling', 'get_expired_cooling_clusters', 'get_cooling_clusters',
           'archive_cooling_cluster', 'get_active_and_cooling_clusters',
           # Новые функции для системы рекомендаций
           'get_user_category_weights', 'update_user_category_weight', 'get_cluster_categories',
           'get_cluster_channels', 'get_cluster_embedding', 'get_user_preferred_embedding',
           'update_user_preferred_embedding', 'get_user_channel_preferences', 'get_user_activity_stats',
           'update_user_activity_stats', 'get_cluster_created_at', 'get_user_liked_clusters',
           'add_to_user_queue', 'get_user_queue', 'mark_queue_item_sent', 'get_user_post_count_today',
           'get_user_post_count_hour', 'increment_user_post_counter', 'get_active_users', 'get_user_tg_id',
           'get_generated_article_by_cluster_id']
logger = logging.getLogger(__name__)
config = load_config()

_SYS_PARAMS_CACHE: Dict[str, Tuple[str, float]] = {}
_SYS_PARAMS_TTL_SECONDS = 90.0

def _get_db_connection():
    """
    Возвращает подключение к базе данных.
    """
    return psycopg2.connect(
        dbname=config.db.db_name,
        user=config.db.db_user,
        password=config.db.db_password,
        host=config.db.db_host,
        port=config.db.db_port
    )

def _get_users():
    query = "SELECT user_tg_id FROM users;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            users = [user[0] for user in cur.fetchall()]

            logger.info("Возвращен список пользователей")
            return users

def get_channels():
    query = "SELECT channel_tg_id FROM channels;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            channels = [channel[0] for channel in cur.fetchall()]

            logger.info("Возвращен список каналов")
            return channels

def get_category_users(category_ids):
    """
    Получает список пользователей, подписанных на указанные категории.
    
    Args:
        category_ids: Кортеж ID категорий
        
    Returns:
        list[int]: Список Telegram ID пользователей
    """
    if not category_ids:
        logger.warning("Передан пустой список категорий")
        return []
    
    # Преобразуем в список, если передан кортеж
    category_ids = list(category_ids)

    query = """
            SELECT DISTINCT u.user_tg_id 
            FROM users u 
            JOIN user_categories uc ON u.user_id = uc.user_id 
            WHERE uc.category_id = ANY(%s)
            AND u.status = 'active';
            """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                # Передаем список как массив
                cur.execute(query, (category_ids,))
                users = [user[0] for user in cur.fetchall()]
                logger.info("Найдено %d пользователей для категорий %s", len(users), category_ids)
                return users
    except Exception as e:
        logger.error("Ошибка при получении пользователей для категорий %s: %s", category_ids, str(e))
        return []

def get_channel_category(channel_tg_id: int) -> list[int]:
    """
    Получает список категорий канала.
    
    Args:
        channel_tg_id: Telegram ID канала
        
    Returns:
        list[int]: Список ID категорий
    """
    query = """
            SELECT category_id FROM channel_categories cc
            JOIN channels c ON c.channel_id = cc.channel_id
            WHERE c.channel_tg_id = %s;
            """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (channel_tg_id,))
            categories = [category[0] for category in cur.fetchall()]
            logger.info("Получены категории %s для канала %s", categories, channel_tg_id)
            return categories

def add_user(user_tg_id, username, first_name, full_name, bio=None):
    query = "INSERT INTO users(user_tg_id, username, first_name, full_name, bio) VALUES (%s, %s, %s, %s, %s);"
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_tg_id, username, first_name, full_name, bio))

        logger.info("[DB] Пользователь успешно добавлен!")
    except psycopg2.IntegrityError:
        logger.exception("[DB] Ошибка уникальности:")


def get_user_id(user_tg_id: int) -> int:
    """Возвращает user_id по Telegram ID или None если пользователь не найден."""
    query = "SELECT user_id FROM users WHERE user_tg_id = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (user_tg_id,))
            row = cur.fetchone()
            return row[0] if row else None


def get_user_tg_id(user_id: int) -> int:
    """Возвращает user_tg_id по user_id или None если пользователь не найден."""
    query = "SELECT user_tg_id FROM users WHERE user_id = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (user_id,))
            row = cur.fetchone()
            return row[0] if row else None


def user_exists(user_tg_id: int) -> bool:
    """Проверяет существует ли пользователь."""
    query = "SELECT user_id FROM users WHERE user_tg_id = %s LIMIT 1;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (user_tg_id,))
            return cur.fetchone() is not None


def record_user_feedback(user_tg_id: int, post_id: int, action: str) -> None:
    """
    Сохраняет лайк/дизлайк пользователя для поста.
    action: 'like' | 'dislike'
    - like: is_liked=True, is_hidden=False
    - dislike: is_liked=False, is_hidden=True
    """
    user_id = get_user_id(user_tg_id)
    is_liked = True if action == 'like' else False
    is_hidden = False if action == 'like' else True
    upsert_q = """
        INSERT INTO user_posts(user_id, post_id, is_read, is_liked, is_hidden, read_at)
        VALUES (%s, %s, TRUE, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, post_id) DO UPDATE SET
            is_read = EXCLUDED.is_read,
            is_liked = EXCLUDED.is_liked,
            is_hidden = EXCLUDED.is_hidden,
            read_at = EXCLUDED.read_at
    """
    touch_user_q = "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(upsert_q, (user_id, post_id, is_liked, is_hidden))
            cur.execute(touch_user_q, (user_id,))
            conn.commit()


def add_channel(channel_tg_id: int, username: str, title: str, description: str = None,
                subscribers_count: int = 0, category_name: str = None) -> int:
    """
    Добавляет новый канал в базу данных и связывает его с категорией.

    Args:
        channel_tg_id: Telegram ID канала
        username: Username канала
        title: Название канала
        description: Описание канала (опционально)
        subscribers_count: Количество подписчиков
        category_name: Название категории для канала (опционально)

    Returns:
        int: ID добавленного канала

    Raises:
        psycopg2.IntegrityError: Если канал с таким channel_tg_id уже существует
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                # Начинаем транзакцию
                conn.autocommit = False

                try:
                    # Добавляем канал
                    channel_query = """
                        INSERT INTO channels 
                        (channel_tg_id, username, title, description, subscribers_count)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING channel_id;
                    """
                    cur.execute(channel_query, (
                        channel_tg_id,
                        username,
                        title,
                        description,
                        subscribers_count
                    ))
                    channel_id = cur.fetchone()[0]

                    # Если указана категория, связываем канал с ней
                    if category_name:
                        # Получаем ID категории
                        category_query = "SELECT category_id FROM categories WHERE name = %s;"
                        cur.execute(category_query, (category_name,))
                        category_result = cur.fetchone()

                        if category_result:
                            category_id = category_result[0]
                            # Связываем канал с категорией
                            link_query = """
                                INSERT INTO channel_categories (channel_id, category_id)
                                VALUES (%s, %s)
                                ON CONFLICT (channel_id, category_id) DO NOTHING;
                            """
                            cur.execute(link_query, (channel_id, category_id))

                    # Подтверждаем транзакцию
                    conn.commit()
                    logger.info(f"Канал {username} успешно добавлен с ID {channel_id}")
                    return channel_id

                except Exception as e:
                    # В случае ошибки откатываем транзакцию
                    conn.rollback()
                    raise e

    except psycopg2.IntegrityError:
        logger.error(f"Канал с ID {channel_tg_id} уже существует")
        raise
    except Exception as e:
        logger.error(f"Ошибка при добавлении канала {username}: {str(e)}")
        raise


def update_channel_info(channel_tg_id: int, username: str = None, title: str = None,
                        description: str = None, subscribers_count: int = None) -> bool:
    """
    Обновляет информацию о существующем канале.

    Args:
        channel_tg_id: Telegram ID канала
        username: Новый username канала (опционально)
        title: Новое название канала (опционально)
        description: Новое описание канала (опционально)
        subscribers_count: Новое количество подписчиков (опционально)

    Returns:
        bool: True если обновление прошло успешно, False если канал не найден
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                # Формируем SET часть запроса только для непустых параметров
                update_parts = []
                params = []

                if username is not None:
                    update_parts.append("username = %s")
                    params.append(username)
                if title is not None:
                    update_parts.append("title = %s")
                    params.append(title)
                if description is not None:
                    update_parts.append("description = %s")
                    params.append(description)
                if subscribers_count is not None:
                    update_parts.append("subscribers_count = %s")
                    params.append(subscribers_count)

                if not update_parts:
                    logger.warning("Нет параметров для обновления канала")
                    return False

                update_parts.append("last_updated = CURRENT_TIMESTAMP")

                query = f"""
                    UPDATE channels 
                    SET {', '.join(update_parts)}
                    WHERE channel_tg_id = %s
                    RETURNING channel_id;
                """
                params.append(channel_tg_id)

                cur.execute(query, params)
                result = cur.fetchone()

                if result:
                    logger.info(f"Информация о канале {channel_tg_id} успешно обновлена")
                    return True
                else:
                    logger.warning(f"Канал с ID {channel_tg_id} не найден")
                    return False

    except Exception as e:
        logger.error(f"Ошибка при обновлении информации о канале {channel_tg_id}: {str(e)}")
        raise


def add_post(channel_tg_id: int, content: str, media_urls: list[str], embedding_vec: list[float], message_id: int = None):
    """
    Добавляет новость с эмбеддингом в базу данных, включая message_id.
    """
    query = """
        INSERT INTO posts (channel_tg_id, content, media_urls, message_id, embedding_vec)
        VALUES (%s, %s, %s, %s, %s::vector)
        RETURNING post_id;
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                # Нормализуем пустой текст, чтобы не сохранять NULL
                norm_content = content if (content is not None and content != "") else ""
                cur.execute(query, (
                    channel_tg_id,
                    norm_content,
                    media_urls,
                    message_id,
                    embedding_vec
                ))
                post_id = cur.fetchone()[0]
                logger.info(f"Новость успешно добавлена с ID {post_id}")
                return post_id
    except Exception as e:
        logger.error(f"Ошибка при добавлении новости: {str(e)}")
        raise


def create_new_cluster(main_post_id: int, lifetime_minutes=360) -> int:
    query = """
            WITH new_cluster AS (
                INSERT INTO clusters (main_post_id, lifetime_minutes)
                VALUES (%s, %s)
                RETURNING cluster_id
            )
            INSERT INTO cluster_posts (cluster_id, post_id)
            SELECT cluster_id, %s FROM new_cluster
            RETURNING cluster_id;
        """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (main_post_id, lifetime_minutes, main_post_id))
            return cur.fetchone()[0]

def add_post_to_cluster(cluster_id: int, post_id: int):
    query = """
        INSERT INTO cluster_posts (cluster_id, post_id)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (cluster_id, post_id))


def get_recent_clusters_with_embeddings(limit: int | None = None) -> list[tuple[int, list[float]]]:
    """
    Возвращает пары (cluster_id, embedding главного поста).
    Если limit указан (int) — ограничивает количество, иначе возвращает все кластеры.
    """
    base_query = (
        "SELECT c.cluster_id, p.embedding_vec "
        "FROM clusters c "
        "JOIN posts p ON c.main_post_id = p.post_id "
        "ORDER BY c.created_at DESC"
    )
    if limit is not None:
        query = base_query + " LIMIT %s;"
        params = (limit,)
    else:
        query = base_query + ";"
        params = ()
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return [(row[0], row[1]) for row in cur.fetchall()]

def find_nearest_active_cluster(embedding: list[float], time_window_minutes: int = 720, max_distance: float = 0.35) -> tuple[int | None, float]:
    """
    Ищет ближайший активный или охлаждающийся кластер по косинусной дистанции через HNSW/pgvector.
    Возвращает пару (cluster_id, similarity) или (None, 0.0), если не найдено приемлемого соответствия.
    """
    query = """
        SELECT c.cluster_id,
               1 - (p.embedding_vec <=> %s::vector) AS similarity
        FROM clusters c
        JOIN posts p ON p.post_id = c.main_post_id
        WHERE c.status IN ('active', 'cooling')
          AND c.created_at > NOW() - (INTERVAL '1 minute' * %s)
        ORDER BY p.embedding_vec <=> %s::vector
        LIMIT 1;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (embedding, time_window_minutes, embedding))
            row = cur.fetchone()
            if not row:
                return None, 0.0
            cluster_id, similarity = row[0], float(row[1])
            # Конверсия max_distance (в косинусной метрике <=>) в similarity: similarity = 1 - distance
            if (1.0 - similarity) <= max_distance:
                return cluster_id, similarity
            return None, similarity

def get_expired_clusters():
    """
    Возвращает список кластеров, у которых истёк срок жизни (expires_at < now()).
    """
    query = """
        SELECT cluster_id, main_post_id FROM clusters
        WHERE expires_at < NOW()
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()  # [(cluster_id, main_post_id), ...]

def get_expired_active_clusters():
    """
    Возвращает список активных кластеров, у которых истёк срок жизни.
    Эти кластеры должны быть архивированы (не были опубликованы).
    """
    query = """
        SELECT cluster_id, main_post_id FROM clusters
        WHERE expires_at < NOW() AND status = 'active'
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()  # [(cluster_id, main_post_id), ...]

def get_cooling_clusters():
    """
    Возвращает список кластеров в статусе 'cooling'.
    """
    query = """
        SELECT cluster_id, main_post_id FROM clusters
        WHERE status = 'cooling'
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()  # [(cluster_id, main_post_id), ...]

def get_expired_cooling_clusters():
    """
    Возвращает список кластеров в статусе 'cooling', у которых истёк срок охлаждения.
    Эти кластеры должны быть переведены в статус 'archived'.
    """
    query = """
        SELECT cluster_id, main_post_id FROM clusters
        WHERE cooling_expires_at < NOW() AND status = 'cooling'
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()  # [(cluster_id, main_post_id), ...]

def transition_cluster_to_cooling(cluster_id: int, cooling_days: int = 3):
    """
    Переводит активный кластер в статус 'cooling' и устанавливает время истечения охлаждения.
    
    Args:
        cluster_id: ID кластера
        cooling_days: Количество дней для охлаждения (по умолчанию 3 дня)
    """
    query = """
        UPDATE clusters 
        SET status = 'cooling', 
            cooling_expires_at = NOW() + (INTERVAL '1 day' * %s)
        WHERE cluster_id = %s
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (cooling_days, cluster_id))
            conn.commit()
            logger.info(f"Кластер {cluster_id} переведён в статус 'cooling' на {cooling_days} дней")

def get_active_clusters():
    """
    Возвращает список активных кластеров (expires_at > NOW() AND status = 'active').
    Для publishing task нужны только по-настоящему активные кластеры, не охлаждающиеся.
    """
    query = """
        SELECT cluster_id, main_post_id FROM clusters
        WHERE expires_at > NOW() AND status = 'active'
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()  # [(cluster_id, main_post_id), ...]

def get_active_and_cooling_clusters():
    """
    Возвращает список активных и охлаждающихся кластеров.
    Используется для metrics/analytics.
    """
    query = """
        SELECT cluster_id, main_post_id FROM clusters
        WHERE status IN ('active', 'cooling')
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()  # [(cluster_id, main_post_id), ...]

def get_main_post_for_cluster(cluster_id):
    """
    Возвращает данные главного поста для кластера.
    """
    query = """
        SELECT p.* FROM posts p
        JOIN clusters c ON c.main_post_id = p.post_id
        WHERE c.cluster_id = %s
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (cluster_id,))
            return cur.fetchone()  # row or None

def get_cluster_posts_full(cluster_id: int):
    """
    Возвращает посты кластера с полями: post_id, channel_tg_id, content, media_urls, views_count,
    reactions_count, comments_count, forwards_count.
    """
    query = """
        SELECT 
            p.post_id,
            p.channel_tg_id,
            p.content,
            p.media_urls,
            p.views_count,
            p.reactions_count,
            p.comments_count,
            p.forwards_count
        FROM cluster_posts cp
        JOIN posts p ON cp.post_id = p.post_id
        WHERE cp.cluster_id = %s;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (cluster_id,))
            rows = cur.fetchall()
            posts = []
            for r in rows:
                posts.append({
                    'post_id': r[0],
                    'channel_tg_id': r[1],
                    'content': r[2] or "",
                    'media_urls': r[3],
                    'views': r[4] or 0,
                    'reactions': r[5] or 0,
                    'comments': r[6] or 0,
                    'forwards': r[7] or 0,
                })
            return posts

def delete_cluster(cluster_id):
    """
    Удаляет кластер и связанные с ним записи (ON DELETE CASCADE).
    """
    query = "DELETE FROM clusters WHERE cluster_id = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (cluster_id,))
            conn.commit()

def get_posts_in_active_clusters():
    """
    Возвращает список постов (post_id, channel_tg_id, message_id) из активных и охлаждающихся кластеров.
    """
    query = """
        SELECT p.post_id, p.channel_tg_id, p.message_id
        FROM clusters c
        JOIN cluster_posts cp ON c.cluster_id = cp.cluster_id
        JOIN posts p ON cp.post_id = p.post_id
        WHERE c.status IN ('active', 'cooling')
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return [
                {'post_id': row[0], 'channel_tg_id': row[1], 'message_id': row[2]}
                for row in cur.fetchall()
            ]

def insert_ad_decision(post_id: int, stage: int, score: float, decision: str, model_version: str = None, features: dict | None = None):
    query = """
        INSERT INTO ad_decisions (post_id, stage, score, decision, model_version, features)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING decision_id;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (post_id, stage, score, decision, model_version, Json(features) if features is not None else None))
            return cur.fetchone()[0]

def get_recent_ad_decisions(limit: int = 200):
    query = """
        SELECT decision_id, post_id, stage, score, decision, model_version, features, created_at
        FROM ad_decisions
        ORDER BY created_at DESC
        LIMIT %s;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def insert_ad_label(post_id: int, label: str, reviewer_tg_id: int | None = None, notes: str | None = None, source: str = 'admin'):
    query = """
        INSERT INTO ad_labels (post_id, label, reviewer_tg_id, notes, source)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (post_id) DO UPDATE SET
            label = EXCLUDED.label,
            reviewer_tg_id = EXCLUDED.reviewer_tg_id,
            notes = EXCLUDED.notes,
            source = EXCLUDED.source
        RETURNING label_id;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (post_id, label, reviewer_tg_id, notes, source))
            return cur.fetchone()[0]

def get_ad_label_for_post(post_id: int):
    query = "SELECT label, reviewer_tg_id, notes, created_at FROM ad_labels WHERE post_id = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (post_id,))
            row = cur.fetchone()
            if not row:
                return None
            return { 'label': row[0], 'reviewer_tg_id': row[1], 'notes': row[2], 'created_at': row[3] }

def increment_pattern_cache(pattern: str):
    query = """
        INSERT INTO ad_pattern_cache(pattern, hits, last_seen)
        VALUES (%s, 1, CURRENT_TIMESTAMP)
        ON CONFLICT (pattern) DO UPDATE SET
            hits = ad_pattern_cache.hits + 1,
            last_seen = CURRENT_TIMESTAMP;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (pattern,))

def get_top_patterns(limit: int = 100):
    query = "SELECT pattern, hits, last_seen FROM ad_pattern_cache ORDER BY hits DESC LIMIT %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            return cur.fetchall()

def upsert_model_version(model_name: str, version: str):
    query = """
        INSERT INTO model_versions(model_name, version)
        VALUES (%s, %s)
        ON CONFLICT (model_name) DO UPDATE SET version = EXCLUDED.version;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (model_name, version))

def update_post_engagement(post_id, views, reactions, comments, forwards, engagement_score):
    """
    Обновляет engagement-метрики для поста:
    - Кол-во просмотров
    - Взвешенные реакции
    - Кол-во комментариев
    - Кол-во пересылок
    - Финальный engagement score (от 0 до 1)
    """
    query = """
        UPDATE posts
        SET 
            prev_views_count = views_count,
            prev_reactions_count = reactions_count,
            prev_comments_count = comments_count,
            prev_forwards_count = forwards_count,
            views_count = %s,
            reactions_count = %s,
            comments_count = %s,
            forwards_count = %s,
            engagement_score = %s,
            last_engagement_update = NOW()
        WHERE post_id = %s;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (
                views,
                reactions,
                comments,
                forwards,
                engagement_score,
                post_id
            ))
            conn.commit()


def get_posts_by_cluster(cluster_id):
    """
    Возвращает список постов для данного кластера с необходимыми метриками:
    views, reactions, comments, forwards, channel_id и post_id.

    Args:
        cluster_id (int): ID кластера

    Returns:
        list[dict]: Список словарей с данными постов
    """
    query = """
        SELECT 
            p.post_id,
            p.channel_tg_id,
            p.views_count,
            p.reactions_count,
            p.comments_count,
            p.forwards_count
        FROM cluster_posts cp
        JOIN posts p ON cp.post_id = p.post_id
        WHERE cp.cluster_id = %s;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (cluster_id,))
            rows = cur.fetchall()
            posts = []
            for row in rows:
                posts.append({
                    'post_id': row[0],
                    'channel_id': row[1],
                    'views': row[2] or 0,
                    'reactions': row[3] or 0,
                    'comments': row[4] or 0,
                    'forwards': row[5] or 0
                })
            return posts

def get_cluster_metadata(cluster_id: int):
    """
    Возвращает метаданные кластера: created_at, expires_at, post_count.
    """
    query = """
        SELECT created_at, expires_at, post_count, status
        FROM clusters WHERE cluster_id = %s;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (cluster_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                'created_at': row[0],
                'expires_at': row[1],
                'post_count': row[2],
                'status' : row[3]
            }

def get_posts_by_cluster_with_reputation(cluster_id):
    """
    Возвращает посты кластера вместе с репутацией канала.
    """
    query = """
        SELECT 
            p.post_id,
            p.channel_tg_id,
            p.views_count,
            p.reactions_count,
            p.comments_count,
            p.forwards_count,
            COALESCE(ch.reputation_score, 0.5) AS reputation_score
        FROM cluster_posts cp
        JOIN posts p ON cp.post_id = p.post_id
        JOIN channels ch ON ch.channel_tg_id = p.channel_tg_id
        WHERE cp.cluster_id = %s;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (cluster_id,))
            rows = cur.fetchall()
            posts = []
            for row in rows:
                posts.append({
                    'post_id': row[0],
                    'channel_id': row[1],
                    'views': row[2] or 0,
                    'reactions': row[3] or 0,
                    'comments': row[4] or 0,
                    'forwards': row[5] or 0,
                    'channel_reputation': float(row[6]) if row[6] is not None else 0.5
                })
            return posts

def archive_cluster(cluster_id):
    """
    Переводит опубликованный кластер в статус 'cooling' (3 дня охлаждения).
    Это позволяет кластеру еще получать похожие новости после публикации.
    """
    # Переводим в cooling вместо архивации, чтобы дать время на получение похожих постов
    query_cluster = """
        UPDATE clusters 
        SET status = 'cooling',
            cooling_expires_at = NOW() + INTERVAL '3 days'
        WHERE cluster_id = %s;
    """
    query_posts = """
            UPDATE posts
            SET status = 'archived'
            WHERE post_id IN (
                SELECT post_id FROM cluster_posts WHERE cluster_id = %s
            );
        """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query_cluster, (cluster_id,))
            cur.execute(query_posts, (cluster_id,))
            conn.commit()
            logger.info(f"Кластер {cluster_id} переведён в статус 'cooling' после публикации")

def archive_cooling_cluster(cluster_id):
    """
    Архивирует охлаждающийся кластер в статус 'archived'.
    Это финальная архивация после периода охлаждения.
    """
    query_cluster = "UPDATE clusters SET status = 'archived' WHERE cluster_id = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query_cluster, (cluster_id,))
            conn.commit()
            logger.info(f"Кластер {cluster_id} окончательно архивирован после периода охлаждения")

def update_post_status(post_id, status):
    """
    Обновляет поле status для одного поста.

    :param post_id: идентификатор поста
    :param status: новое значение статуса, например 'ad', 'active', 'archived'
    """
    query = "UPDATE posts SET status = %s WHERE post_id = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (status, post_id))
            conn.commit()

def update_cluster_status(cluster_id, status):
    """
    Обновляет поле status для одного кластера.

    :param cluster_id: идентификатор кластера
    :param status: новое значение статуса, например 'ad', 'active', 'archived'
    """
    query = "UPDATE clusters SET status = %s WHERE cluster_id = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (status, cluster_id))
            conn.commit()

def get_cluster_id_by_post(post_id):
    query = "SELECT cluster_id FROM cluster_posts WHERE post_id = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (post_id,))
            result = cur.fetchone()
            return result[0] if result else None

def get_channel_tg_id_for_post(post_id: int) -> int | None:
    query = "SELECT channel_tg_id FROM posts WHERE post_id = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (post_id,))
            row = cur.fetchone()
            return row[0] if row else None

def get_engagement_score_score_by_post_id(post_id):
    query = "SELECT engagement_score FROM posts WHERE post_id = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (post_id,))
            result = cur.fetchone()
            return result[0] if result else 0.0

def get_post_content_by_id(post_id):
    query = "SELECT content FROM posts WHERE post_id = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (post_id,))
            result = cur.fetchone()
            if result:
                return result[0]  # содержимое content
            else:
                return None  # пост не найден

def get_post_prev_metrics(post_id: int):
    """
    Возвращает предыдущие метрики и временные метки для поста.
    """
    query = """
        SELECT prev_views_count, prev_reactions_count, prev_comments_count, prev_forwards_count,
               last_engagement_update, published_at
        FROM posts WHERE post_id = %s;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (post_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                'prev_views': row[0] or 0,
                'prev_reactions': row[1] or 0,
                'prev_comments': row[2] or 0,
                'prev_forwards': row[3] or 0,
                'last_update': row[4],
                'published_at': row[5]
            }

def get_system_param(key: str, default: str | None = None):
    """Извлекает системный параметр с TTL-кэшем

    Notes:
    - Кэширует значения на короткий период, чтобы уменьшить нагрузку на базу данных.
    - НЕ используйте это для секретов; секреты должны поступать из env/secret manager.
    """
    now = time.time()
    cached = _SYS_PARAMS_CACHE.get(key)
    if cached is not None:
        value, expires_at = cached
        if now < expires_at:
            return value
        else:
            _SYS_PARAMS_CACHE.pop(key, None)

    query = "SELECT param_value FROM system_params WHERE param_key = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (key,))
            row = cur.fetchone()
            if row:
                value = row[0]
                _SYS_PARAMS_CACHE[key] = (value, now + _SYS_PARAMS_TTL_SECONDS)
                return value
            return default

def set_system_param(key: str, value: str):
    query = """
        INSERT INTO system_params(param_key, param_value)
        VALUES (%s, %s)
        ON CONFLICT (param_key) DO UPDATE SET param_value = EXCLUDED.param_value, updated_at = CURRENT_TIMESTAMP;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (key, value))
            conn.commit()
    # Инвалидирует кэш немедленно
    _SYS_PARAMS_CACHE.pop(key, None)

def log_cluster_score(cluster_id: int, algorithm: str, score: float):
    query = """
        INSERT INTO cluster_scores(cluster_id, algorithm, score)
        VALUES (%s, %s, %s);
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (cluster_id, algorithm, score))
            conn.commit()

def get_recent_clusters(window_minutes: int = 120):
    """
    Возвращает последние кластеры за окно времени.
    """
    query = """
        SELECT cluster_id, created_at, expires_at, post_count, status
        FROM clusters
        WHERE created_at > NOW() - (INTERVAL '1 minute' * %s);
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (window_minutes,))
            rows = cur.fetchall()
            return [
                {
                    'cluster_id': r[0],
                    'created_at': r[1],
                    'expires_at': r[2],
                    'post_count': r[3] or 0,
                    'status': r[4]
                }
                for r in rows
            ]

def get_latest_cluster_scores(algorithm: str, window_minutes: int = 120):
    """
    Возвращает последний зафиксированный скор для каждого кластера в окне времени.
    """
    query = """
        SELECT DISTINCT ON (cluster_id) cluster_id, score
        FROM cluster_scores
        WHERE algorithm = %s
          AND created_at > NOW() - (INTERVAL '1 minute' * %s)
        ORDER BY cluster_id, created_at DESC;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (algorithm, window_minutes))
            rows = cur.fetchall()
            return { r[0]: float(r[1]) for r in rows }

def recalc_channel_reputation(channel_tg_id: int):
    """
    Пересчитывает метрики канала (ad_ratio, quality_score, reputation_score) на основе постов за 30 дней.
    reputation_score в [0..1]: 0.2 + 0.6*(1 - ad_ratio) + 0.2*quality_score, усечённое.
    """
    query_stats = """
        WITH recent AS (
            SELECT status, engagement_score
            FROM posts
            WHERE channel_tg_id = %s AND created_at > NOW() - INTERVAL '30 days'
        )
        SELECT
            CASE WHEN COUNT(*) = 0 THEN 0.0 ELSE (SUM(CASE WHEN status = 'ad' THEN 1 ELSE 0 END)::float / COUNT(*)) END AS ad_ratio,
            COALESCE(percentile_disc(0.5) WITHIN GROUP (ORDER BY engagement_score), 0.0) AS quality_score
        FROM recent;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query_stats, (channel_tg_id,))
            row = cur.fetchone()
            if not row:
                ad_ratio = 0.0
                quality_score = 0.0
            else:
                ad_ratio = float(row[0] or 0.0)
                quality_score = float(row[1] or 0.0)
            reputation = max(0.0, min(1.0, 0.2 + 0.6 * (1.0 - ad_ratio) + 0.2 * quality_score))
            update_query = """
                UPDATE channels
                SET ad_ratio = %s,
                    quality_score = %s,
                    reputation_score = %s,
                    last_reputation_update = NOW(),
                    last_updated = CURRENT_TIMESTAMP
                WHERE channel_tg_id = %s;
            """
            cur.execute(update_query, (ad_ratio, quality_score, reputation, channel_tg_id))
            conn.commit()

def get_channel_reputation(channel_tg_id: int) -> float:
    query = "SELECT reputation_score FROM channels WHERE channel_tg_id = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (channel_tg_id,))
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.5

def get_channel_reputation_by_post_id(post_id: int) -> float:
    query = """
        SELECT COALESCE(c.reputation_score, 0.5)
        FROM posts p JOIN channels c ON c.channel_tg_id = p.channel_tg_id
        WHERE p.post_id = %s;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (post_id,))
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.5


def put_generated_article(cluster_id: int, mode: str,
                          text: str, model_name: str | None,
                          facts_json: dict | None = None) -> int:
    """
    Сохраняет сгенерированный текст в БД
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO generated_articles(cluster_id, mode, model_name, text, facts_json)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (cluster_id, mode, model_name, text, Json(facts_json) if facts_json is not None else None),
            )
            new_id = cur.fetchone()[0]
            conn.commit()
            return new_id


def get_generated_articles_by_date(date: str) -> list[dict]:
    """
    Возвращает сгенерированные статьи, созданные в окне времени вокруг переданной даты.

    Notes:
    - Ширина окна настраивается системным параметром 'generated_lookup_window_seconds'
    """
    # Читаем ширину окна поиска (в секундах); по умолчанию 2 секунды
    try:
        window_seconds_raw = get_system_param('generated_lookup_window_seconds', '300')
        window_seconds = int(window_seconds_raw) if window_seconds_raw is not None else 300
    except Exception as e:
        logger.warning(f"[DB] Ошибка получения окна времени {e}")
        window_seconds = 300

    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            # Сопоставляем по времени с учетом окна
            cur.execute(
                """
                SELECT cluster_id, text, created_at
                FROM generated_articles
                WHERE created_at BETWEEN %s::timestamp - INTERVAL '%s seconds' AND %s::timestamp + INTERVAL '%s seconds'
                ORDER BY ABS(EXTRACT(EPOCH FROM (created_at - %s::timestamp)))
                """,
                (date, window_seconds, date, window_seconds, date),
            )
            rows = cur.fetchall()
            return [
                { 'cluster_id': r[0], 'text': r[1] or '', 'created_at': r[2] }
                for r in rows
            ]


def get_generated_article_cluster_id_by_text_prefix(prefix: str, min_prefix_len: int = 40) -> int | None:
    """
    Ищет cluster_id по префиксу текста сгенерированной статьи (по первым N символам).
    """
    if not prefix:
        return None
    normalized = (prefix or "").strip().replace("\n", " ")
    if len(normalized) < min_prefix_len:
        return None
    candidate = normalized[:min_prefix_len]
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT cluster_id
                FROM generated_articles
                WHERE LEFT(text, %s) = %s
                ORDER BY created_at DESC
                LIMIT 1;
                """,
                (min_prefix_len, candidate),
            )
            row = cur.fetchone()
            return row[0] if row else None


def get_generated_article_by_cluster_id(cluster_id: int) -> str | None:
    """
    Получает сгенерированный текст для кластера.
    
    Args:
        cluster_id: ID кластера
        
    Returns:
        str: Сгенерированный текст или None если не найден
    """
    query = """
        SELECT text
        FROM generated_articles
        WHERE cluster_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (cluster_id,))
                row = cur.fetchone()
                return row[0] if row and row[0] else None
    except Exception as e:
        logger.error(f"Ошибка получения сгенерированного текста для cluster_id={cluster_id}: {e}")
        return None


def get_user_categories(user_id: int) -> list[dict]:
    """
    Получает категории пользователя с их названиями.
    
    Args:
        user_id: ID пользователя в базе данных
        
    Returns:
        list[dict]: Список словарей с информацией о категориях
                   Формат: [{'category_id': int, 'name': str, 'description': str|None}, ...]
    """
    query = """
        SELECT c.category_id, c.name, c.description
        FROM categories c
        JOIN user_categories uc ON c.category_id = uc.category_id
        WHERE uc.user_id = %s
        ORDER BY c.name;
    """
    
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id,))
                categories = []
                for row in cur.fetchall():
                    categories.append({
                        'category_id': row[0],
                        'name': row[1],
                        'description': row[2]
                    })
                logger.info(f"Получены категории для пользователя {user_id}: {len(categories)}")
                return categories
    except psycopg2.Error as e:
        logger.error(f"Ошибка БД при получении категорий пользователя {user_id}: {e}")
        return []
    except Exception as e:
        logger.exception(f"Неожиданная ошибка при получении категорий пользователя {user_id}: {e}")
        return []


def get_user_stats(user_id: int) -> dict:
    """
    Получает статистику пользователя для генерации профиля.
    
    Args:
        user_id: ID пользователя в базе данных
        
    Returns:
        dict: Словарь со статистикой пользователя с ключами:
            - username (str)
            - first_name (str|None)
            - bio (str|None)
            - total_likes (int)
            - total_read (int)
            - days_active (int)
            - avg_engagement (float)
            - favorite_phrase (str)
    """
    # Константа для дефолтного возврата при ошибке
    DEFAULT_STATS = {
        'username': 'user',
        'first_name': None,
        'bio': None,
        'total_likes': 0,
        'total_read': 0,
        'days_active': 0,
        'avg_engagement': 0.0,
        'favorite_phrase': 'Нет фразы'
    }
    
    query = """
        WITH user_stats AS (
            SELECT 
                u.user_id,
                u.username,
                u.first_name,
                u.bio,
                u.created_at,
                COUNT(DISTINCT up.post_id) as total_posts_interacted,
                COUNT(DISTINCT CASE WHEN up.is_liked THEN up.post_id END) as total_likes,
                COUNT(DISTINCT CASE WHEN up.is_read THEN up.post_id END) as total_read,
                EXTRACT(DAYS FROM (CURRENT_TIMESTAMP - u.created_at)) as days_active,
                COALESCE(AVG(p.engagement_score), 0) as avg_engagement
            FROM users u
            LEFT JOIN user_posts up ON u.user_id = up.user_id
            LEFT JOIN posts p ON up.post_id = p.post_id
            WHERE u.user_id = %s
            GROUP BY u.user_id, u.username, u.first_name, u.bio, u.created_at
        ),
        favorite_content AS (
            SELECT LEFT(p.content, 100) as content
            FROM posts p
            JOIN user_posts up ON p.post_id = up.post_id
            WHERE up.user_id = %s AND up.is_liked = true
            ORDER BY p.engagement_score DESC
            LIMIT 1
        )
        SELECT 
            us.username,
            us.first_name,
            us.bio,
            us.total_likes,
            us.total_read,
            us.days_active,
            us.avg_engagement,
            COALESCE(
                us.bio,
                (SELECT fc.content FROM favorite_content fc),
                'Нет фразы'
            ) as favorite_phrase
        FROM user_stats us;
    """
    
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id, user_id))
                row = cur.fetchone()
                
                if not row:
                    logger.warning(f"Пользователь {user_id} не найден в базе")
                    return DEFAULT_STATS.copy()
                
                # Используем понятные индексы через деструктуризацию
                username, first_name, bio, total_likes, total_read, days_active, avg_engagement, favorite_phrase = row
                
                stats = {
                    'username': username or 'user',
                    'first_name': first_name,
                    'bio': bio,
                    'total_likes': int(total_likes or 0),
                    'total_read': int(total_read or 0),
                    'days_active': int(days_active or 0),
                    'avg_engagement': float(avg_engagement or 0.0),
                    'favorite_phrase': favorite_phrase or 'Нет фразы'
                }
                
                # Ограничиваем длину favorite_phrase
                if stats['favorite_phrase']:
                    stats['favorite_phrase'] = stats['favorite_phrase'][:100]
                
                logger.info(f"Получена статистика для пользователя {user_id}: likes={stats['total_likes']}, days={stats['days_active']}")
                return stats
                
    except Exception as e:
        logger.error(f"Ошибка получения статистики пользователя {user_id}: {e}", exc_info=True)
        return DEFAULT_STATS.copy()


def update_user_bio(user_tg_id: int, bio: str) -> bool:
    """
    Обновляет bio пользователя
    
    Args:
        user_tg_id: Telegram ID пользователя
        bio: Описание пользователя
        
    Returns:
        True если успешно, False в случае ошибки
    """
    query = """
        UPDATE users 
        SET bio = %s 
        WHERE user_tg_id = %s;
    """
    
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (bio, user_tg_id))
                conn.commit()
                
        logger.info(f"Bio пользователя {user_tg_id} обновлен")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка обновления bio пользователя {user_tg_id}: {e}")
        return False


# ====================
# Функции для системы рекомендаций и персонализации
# ====================

def get_user_category_weights(user_id: int) -> Dict[int, float]:
    """
    Получает веса категорий для пользователя.
    
    Args:
        user_id: ID пользователя в БД
        
    Returns:
        Dict[int, float]: Словарь {category_id: weight}
    """
    query = """
        SELECT category_id, weight
        FROM user_category_weights
        WHERE user_id = %s
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id,))
                return {row[0]: float(row[1]) for row in cur.fetchall()}
    except Exception as e:
        logger.error(f"Ошибка получения весов категорий для user_id={user_id}: {e}")
        return {}


def update_user_category_weight(user_id: int, category_id: int, delta: float):
    """
    Обновляет вес категории для пользователя.
    
    Args:
        user_id: ID пользователя
        category_id: ID категории
        delta: Изменение веса (может быть отрицательным)
    """
    query = """
        INSERT INTO user_category_weights (user_id, category_id, weight)
        VALUES (%s, %s, GREATEST(0.1, LEAST(2.0, 1.0 + %s)))
        ON CONFLICT (user_id, category_id) DO UPDATE
        SET weight = GREATEST(0.1, LEAST(2.0, user_category_weights.weight + %s)),
            last_updated = CURRENT_TIMESTAMP
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id, category_id, delta, delta))
                conn.commit()
    except Exception as e:
        logger.error(f"Ошибка обновления веса категории: {e}")


def get_cluster_categories(cluster_id: int) -> List[int]:
    """
    Получает список категорий кластера через каналы.
    
    Args:
        cluster_id: ID кластера
        
    Returns:
        List[int]: Список ID категорий
    """
    query = """
        SELECT DISTINCT cc.category_id
        FROM clusters c
        JOIN posts p ON p.post_id = c.main_post_id
        JOIN channels ch ON ch.channel_tg_id = p.channel_tg_id
        JOIN channel_categories cc ON cc.channel_id = ch.channel_id
        WHERE c.cluster_id = %s
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (cluster_id,))
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения категорий кластера {cluster_id}: {e}")
        return []


def get_cluster_channels(cluster_id: int) -> List[int]:
    """
    Получает список channel_tg_id каналов в кластере.
    
    Args:
        cluster_id: ID кластера
        
    Returns:
        List[int]: Список channel_tg_id
    """
    query = """
        SELECT DISTINCT p.channel_tg_id
        FROM clusters c
        JOIN cluster_posts cp ON cp.cluster_id = c.cluster_id
        JOIN posts p ON p.post_id = cp.post_id
        WHERE c.cluster_id = %s
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (cluster_id,))
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения каналов кластера {cluster_id}: {e}")
        return []


def get_cluster_embedding(cluster_id: int) -> List[float]:
    """
    Получает embedding главного поста кластера.
    
    Args:
        cluster_id: ID кластера
        
    Returns:
        List[float]: Embedding вектор или None
    """
    query = """
        SELECT p.embedding_vec
        FROM clusters c
        JOIN posts p ON p.post_id = c.main_post_id
        WHERE c.cluster_id = %s
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (cluster_id,))
                row = cur.fetchone()
                if row and row[0]:
                    return list(row[0])
                return None
    except Exception as e:
        logger.error(f"Ошибка получения embedding кластера {cluster_id}: {e}")
        return None


def get_user_preferred_embedding(user_id: int) -> List[float]:
    """
    Получает предпочтительный embedding пользователя.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        List[float]: Embedding вектор или None
    """
    query = """
        SELECT preferred_embedding
        FROM user_profiles
        WHERE user_id = %s
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id,))
                row = cur.fetchone()
                if row and row[0]:
                    return list(row[0])
                return None
    except Exception as e:
        logger.error(f"Ошибка получения preferred embedding для user_id={user_id}: {e}")
        return None


def update_user_preferred_embedding(user_id: int, embedding: List[float]):
    """
    Обновляет предпочтительный embedding пользователя.
    
    Args:
        user_id: ID пользователя
        embedding: Новый embedding вектор
    """
    query = """
        INSERT INTO user_profiles (user_id, preferred_embedding, last_updated)
        VALUES (%s, %s::vector, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE
        SET preferred_embedding = EXCLUDED.preferred_embedding,
            last_updated = CURRENT_TIMESTAMP
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id, embedding))
                conn.commit()
    except Exception as e:
        logger.error(f"Ошибка обновления preferred embedding для user_id={user_id}: {e}")


def get_user_channel_preferences(user_id: int) -> Dict[int, float]:
    """
    Получает предпочтения пользователя к каналам.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Dict[int, float]: Словарь {channel_tg_id: preference_score}
    """
    query = """
        SELECT channel_tg_id, preference_score
        FROM user_channel_preferences
        WHERE user_id = %s
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id,))
                return {row[0]: float(row[1]) for row in cur.fetchall()}
    except Exception as e:
        logger.error(f"Ошибка получения channel preferences для user_id={user_id}: {e}")
        return {}


def get_user_activity_stats(user_id: int) -> Dict:
    """
    Получает статистику активности пользователя.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Dict: Словарь со статистикой активности
    """
    query = """
        SELECT avg_active_hour, active_days, timezone_offset, interaction_count, last_interaction
        FROM user_activity_stats
        WHERE user_id = %s
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id,))
                row = cur.fetchone()
                if row:
                    return {
                        'avg_active_hour': row[0],
                        'active_days': row[1] if row[1] else [],
                        'timezone_offset': row[2] or 0,
                        'interaction_count': row[3] or 0,
                        'last_interaction': row[4]
                    }
                return {}
    except Exception as e:
        logger.error(f"Ошибка получения activity stats для user_id={user_id}: {e}")
        return {}


def update_user_activity_stats(user_id: int, active_hour: int, active_day: int):
    """
    Обновляет статистику активности пользователя.
    
    Args:
        user_id: ID пользователя
        active_hour: Час активности (0-23)
        active_day: День недели (0-6, где 0 = понедельник)
    """
    query = """
        INSERT INTO user_activity_stats (user_id, avg_active_hour, active_days, interaction_count, last_interaction, last_updated)
        VALUES (%s, %s, %s::jsonb, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE
        SET avg_active_hour = (
            CASE 
                WHEN user_activity_stats.avg_active_hour IS NULL THEN %s
                ELSE (user_activity_stats.avg_active_hour + %s) / 2
            END
        ),
        active_days = (
            CASE 
                WHEN user_activity_stats.active_days IS NULL OR jsonb_array_length(user_activity_stats.active_days) = 0
                THEN %s::jsonb
                ELSE user_activity_stats.active_days || %s::jsonb
            END
        ),
        interaction_count = user_activity_stats.interaction_count + 1,
        last_interaction = CURRENT_TIMESTAMP,
        last_updated = CURRENT_TIMESTAMP
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                # Преобразуем день в JSONB массив
                import json
                active_days_json = json.dumps([active_day])
                cur.execute(query, (user_id, active_hour, active_days_json, active_hour, active_hour, active_days_json, active_days_json))
                conn.commit()
    except Exception as e:
        logger.error(f"Ошибка обновления activity stats для user_id={user_id}: {e}")


def get_cluster_created_at(cluster_id: int):
    """
    Получает время создания кластера.
    
    Args:
        cluster_id: ID кластера
        
    Returns:
        datetime: Время создания или None
    """
    query = """
        SELECT created_at
        FROM clusters
        WHERE cluster_id = %s
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (cluster_id,))
                row = cur.fetchone()
                return row[0] if row else None
    except Exception as e:
        logger.error(f"Ошибка получения created_at для cluster_id={cluster_id}: {e}")
        return None


def get_user_liked_clusters(user_id: int, limit: int = 50) -> List[Tuple[int, List[float]]]:
    """
    Получает список кластеров, которые пользователь лайкнул, с их embedding.
    
    Args:
        user_id: ID пользователя
        limit: Максимальное количество кластеров
        
    Returns:
        List[Tuple[int, List[float]]]: Список (cluster_id, embedding)
    """
    query = """
        SELECT DISTINCT c.cluster_id, p.embedding_vec
        FROM user_posts up
        JOIN posts p ON p.post_id = up.post_id
        JOIN cluster_posts cp ON cp.post_id = p.post_id
        JOIN clusters c ON c.cluster_id = cp.cluster_id
        WHERE up.user_id = %s
          AND up.is_liked = TRUE
          AND p.embedding_vec IS NOT NULL
        ORDER BY up.read_at DESC
        LIMIT %s
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id, limit))
                return [(row[0], list(row[1]) if row[1] else None) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения liked clusters для user_id={user_id}: {e}")
        return []


def add_to_user_queue(user_id: int, cluster_id: int, personal_score: float, priority: int, scheduled_for=None):
    """
    Добавляет кластер в очередь пользователя.
    
    Args:
        user_id: ID пользователя
        cluster_id: ID кластера
        personal_score: Персональный score
        priority: Приоритет (1-10)
        scheduled_for: Запланированное время отправки (опционально)
    """
    query = """
        INSERT INTO user_post_queue (user_id, cluster_id, personal_score, priority, scheduled_for, status)
        VALUES (%s, %s, %s, %s, %s, 'pending')
        ON CONFLICT (user_id, cluster_id) DO UPDATE
        SET personal_score = EXCLUDED.personal_score,
            priority = EXCLUDED.priority,
            scheduled_for = EXCLUDED.scheduled_for,
            status = CASE 
                WHEN user_post_queue.status = 'pending' THEN 'pending'
                ELSE EXCLUDED.status
            END
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id, cluster_id, personal_score, priority, scheduled_for))
                conn.commit()
    except Exception as e:
        logger.error(f"Ошибка добавления в очередь: {e}")


def get_user_queue(user_id: int, limit: int = 10, status: str = 'pending') -> List[Dict]:
    """
    Получает очередь новостей пользователя.
    
    Args:
        user_id: ID пользователя
        limit: Максимальное количество записей
        status: Статус записей ('pending', 'sent', 'skipped', 'expired')
        
    Returns:
        List[Dict]: Список записей очереди
    """
    query = """
        SELECT queue_id, cluster_id, personal_score, priority, scheduled_for, created_at
        FROM user_post_queue
        WHERE user_id = %s AND status = %s
        ORDER BY priority DESC, personal_score DESC, scheduled_for NULLS LAST
        LIMIT %s
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id, status, limit))
                return [
                    {
                        'queue_id': row[0],
                        'cluster_id': row[1],
                        'personal_score': float(row[2]),
                        'priority': row[3],
                        'scheduled_for': row[4],
                        'created_at': row[5]
                    }
                    for row in cur.fetchall()
                ]
    except Exception as e:
        logger.error(f"Ошибка получения очереди для user_id={user_id}: {e}")
        return []


def mark_queue_item_sent(user_id: int, cluster_id: int):
    """
    Помечает элемент очереди как отправленный.
    
    Args:
        user_id: ID пользователя
        cluster_id: ID кластера
    """
    query = """
        UPDATE user_post_queue
        SET status = 'sent', sent_at = CURRENT_TIMESTAMP
        WHERE user_id = %s AND cluster_id = %s AND status = 'pending'
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id, cluster_id))
                conn.commit()
    except Exception as e:
        logger.error(f"Ошибка пометки очереди как sent: {e}")


def get_user_post_count_today(user_id: int) -> int:
    """
    Получает количество постов, отправленных пользователю сегодня.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        int: Количество постов
    """
    query = """
        SELECT COALESCE(SUM(post_count), 0)
        FROM user_post_counters
        WHERE user_id = %s AND date = CURRENT_DATE
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id,))
                row = cur.fetchone()
                return int(row[0]) if row else 0
    except Exception as e:
        logger.error(f"Ошибка получения post count today для user_id={user_id}: {e}")
        return 0


def get_user_post_count_hour(user_id: int, hour: int) -> int:
    """
    Получает количество постов, отправленных пользователю в указанный час сегодня.
    
    Args:
        user_id: ID пользователя
        hour: Час (0-23)
        
    Returns:
        int: Количество постов
    """
    query = """
        SELECT COALESCE(SUM(post_count), 0)
        FROM user_post_counters
        WHERE user_id = %s AND date = CURRENT_DATE AND hour = %s
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id, hour))
                row = cur.fetchone()
                return int(row[0]) if row else 0
    except Exception as e:
        logger.error(f"Ошибка получения post count hour для user_id={user_id}, hour={hour}: {e}")
        return 0


def increment_user_post_counter(user_id: int):
    """
    Увеличивает счетчик отправленных постов для пользователя.
    
    Args:
        user_id: ID пользователя
    """
    from datetime import datetime
    current_date = datetime.now().date()
    current_hour = datetime.now().hour
    
    query = """
        INSERT INTO user_post_counters (user_id, date, hour, post_count)
        VALUES (%s, %s, %s, 1)
        ON CONFLICT (user_id, date, hour) DO UPDATE
        SET post_count = user_post_counters.post_count + 1
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id, current_date, current_hour))
                conn.commit()
    except Exception as e:
        logger.error(f"Ошибка увеличения post counter для user_id={user_id}: {e}")


def get_active_users() -> List[int]:
    """
    Получает список активных пользователей (user_id в БД).
    
    Returns:
        List[int]: Список user_id
    """
    query = """
        SELECT user_id
        FROM users
        WHERE status = 'active'
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения active users: {e}")
        return []
