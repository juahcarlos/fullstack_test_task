"""Помощник ожидания результата асинхронной обработки файла воркером.

POST /files возвращает ответ сразу после постановки задачи в очередь —
обработка (_process_file) идёт в отдельном процессе-воркере асинхронно.
Тест не может проверять processing_status сразу после запроса, поэтому
поллит БД до готовности или таймаута.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import StoredFile


async def wait_for_processing(
    session_maker: async_sessionmaker,
    file_id: str,
    timeout: float = 10.0,
    interval: float = 0.2,
) -> StoredFile:
    """Ждёт, пока воркер завершит обработку файла (processing_status != 'uploaded').

    Args:
        session_maker (async_sessionmaker): Фабрика сессий тестовой БД.
        file_id (str): Идентификатор файла, обработку которого ждём.
        timeout (float): Максимальное время ожидания в секундах.
        interval (float): Пауза между проверками в секундах.

    Returns:
        StoredFile: Запись файла после завершения обработки (processed/failed).

    Raises:
        TimeoutError: Если обработка не завершилась за отведённое время.
    """
    elapsed = 0.0
    async with session_maker() as session:
        while elapsed < timeout:
            result = await session.execute(select(StoredFile).where(StoredFile.id == file_id))
            file_item = result.scalar_one_or_none()
            if file_item and file_item.processing_status in {"processed", "failed"}:
                return file_item
            session.expire_all()
            await asyncio.sleep(interval)
            elapsed += interval
    raise TimeoutError(f"File {file_id} was not processed within {timeout}s")