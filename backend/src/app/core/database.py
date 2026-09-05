"""Инициализация подключения к базе данных.

Создаёт единый асинхронный engine и sessionmaker SQLAlchemy на основе
настроек из core/config.py. Сессия предоставляется как FastAPI-зависимость
(get_session), что позволяет подменять её в тестах через переопределение
Depends, а не полагаться на глобальный объект, создаваемый при импорте.
Этот же async_session_maker переиспользуется в Celery-таске (tasks.py),
чтобы не дублировать конфигурацию подключения к БД.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# Асинхронный engine — одно соединение-пул на всё приложение.
engine = create_async_engine(settings.database_url)

# Фабрика сессий. expire_on_commit=False — чтобы после commit можно было
# читать атрибуты объекта без дополнительного похода в БД.
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-зависимость: открывает сессию на время запроса и закрывает её после."""
    async with async_session_maker() as session:
        yield session