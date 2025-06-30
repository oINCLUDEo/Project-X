import psycopg2
import logging
from config.config import load_config

__all__ = ['get_channels', 'get_category_users', 'get_channel_category', 'add_user', 'add_channel', 'update_channel_info']
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