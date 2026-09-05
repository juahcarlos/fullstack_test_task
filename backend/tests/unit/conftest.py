"""Общие фикстуры для unit-тестов.

mock_uow эмулирует UnitOfWork: атрибуты files/alerts — это моки
BaseRepository (AsyncMock), поэтому сервисы тестируются без обращения
к реальной БД. task_dispatcher подменяется отдельным моком, чтобы
проверять факт вызова без реального Celery/Redis.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_uow() -> MagicMock:
    """Возвращает мок UnitOfWork с мок-репозиториями files и alerts.

    Returns:
        MagicMock: Объект с атрибутами .files и .alerts, каждый из которых
            имеет асинхронные методы get_by_id/get_multi/create/update/delete.
    """
    uow = MagicMock()
    uow.files = AsyncMock()
    uow.alerts = AsyncMock()
    uow.session = AsyncMock()
    uow.commit = AsyncMock()
    return uow


@pytest.fixture
def mock_task_dispatcher() -> MagicMock:
    """Возвращает мок функции постановки задачи в очередь (аналог process_file.delay).

    Returns:
        MagicMock: Мок, вызов которого можно проверить в assert.
    """
    return MagicMock()