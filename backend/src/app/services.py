"""Сервисный слой: бизнес-логика работы с файлами и алертами.

Сервисы принимают UnitOfWork через конструктор (а не отдельные
репозитории или сессию напрямую) — это единая точка доступа к БД и
транзакции, репозитории достаются как uow.files/uow.alerts. Такой же
UnitOfWork подставляется в тестах с мок-репозиториями внутри, без
обращения к реальной БД.
"""
import asyncio
import mimetypes
import re
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.uow import UnitOfWork
from app.exceptions import EmptyFileError, FileNotFoundInStorageError
from app.models import Alert, StoredFile

settings = get_settings()

# Разрешены только буквы/цифры/точка/дефис/подчёркивание — остальное заменяется на "_".
_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: str) -> str:
    """Приводит оригинальное имя файла к безопасному виду.

    Убирает возможные компоненты пути (защита от path traversal) и
    заменяет недопустимые символы, чтобы имя было безопасно использовать
    в заголовке Content-Disposition при отдаче файла.

    Args:
        name (str): Исходное имя файла, полученное от клиента.

    Returns:
        str: Безопасное имя файла, пригодное для хранения/выдачи.
    """
    name = Path(name).name  # отбрасываем любые компоненты пути
    name = _UNSAFE_NAME_CHARS.sub("_", name)
    return name or "unnamed"


class FileService:
    """Бизнес-логика, связанная с загруженными файлами."""

    def __init__(
        self,
        uow: UnitOfWork,
        task_dispatcher: Callable[[str], None] | None = None,
    ):
        """Инициализирует сервис.

        Args:
            uow (UnitOfWork): Unit of Work текущего запроса (даёт uow.files/uow.alerts).
            task_dispatcher (Callable[[str], None] | None): Функция постановки файла
                в очередь на обработку (обычно process_file.delay). Опциональна —
                в тестах заменяется на мок или None.
        """
        self.uow = uow
        self.task_dispatcher = task_dispatcher

    async def list_files(self, skip: int = 0, limit: int = 50) -> list[StoredFile]:
        """Возвращает страницу файлов.

        Args:
            skip (int): Количество записей, пропускаемых от начала выборки.
            limit (int): Максимальное количество записей в ответе.

        Returns:
            list[StoredFile]: Список файлов текущей страницы.
        """
        return await self.uow.files.get_multi(skip=skip, limit=limit)

    async def get_file(self, file_id: str) -> StoredFile:
        """Возвращает файл по идентификатору.

        Args:
            file_id (str): Идентификатор файла.

        Returns:
            StoredFile: Найденная запись файла.

        Raises:
            HTTPException: 404, если файл с таким id не найден.
        """
        file_item = await self.uow.files.get_by_id(file_id)
        if not file_item:
            raise FileNotFoundInStorageError(f"File {file_id} not found")
        return file_item

    async def get_file_with_path(self, file_id: str) -> tuple[StoredFile, Path]:
        """Возвращает файл вместе с путём к нему на диске.

        Args:
            file_id (str): Идентификатор файла.

        Returns:
            tuple[StoredFile, Path]: Запись файла и путь к физическому файлу на диске.

        Raises:
            HTTPException: 404, если запись не найдена или файл отсутствует на диске.
        """
        file_item = await self.get_file(file_id)
        stored_path = settings.storage_dir / file_item.stored_name
        if not stored_path.exists():
            raise FileNotFoundInStorageError(f"Stored file for {file_id} not found on disk")
        return file_item, stored_path

    async def create_file(self, title: str, upload_file: UploadFile) -> StoredFile:
        """Сохраняет загруженный файл на диск, создаёт запись в БД и ставит его в очередь на обработку.

        Args:
            title (str): Пользовательское название файла.
            upload_file (UploadFile): Загружаемый файл из multipart-запроса.

        Returns:
            StoredFile: Созданная запись файла.

        Raises:
            HTTPException: 400, если файл пустой.
        """
        chunk_size = 1024 * 1024  # 1 MB
        size = 0
        safe_original_name = sanitize_filename(upload_file.filename or "unnamed")
        file_id = str(uuid4())
        suffix = Path(safe_original_name).suffix
        # Файл на диске хранится под id, а не под оригинальным именем —
        # исключает коллизии имён и path traversal при записи.
        stored_name = f"{file_id}{suffix}"
        stored_path = settings.storage_dir / stored_name
        with stored_path.open("wb") as f:
            while chunk := await upload_file.read(chunk_size):
                size += len(chunk)
                await asyncio.to_thread(f.write, chunk)

        if size == 0:
            stored_path.unlink()
            raise EmptyFileError("Uploaded file is empty")

        file_item = await self.uow.files.create(
            id=file_id,
            title=title,
            original_name=safe_original_name,
            stored_name=stored_name,
            mime_type=upload_file.content_type or mimetypes.guess_type(stored_name)[0] or "application/octet-stream",
            size=size,
            processing_status="uploaded",
        )

        await self.uow.commit()

        if self.task_dispatcher:
            self.task_dispatcher(file_item.id)

        return file_item

    async def update_file(self, file_id: str, title: str) -> StoredFile:
        """Обновляет название файла.

        Args:
            file_id (str): Идентификатор файла.
            title (str): Новое название.

        Returns:
            StoredFile: Обновлённая запись файла.

        Raises:
            HTTPException: 404, если файл не найден.
        """
        file_item = await self.get_file(file_id)
        return await self.uow.files.update(file_item, title=title)

    async def delete_file(self, file_id: str) -> None:
        """Удаляет файл с диска (если присутствует) и запись из БД.

        Порядок важен: сначала коммитим удаление из БД, потом удаляем
        физический файл. Если что-то пойдёт не так между ними, на диске
        может остаться файл-сирота без записи в БД — это не страшно
        (не влияет на работу API). Обратный порядок опаснее: он может
        оставить в БД запись без файла на диске, из-за чего download
        такого файла начнёт падать.

        Args:
            file_id (str): Идентификатор файла.

        Returns:
            None

        Raises:
            HTTPException: 404, если файл не найден.
        """
        file_item = await self.get_file(file_id)
        stored_path = settings.storage_dir / file_item.stored_name
        alerts = await self.uow.alerts.get_multi(filters={"file_id": file_id})
        for alert in alerts:
            await self.uow.alerts.delete(alert)
        await self.uow.files.delete(file_item)
        await self.uow.commit()
        if stored_path.exists():
            stored_path.unlink()

class AlertService:
    """Бизнес-логика, связанная с алертами."""

    def __init__(self, uow: UnitOfWork):
        """Инициализирует сервис.

        Args:
            uow (UnitOfWork): Unit of Work текущего запроса (даёт uow.alerts).
        """
        self.uow = uow

    async def list_alerts(self, skip: int = 0, limit: int = 50) -> list[Alert]:
        """Возвращает страницу алертов.

        Args:
            skip (int): Количество записей, пропускаемых от начала выборки.
            limit (int): Максимальное количество записей в ответе.

        Returns:
            list[Alert]: Список алертов текущей страницы.
        """
        return await self.uow.alerts.get_multi(skip=skip, limit=limit)