import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class DatabaseConfig:
    db_name: str         # Название базы данных
    db_user: str          # Username пользователя базы данных
    db_password: str      # Пароль к базе данных
    db_host: str          # URL-адрес базы данных
    db_port: str          # Порт базы данных


@dataclass
class AiogramBot:
    token: str            # Токен для доступа к телеграм-боту


@dataclass
class TelethonClient:
    api_id: int            # API-ID для доступа к клиенту(парсеру) через API
    api_hash: str            # API-Hash для доступа к клиенту(парсеру) через API


@dataclass
class Config:
    aiogram_bot: AiogramBot
    telethon_client: TelethonClient
    db: DatabaseConfig


def load_config() -> Config:
    load_dotenv()   # Загрузка переменных окружения из файла .env

    return Config(
        aiogram_bot=AiogramBot(
            token=os.getenv('BOT_TOKEN')
        ),
        telethon_client=TelethonClient(
            api_id=int(os.getenv('API_ID')),
            api_hash=os.getenv('API_HASH')
        ),
        db=DatabaseConfig(
            db_name=os.getenv('DB_NAME'),
            db_host=os.getenv('DB_HOST'),
            db_user=os.getenv('DB_USER'),
            db_password=os.getenv('DB_PASSWORD'),
            db_port=os.getenv('DB_PORT')
        )
    )
