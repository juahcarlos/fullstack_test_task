"""DI-зависимости FastAPI.

Вместо отдельных зависимостей на каждый репозиторий приложение получает
один UnitOfWork на запрос — сервисы работают с ним напрямую (uow.files,
uow.alerts), а транзакция коммитится по выходу из UoW.
"""

from typing import Annotated

from fastapi import Depends

from app.core.database import async_session_maker
from app.core.uow import UnitOfWork
from app.services import AlertService, FileService
from app.tasks import process_file


async def get_uow():
    """Открывает UnitOfWork на время обработки запроса.

    Returns:
        AsyncGenerator[UnitOfWork, None]: Готовый к использованию UoW.
    """
    async with UnitOfWork(async_session_maker) as uow:
        yield uow


UoWDep = Annotated[UnitOfWork, Depends(get_uow)]


def get_file_service(uow: UoWDep) -> FileService:
    """Собирает сервис файлов.

    Args:
        uow (UnitOfWork): Unit of Work текущего запроса.

    Returns:
        FileService: Готовый к использованию сервис файлов.
    """
    return FileService(uow=uow, task_dispatcher=process_file.delay)


def get_alert_service(uow: UoWDep) -> AlertService:
    """Собирает сервис алертов.

    Args:
        uow (UnitOfWork): Unit of Work текущего запроса.

    Returns:
        AlertService: Готовый к использованию сервис алертов.
    """
    return AlertService(uow=uow)


FileServiceDep = Annotated[FileService, Depends(get_file_service)]
AlertServiceDep = Annotated[AlertService, Depends(get_alert_service)]