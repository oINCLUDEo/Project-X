import psycopg2
import os
from dotenv import load_dotenv

# Загрузка переменных окружения из файла .env
load_dotenv()

# Получение значений переменных окружения
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')


def get_users():
    # Подключение к базе данных postgres
    with psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users;")
            users = [user[0] for user in cur.fetchall()]

            return users


def add_user(user_id):
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
                cur.execute("INSERT INTO users(user_id) VALUES (%s);", (user_id,))

        return "Пользователь успешно добавлен!"
    except psycopg2.IntegrityError as e:

        return f"Ошибка уникальности: {e}"
