import psycopg2
from psycopg2.extras import Json
import logging
from config.config import load_config

__all__ = ['get_channels', 'get_category_users', 'get_channel_category', 'add_user', 'add_channel', 'update_channel_info',
           'add_post', 'create_new_cluster', 'add_post_to_cluster', 'get_recent_clusters_with_embeddings',
           'get_expired_clusters', 'get_main_post_for_cluster', 'delete_cluster',
           'get_posts_in_active_clusters', 'update_post_engagement', 'get_posts_by_cluster', 'archive_cluster',
           'update_post_status', 'update_cluster_status', 'get_cluster_id_by_post',
           'get_engagement_score_score_by_post_id', 'get_post_content_by_id',
           'insert_ad_decision', 'insert_ad_label', 'get_ad_label_for_post', 'increment_pattern_cache',
           'get_top_patterns', 'get_recent_ad_decisions', 'upsert_model_version']
logger = logging.getLogger(__name__)
config = load_config()

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
            AND u.is_active = TRUE;
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

def add_user(user_tg_id):
    query = "INSERT INTO users(user_tg_id) VALUES (%s);"
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_tg_id,))

        logger.info("Пользователь успешно добавлен!")
    except psycopg2.IntegrityError:
        logger.exception("Ошибка уникальности:")


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


def add_post(channel_tg_id: int, content: str, embedding: list[float], media_urls: list[str], message_id: int = None):
    """
    Добавляет новость с эмбеддингом в базу данных, включая message_id.
    """
    query = """
        INSERT INTO posts (channel_tg_id, content, embedding, media_urls, message_id)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING post_id;
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (
                    channel_tg_id,
                    content,
                    embedding,
                    media_urls,
                    message_id
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


def get_recent_clusters_with_embeddings(limit=50) -> list[tuple[int, list[float]]]:
    query = """
        SELECT c.cluster_id, p.embedding
        FROM clusters c
        JOIN posts p ON c.main_post_id = p.post_id
        ORDER BY c.created_at DESC
        LIMIT %s;
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            return [(row[0], row[1]) for row in cur.fetchall()]

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

def get_active_clusters():
    """
    Возвращает список активных кластеров (expires_at > NOW()).
    """
    query = """
        SELECT cluster_id, main_post_id FROM clusters
        WHERE expires_at > NOW() AND status = 'active'
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
    Возвращает список постов (post_id, channel_tg_id, message_id) из активных кластеров.
    """
    query = """
        SELECT p.post_id, p.channel_tg_id, p.message_id
        FROM clusters c
        JOIN cluster_posts cp ON c.cluster_id = cp.cluster_id
        JOIN posts p ON cp.post_id = p.post_id
        WHERE c.expires_at > NOW() AND c.status = 'active'
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
            views_count = %s,
            reactions_count = %s,
            comments_count = %s,
            forwards_count = %s,
            engagement_score = %s
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

def archive_cluster(cluster_id):
    """
    Архивирует кластер и связанные с ним посты.
    """
    query_cluster = "UPDATE clusters SET status = 'archived' WHERE cluster_id = %s;"
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

