"""Фоновая обработка уже загруженного файла (Celery-таск).

Сам файл к этому моменту уже принят и сохранён на диск через API (см.
services.py, FileService.create_file) — этот модуль занимается не загрузкой файла, а обрабатывает то, что уже
лежит на диске: проверяет на подозрительность и извлекает информацию
о содержимом, чтобы показать статус на фронте и создать алерт.

Раньше это были 3 отдельных Celery-таска (скан → метаданные → алерт),
каждый со своей транзакцией БД, вызывающих друг друга через .delay() —
3 похода в очередь Redis и 3 коммита на файл. Здесь один таск с двумя
короткими транзакциями через UnitOfWork: одна читает данные файла в
начале, другая сохраняет результат в конце. Само чтение файла с диска
происходит между ними, без открытой транзакции БД.
"""

import asyncio
from pathlib import Path

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.database import async_session_maker
from app.core.uow import UnitOfWork

settings = get_settings()


# asyncpg-соединения привязаны к event loop, в котором были созданы, а
# engine/пул соединений (async_session_maker) общий на весь процесс воркера
# и живёт дольше одного таска. asyncio.run() создавал бы новый loop на
# каждый вызов — из пула доставалось бы соединение из "чужого" loop, и
# asyncpg падал с InterfaceError. Поэтому здесь один переиспользуемый loop
# на весь воркер, а не asyncio.run() на каждый вызов.
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


def _scan_for_threats(original_name: str, size: int, mime_type: str) -> tuple[str, str, bool]:
    """Проверяет файл на признаки подозрительности по его метаданным (без чтения содержимого).

    Args:
        original_name (str): Оригинальное имя файла.
        size (int): Размер файла в байтах.
        mime_type (str): MIME-тип файла.

    Returns:
        tuple[str, str, bool]: (scan_status, scan_details, requires_attention).
    """
    reasons: list[str] = []
    extension = Path(original_name).suffix.lower()

    # опасное расширение файла
    if extension in {".exe", ".bat", ".cmd", ".sh", ".js"}:
        reasons.append(f"suspicious extension {extension}")

    # слишком большой файл
    if size > 10 * 1024 * 1024:
        reasons.append("file is larger than 10 MB")

    # расширение не совпадает с заявленным mime-типом
    if extension == ".pdf" and mime_type not in {"application/pdf", "application/octet-stream"}:
        reasons.append("pdf extension does not match mime type")

    scan_status = "suspicious" if reasons else "clean"
    scan_details = ", ".join(reasons) if reasons else "no threats found"
    return scan_status, scan_details, bool(reasons)


def _extract_metadata(stored_path: Path, mime_type: str) -> dict:
    """Читает файл с диска и собирает метаданные (тип, размер, для текста/PDF — доп. поля).

    Args:
        stored_path (Path): Путь к физическому файлу на диске.
        mime_type (str): MIME-тип файла.

    Returns:
        dict: Собранные метаданные файла.
    """
    metadata = {
        "extension": stored_path.suffix.lower(),
        "size_bytes": stored_path.stat().st_size,
        "mime_type": mime_type,
    }

    if mime_type.startswith("text/"):
        # построчное чтение, а не весь файл разом — экономим память
        line_count = 0
        char_count = 0
        with stored_path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_count += 1
                char_count += len(line)
        metadata["line_count"] = line_count
        metadata["char_count"] = char_count
    elif mime_type == "application/pdf":
        # грубая оценка числа страниц по маркеру в бинарнике, чанками по 64 КБ
        page_count = 0
        with stored_path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                page_count += chunk.count(b"/Type /Page")
        metadata["approx_page_count"] = max(page_count, 1)

    return metadata


def _build_alert(processing_status: str, requires_attention: bool, scan_details: str) -> tuple[str, str]:
    """Определяет уровень и текст алерта по итогу обработки файла.

    Args:
        processing_status (str): Итоговый статус обработки файла.
        requires_attention (bool): Требует ли файл внимания по итогам скана.
        scan_details (str): Пояснение по итогам скана.

    Returns:
        tuple[str, str]: (level, message).
    """
    if processing_status == "failed":
        return "critical", "File processing failed"
    if requires_attention:
        return "warning", f"File requires attention: {scan_details}"
    return "info", "File processed successfully"


async def _load_file_snapshot(file_id: str) -> tuple[str, str, int, str] | None:
    """Читает исходные поля файла и переводит его в статус processing.

    Короткая транзакция: сразу коммитит, чтобы не держать БД открытой
    во время последующего чтения файла с диска.

    Args:
        file_id (str): Идентификатор файла.

    Returns:
        tuple[str, str, int, str] | None: (original_name, stored_name, size, mime_type)
            или None, если файл не найден (например, удалили, пока таск ждал в очереди).
    """
    async with UnitOfWork(async_session_maker) as uow:
        file_item = await uow.files.get_by_id_for_update(file_id)
        if not file_item:
            return None
        if file_item.processing_status in {"processed", "failed"}:
            return None  # уже обработан — повторный запуск таска ничего не делает
        file_item.processing_status = "processing"
        await uow.commit()
        return file_item.original_name, file_item.stored_name, file_item.size, file_item.mime_type


async def _save_processing_result(
    file_id: str,
    scan_status: str,
    scan_details: str,
    requires_attention: bool,
    processing_status: str,
    metadata: dict | None,
) -> None:
    """Сохраняет итог обработки файла и создаёт алерт, одной короткой транзакцией.

    Args:
        file_id (str): Идентификатор файла.
        scan_status (str): Итоговый статус скана ("clean"/"suspicious"/"failed").
        scan_details (str): Пояснение по итогам скана.
        requires_attention (bool): Требует ли файл внимания.
        processing_status (str): Итоговый статус обработки ("processed"/"failed").
        metadata (dict | None): Собранные метаданные файла, если обработка дошла до этого шага.

    Returns:
        None
    """
    async with UnitOfWork(async_session_maker) as uow:
        file_item = await uow.files.get_by_id(file_id)
        if not file_item:
            return  # файл удалили, пока шла обработка

        file_item.scan_status = scan_status
        file_item.scan_details = scan_details
        file_item.requires_attention = requires_attention
        file_item.processing_status = processing_status
        if metadata is not None:
            file_item.metadata_json = metadata

        await uow.session.flush()  # чтобы алерт ниже видел актуальный file_item

        level, message = _build_alert(processing_status, requires_attention, scan_details)
        await uow.alerts.create(file_id=file_id, level=level, message=message)


async def _process_file(file_id: str) -> None:
    """Выполняет полный цикл обработки файла: скан -> метаданные -> алерт.

    Три шага: короткая транзакция читает данные файла (_load_file_snapshot),
    затем без БД идут скан по метаданным и чтение файла с диска, в конце
    вторая короткая транзакция сохраняет результат и создаёт алерт
    (_save_processing_result).

    Args:
        file_id (str): Идентификатор файла, подлежащего обработке.

    Returns:
        None
    """
    snapshot = await _load_file_snapshot(file_id)
    if snapshot is None:
        return
    original_name, stored_name, size, mime_type = snapshot

    scan_status, scan_details, requires_attention = _scan_for_threats(original_name, size, mime_type)

    stored_path = settings.storage_dir / stored_name
    metadata = None
    processing_status = "processed"

    if not stored_path.exists():
        # файл пропал с диска между загрузкой и обработкой
        processing_status = "failed"
        scan_status = scan_status or "failed"
        scan_details = "stored file not found during metadata extraction"
    else:
        try:
            metadata = _extract_metadata(stored_path, mime_type)
        except OSError as e:
            # файл есть, но прочитать не вышло (права, диск и т.п.) — тоже сбой
            metadata = None
            processing_status = "failed"
            scan_status = scan_status or "failed"
            scan_details = f"metadata extraction failed: {e}"

    await _save_processing_result(file_id, scan_status, scan_details, requires_attention, processing_status, metadata)


@celery_app.task
def process_file(file_id: str) -> None:
    """Точка входа Celery-таска — синхронно запускает асинхронную обработку файла.

    Args:
        file_id (str): Идентификатор файла, переданный при постановке задачи в очередь.

    Returns:
        None
    """
    run_in_worker_loop(_process_file(file_id))