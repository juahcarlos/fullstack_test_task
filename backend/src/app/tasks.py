"""Celery-таск обработки файла.

Исходно проверка на угрозы, извлечение метаданных и создание алерта были
тремя отдельными Celery-тасками, вызывающими друг друга через .delay() —
это три отдельных похода в очередь Redis и три отдельные транзакции БД
на один загруженный файл. Здесь это объединено в один таск с одной
транзакцией через UnitOfWork — сама оптимизация, требуемая доп. пунктом ТЗ.
"""

import asyncio
from pathlib import Path

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.database import async_session_maker
from app.core.uow import UnitOfWork

settings = get_settings()

# Celery-воркер синхронный, поэтому для вызова async-кода (SQLAlchemy async)
# используется отдельный, переиспользуемый event loop.
_worker_loop: asyncio.AbstractEventLoop | None = None


def run_in_worker_loop(coroutine):
    """Выполняет переданную корутину в выделенном для воркера event loop'е.

    Args:
        coroutine (Coroutine): Корутина, которую нужно выполнить синхронно
            в контексте Celery-таска.

    Returns:
        Any: Результат выполнения корутины.
    """
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop.run_until_complete(coroutine)


async def _process_file(file_id: str) -> None:
    """Выполняет полный цикл обработки файла: скан -> метаданные -> алерт, одной транзакцией.

    Args:
        file_id (str): Идентификатор файла, подлежащего обработке.

    Returns:
        None
    """
    async with UnitOfWork(async_session_maker) as uow:
        file_item = await uow.files.get_by_id(file_id)
        if not file_item:
            return

        file_item.processing_status = "processing"

        # --- Проверка на подозрительный контент ---
        reasons: list[str] = []
        extension = Path(file_item.original_name).suffix.lower()

        if extension in {".exe", ".bat", ".cmd", ".sh", ".js"}:
            reasons.append(f"suspicious extension {extension}")
        if file_item.size > 10 * 1024 * 1024:
            reasons.append("file is larger than 10 MB")
        if extension == ".pdf" and file_item.mime_type not in {"application/pdf", "application/octet-stream"}:
            reasons.append("pdf extension does not match mime type")

        file_item.scan_status = "suspicious" if reasons else "clean"
        file_item.scan_details = ", ".join(reasons) if reasons else "no threats found"
        file_item.requires_attention = bool(reasons)

        # --- Извлечение метаданных ---
        stored_path = settings.storage_dir / file_item.stored_name
        if not stored_path.exists():
            file_item.processing_status = "failed"
            file_item.scan_status = file_item.scan_status or "failed"
            file_item.scan_details = "stored file not found during metadata extraction"
        else:
            metadata = {
                "extension": extension,
                "size_bytes": file_item.size,
                "mime_type": file_item.mime_type,
            }

            if file_item.mime_type.startswith("text/"):
                # Построчное чтение вместо загрузки всего файла в память целиком.
                line_count = 0
                char_count = 0
                with stored_path.open("r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line_count += 1
                        char_count += len(line)
                metadata["line_count"] = line_count
                metadata["char_count"] = char_count
            elif file_item.mime_type == "application/pdf":
                # Чтение чанками вместо read() всего файла разом.
                page_count = 0
                with stored_path.open("rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        page_count += chunk.count(b"/Type /Page")
                metadata["approx_page_count"] = max(page_count, 1)

            file_item.metadata_json = metadata
            file_item.processing_status = "processed"

        # Промежуточный flush, чтобы алерт ниже создавался в рамках той же
        # транзакции и видел актуальное состояние file_item без отдельного commit.
        await uow.session.flush()

        # --- Создание алерта по итогу обработки ---
        if file_item.processing_status == "failed":
            level, message = "critical", "File processing failed"
        elif file_item.requires_attention:
            level, message = "warning", f"File requires attention: {file_item.scan_details}"
        else:
            level, message = "info", "File processed successfully"

        await uow.alerts.create(file_id=file_id, level=level, message=message)
        # Commit всей транзакции целиком происходит в UnitOfWork.__aexit__.


@celery_app.task
def process_file(file_id: str) -> None:
    """Точка входа Celery-таска — синхронно запускает асинхронную обработку файла.

    Args:
        file_id (str): Идентификатор файла, переданный при постановке задачи в очередь.

    Returns:
        None
    """
    run_in_worker_loop(_process_file(file_id))