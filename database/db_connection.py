import psycopg2
import logging
import os
from dotenv import load_dotenv

# Загрузка переменных окружения из файла .env
load_dotenv()
logger = logging.getLogger(__name__)

# Получение значений переменных окружения
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')


def get_users():
    query = "SELECT user_tg_id FROM users;"
    # Подключение к базе данных postgres
    with psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            users = [user[0] for user in cur.fetchall()]

            logger.info("Возвращен список пользователей")
            return users


def get_channels():
    query = "SELECT channel_tg_id FROM channels;"
    # Подключение к базе данных postgres
    with psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
    ) as conn:
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
    # Подключение к базе данных postgres
    with psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
    ) as conn:
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
    # Подключение к базе данных postgres
    with psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(query, (channel_tg_id,))
            categories = [category[0] for category in cur.fetchall()]

            logger.info("Возвращен список категорий канала channel_tg_id")
            return categories


def add_user(user_id):
    query = "INSERT INTO users(user_tg_id) VALUES (%s);"
    try:
        # Подключение к базе данных postgres
        with psycopg2.connect(
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                host=DB_HOST,
                port=DB_PORT
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id,))

        logger.info("Пользователь успешно добавлен!")
    except psycopg2.IntegrityError:
        logger.exception("Ошибка уникальности:")
