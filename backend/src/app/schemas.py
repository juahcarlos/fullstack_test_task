"""Pydantic-схемы для сериализации запросов/ответов API.

Соответствуют полям моделей из models.py; from_attributes=True позволяет
строить схему напрямую из ORM-объекта.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileItem(BaseModel):
    """Представление файла в ответах API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    original_name: str
    mime_type: str
    size: int
    processing_status: str
    scan_status: str | None
    scan_details: str | None
    metadata_json: dict | None
    requires_attention: bool
    created_at: datetime
    updated_at: datetime


class FileUpdate(BaseModel):
    """Тело запроса на обновление файла — на данный момент только название."""

    title: str


class AlertItem(BaseModel):
    """Представление алерта в ответах API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    file_id: str
    level: str
    message: str
    created_at: datetime