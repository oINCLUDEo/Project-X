import os
from dataclasses import dataclass
from dotenv import load_dotenv
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings
from typing import Optional


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
    api_hash: str           # API-Hash для доступа к клиенту(парсеру) через API
    password: str           # Пароль от Telegram аккаунта с которого парсятся паблики


@dataclass
class StorageConfig:
    media_dir: str          # Каталог для сохранения медиа


@dataclass
class Config:
    aiogram_bot: AiogramBot
    telethon_client: TelethonClient
    db: DatabaseConfig
    storage: StorageConfig
    # Optional, not used everywhere but validated and available
    dev_logs: bool | None = None
    openai_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None
    openrouter_referer: Optional[str] = None
    openrouter_title: Optional[str] = None


class EnvSettings(BaseSettings):
    # Aiogram
    BOT_TOKEN: str

    # Telethon
    API_ID: int
    API_HASH: str
    TG_ACCOUNT_PARSER_PASSWORD: str

    # Database
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str = Field(default="localhost")
    DB_PORT: int = Field(default=5432)

    # Storage
    MEDIA_DIR: str = Field(default="media")

    # Optional
    DEV_LOGS: bool | None = None

    # OpenRouter
    OPENAI_BASE_URL: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: Optional[str] = None
    OPENROUTER_REFERER: Optional[str] = None
    OPENROUTER_TITLE: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False


def load_config() -> Config:
    """Загружает и проверяет конфигурацию из переменных окружения.

    Сохраняет существующий возвращаемый тип на основе dataclass Config,
    но использует Pydantic для типизированного парсинга, значений по умолчанию
    и валидации. Это позволяет другим модулям продолжать использовать
    load_config() без изменений.
    """
    # Гарантируем чтение .env файла для совместимости с не-Pydantic компонентами
    load_dotenv()
    try:
        env = EnvSettings()  # type: ignore[call-arg]
    except ValidationError as e:
        # Перевыбрасываем исключение с понятным сообщением для упрощения отладки
        raise RuntimeError(f"[CONFIG] Неверная конфигурация окружения: {e}")

    return Config(
        aiogram_bot=AiogramBot(
            token=env.BOT_TOKEN
        ),
        telethon_client=TelethonClient(
            api_id=env.API_ID,
            api_hash=env.API_HASH,
            password=env.TG_ACCOUNT_PARSER_PASSWORD
        ),
        db=DatabaseConfig(
            db_name=env.DB_NAME,
            db_host=env.DB_HOST,
            db_user=env.DB_USER,
            db_password=env.DB_PASSWORD,
            db_port=str(env.DB_PORT)
        ),
        storage=StorageConfig(
            media_dir=env.MEDIA_DIR
        ),
        # Опциональные параметры
        dev_logs=env.DEV_LOGS,
        openai_base_url=env.OPENAI_BASE_URL,
        openai_api_key=env.OPENAI_API_KEY,
        openai_model=env.OPENAI_MODEL,
        openrouter_referer=env.OPENROUTER_REFERER,
        openrouter_title=env.OPENROUTER_TITLE,
    )
