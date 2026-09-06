"""Unit-тесты Celery-таска обработки файла (_process_file).
UnitOfWork заменяется на асинхронный контекстный менеджер-заглушку,
оборачивающий тот же mock_uow — таск работает с моками repositories,
без реальной БД. Файловая система подменяется через tmp_path.
"""
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import StoredFile
from app.tasks import PROCESSING_TIMEOUT, _load_file_snapshot, _process_file


@pytest.fixture
def patch_uow(monkeypatch, mock_uow):
    """Подменяет UnitOfWork в app.tasks на асинхронный контекстный менеджер над mock_uow.
    Args:
        monkeypatch: Стандартная фикстура pytest для подмены атрибутов.
        mock_uow: Мок UnitOfWork из conftest.py.
    Returns:
        MagicMock: Тот же mock_uow, для использования и настройки в тесте.
    """
    import app.tasks as tasks_module

    @asynccontextmanager
    async def fake_uow_context(*args, **kwargs):
        yield mock_uow

    monkeypatch.setattr(tasks_module, "UnitOfWork", fake_uow_context)
    return mock_uow


class TestProcessFile:
    """Тесты _process_file."""

    async def test_returns_early_when_file_not_found(self, patch_uow):
        """Если файл не найден, обработка прекращается без создания алерта."""
        patch_uow.files.get_by_id_for_update.return_value = None

        await _process_file("missing", "task-1")

        patch_uow.alerts.create.assert_not_called()

    async def test_marks_clean_file_as_processed(self, patch_uow, tmp_path, monkeypatch):
        """Обычный текстовый файл без подозрительных признаков помечается как чистый."""
        import app.tasks as tasks_module

        monkeypatch.setattr(tasks_module.settings, "storage_dir", tmp_path)
        stored_path = tmp_path / "report.txt"
        stored_path.write_text("line one\nline two\n")

        file_item = StoredFile(
            id="1",
            original_name="report.txt",
            stored_name="report.txt",
            mime_type="text/plain",
            size=stored_path.stat().st_size,
        )
        patch_uow.files.get_by_id_for_update.return_value = file_item
        patch_uow.files.get_by_id.return_value = file_item

        await _process_file("1", "task-1")

        assert file_item.scan_status == "clean"
        assert file_item.requires_attention is False
        assert file_item.processing_status == "processed"
        assert file_item.metadata_json["line_count"] == 2
        patch_uow.alerts.create.assert_awaited_once()
        _, kwargs = patch_uow.alerts.create.call_args
        assert kwargs["level"] == "info"

    async def test_flags_suspicious_extension(self, patch_uow, tmp_path, monkeypatch):
        """Файл с подозрительным расширением помечается requires_attention=True."""
        import app.tasks as tasks_module

        monkeypatch.setattr(tasks_module.settings, "storage_dir", tmp_path)
        stored_path = tmp_path / "script.sh"
        stored_path.write_bytes(b"#!/bin/sh\necho hi\n")

        file_item = StoredFile(
            id="2",
            original_name="script.sh",
            stored_name="script.sh",
            mime_type="text/plain",
            size=stored_path.stat().st_size,
        )
        patch_uow.files.get_by_id_for_update.return_value = file_item
        patch_uow.files.get_by_id.return_value = file_item

        await _process_file("2", "task-2")

        assert file_item.scan_status == "suspicious"
        assert file_item.requires_attention is True
        assert "suspicious extension .sh" in file_item.scan_details
        _, kwargs = patch_uow.alerts.create.call_args
        assert kwargs["level"] == "warning"

    async def test_flags_oversized_file(self, patch_uow, tmp_path, monkeypatch):
        """Файл больше 10 МБ помечается как подозрительный по размеру."""
        import app.tasks as tasks_module

        monkeypatch.setattr(tasks_module.settings, "storage_dir", tmp_path)
        stored_path = tmp_path / "big.txt"
        stored_path.write_text("x")

        file_item = StoredFile(
            id="3",
            original_name="big.txt",
            stored_name="big.txt",
            mime_type="text/plain",
            size=11 * 1024 * 1024,  # больше лимита, реальный файл маленький — размер берём из записи БД
        )
        patch_uow.files.get_by_id_for_update.return_value = file_item
        patch_uow.files.get_by_id.return_value = file_item

        await _process_file("3", "task-3")

        assert "file is larger than 10 MB" in file_item.scan_details
        assert file_item.requires_attention is True

    async def test_marks_failed_when_stored_file_missing(self, patch_uow, tmp_path, monkeypatch):
        """Если физический файл отсутствует на диске, статус становится failed и алерт critical."""
        import app.tasks as tasks_module

        monkeypatch.setattr(tasks_module.settings, "storage_dir", tmp_path)

        file_item = StoredFile(
            id="4",
            original_name="ghost.txt",
            stored_name="ghost.txt",  # файла в tmp_path нет
            mime_type="text/plain",
            size=10,
        )
        patch_uow.files.get_by_id_for_update.return_value = file_item
        patch_uow.files.get_by_id.return_value = file_item

        await _process_file("4", "task-4")

        assert file_item.processing_status == "failed"
        _, kwargs = patch_uow.alerts.create.call_args
        assert kwargs["level"] == "critical"

    async def test_extracts_pdf_page_count(self, patch_uow, tmp_path, monkeypatch):
        """Для PDF извлекается приблизительное количество страниц по маркерам /Type /Page."""
        import app.tasks as tasks_module

        monkeypatch.setattr(tasks_module.settings, "storage_dir", tmp_path)
        stored_path = tmp_path / "doc.pdf"
        stored_path.write_bytes(b"%PDF-1.4\n/Type /Page\n/Type /Page\n")

        file_item = StoredFile(
            id="5",
            original_name="doc.pdf",
            stored_name="doc.pdf",
            mime_type="application/pdf",
            size=stored_path.stat().st_size,
        )
        patch_uow.files.get_by_id_for_update.return_value = file_item
        patch_uow.files.get_by_id.return_value = file_item

        await _process_file("5", "task-5")

        assert file_item.metadata_json["approx_page_count"] == 2


class TestProcessingRecovery:
    """Тесты recovery зависшего processing (_load_file_snapshot)."""

    async def test_fresh_processing_by_other_task_is_skipped(self, patch_uow):
        """Файл, обрабатываемый прямо сейчас ДРУГИМ таском (processing моложе таймаута), пропускается."""
        file_item = StoredFile(
            id="10",
            original_name="a.txt",
            stored_name="a.txt",
            mime_type="text/plain",
            size=10,
            processing_status="processing",
            processing_started_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            processing_task_id="task-owner",
        )
        patch_uow.files.get_by_id_for_update.return_value = file_item

        result = await _load_file_snapshot("10", "task-other")

        assert result is None
        patch_uow.commit.assert_not_called()

    async def test_stale_processing_is_retried(self, patch_uow):
        """Файл, зависший в processing дольше таймаута, обрабатывается заново другим таском."""
        file_item = StoredFile(
            id="11",
            original_name="b.txt",
            stored_name="b.txt",
            mime_type="text/plain",
            size=10,
            processing_status="processing",
            processing_started_at=datetime.now(timezone.utc) - PROCESSING_TIMEOUT - timedelta(minutes=1),
            processing_task_id="task-dead",
        )
        patch_uow.files.get_by_id_for_update.return_value = file_item

        result = await _load_file_snapshot("11", "task-new")

        assert result == ("b.txt", "b.txt", 10, "text/plain")
        assert file_item.processing_status == "processing"
        assert file_item.processing_started_at is not None
        assert file_item.processing_task_id == "task-new"
        patch_uow.commit.assert_awaited_once()

    async def test_processing_without_started_at_is_retried(self, patch_uow):
        """Файл в processing без метки времени (legacy-запись) считается зависшим и обрабатывается заново."""
        file_item = StoredFile(
            id="12",
            original_name="c.txt",
            stored_name="c.txt",
            mime_type="text/plain",
            size=10,
            processing_status="processing",
            processing_started_at=None,
            processing_task_id="task-old",
        )
        patch_uow.files.get_by_id_for_update.return_value = file_item

        result = await _load_file_snapshot("12", "task-new")

        assert result == ("c.txt", "c.txt", 10, "text/plain")
        assert file_item.processing_started_at is not None

    async def test_concurrent_worker_does_not_reprocess_freshly_claimed_file(self, patch_uow):
        """Второй worker (другой task_id), увидевший файл сразу после claim первым, не берёт файл повторно."""
        file_item = StoredFile(
            id="13",
            original_name="d.txt",
            stored_name="d.txt",
            mime_type="text/plain",
            size=10,
            processing_status="uploaded",
        )
        patch_uow.files.get_by_id_for_update.return_value = file_item

        first_result = await _load_file_snapshot("13", "task-a")
        assert first_result is not None
        assert file_item.processing_status == "processing"
        assert file_item.processing_task_id == "task-a"

        second_result = await _load_file_snapshot("13", "task-b")
        assert second_result is None

    async def test_same_task_redelivery_continues_processing(self, patch_uow):
        """Redelivery ТОГО ЖЕ task_id (worker умер, Celery вернул задачу) продолжает обработку, а не пропускает."""
        file_item = StoredFile(
            id="14",
            original_name="e.txt",
            stored_name="e.txt",
            mime_type="text/plain",
            size=10,
            processing_status="processing",
            processing_started_at=datetime.now(timezone.utc) - timedelta(seconds=5),
            processing_task_id="task-same",
        )
        patch_uow.files.get_by_id_for_update.return_value = file_item

        result = await _load_file_snapshot("14", "task-same")

        assert result == ("e.txt", "e.txt", 10, "text/plain")
        patch_uow.commit.assert_awaited_once()