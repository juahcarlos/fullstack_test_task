"""Конфигурация приложения.

Модуль собирает все настройки сервиса (подключение к БД, Redis,
хранилище файлов, лимиты загрузки) в единый объект Settings на базе
pydantic-settings вместо разрозненных os.environ.get() по всему коду.
Значения читаются из переменных окружения и/или файла .env.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения, валидируемые pydantic при старте."""

    # Источник значений: переменные окружения и файл .env; неизвестные
    # переменные окружения игнорируются, а не вызывают ошибку валидации.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Параметры подключения к PostgreSQL — приходят из окружения контейнера.
    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_db: str
    pgport: int = 5432

    # URL брокера/backend'а для Celery (Redis).
    redis_url: str = "redis://backend-redis:6379/0"

    # Директория хранения загруженных файлов на диске.
    # parents[3] поднимается от core/config.py до backend/, затем storage/files.
    storage_dir: Path = Path(__file__).resolve().parents[3] / "storage" / "files"

    # Максимально допустимый размер загружаемого файла в байтах (10 МБ).
    max_upload_size: int = 10 * 1024 * 1024

    @property
    def database_url(self) -> str:
        """Собирает строку подключения SQLAlchemy (async, asyncpg-драйвер)."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.pgport}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр Settings (создаётся один раз)."""
    return Settings()