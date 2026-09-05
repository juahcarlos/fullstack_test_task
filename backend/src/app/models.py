"""ORM-модели SQLAlchemy.

Base объявлен здесь же — от неё наследуются все модели проекта и на неё
опирается generic BaseRepository (bound=Base) в repositories.py.
Схема БД и поля моделей не менялись относительно исходного варианта —
задача рефакторинга не подразумевает изменение бизнес-логики/данных.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей проекта."""

    pass


class StoredFile(Base):
    """Загруженный файл и его текущее состояние обработки/сканирования."""

    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Имя, под которым файл реально лежит на диске (уникально, чтобы избежать коллизий).
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    # Статус пайплайна обработки: uploaded -> processing -> processed/failed.
    processing_status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded")
    # Результат проверки на подозрительный контент: clean / suspicious / failed / None (ещё не проверен).
    scan_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    scan_details: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Извлечённые метаданные файла (строки/страницы и т.п.), формат зависит от mime_type.
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    requires_attention: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Alert(Base):
    """Уведомление, связанное с обработкой конкретного файла."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id"), nullable=False)
    # Уровень серьёзности: info / warning / critical.
    level: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )