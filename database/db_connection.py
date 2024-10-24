import psycopg2
import logging
from config.config import load_config

__all__ = ['get_channels', 'get_category_users', 'get_channel_category', 'add_user']
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

def get_category_users(category_id):
    query = """
            SELECT user_tg_id FROM users u 
            JOIN user_categories uc ON u.user_id = uc.user_id 
            WHERE uc.category_id IN %s
            GROUP BY user_tg_id;
            """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (category_id,))
            users = [user[0] for user in cur.fetchall()]

            logger.info("Возвращен список пользователей, имеющих category_id")
            return users

def get_channel_category(channel_tg_id):
    query = """
            SELECT category_id FROM channel_categories cc
            JOIN channels c ON c.channel_id = cc.channel_id
            WHERE c.channel_tg_id = %s;
            """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (channel_tg_id,))
            categories = [category[0] for category in cur.fetchall()]

            logger.info("Возвращен список категорий канала channel_tg_id")
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
