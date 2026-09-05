"""Unit-тесты Celery-таска обработки файла (_process_file).

UnitOfWork заменяется на асинхронный контекстный менеджер-заглушку,
оборачивающий тот же mock_uow — таск работает с моками repositories,
без реальной БД. Файловая система подменяется через tmp_path.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import StoredFile
from app.tasks import _process_file


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
        patch_uow.files.get_by_id.return_value = None

        await _process_file("missing")

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
        patch_uow.files.get_by_id.return_value = file_item

        await _process_file("1")

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
        patch_uow.files.get_by_id.return_value = file_item

        await _process_file("2")

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
        patch_uow.files.get_by_id.return_value = file_item

        await _process_file("3")

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
        patch_uow.files.get_by_id.return_value = file_item

        await _process_file("4")

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
        patch_uow.files.get_by_id.return_value = file_item

        await _process_file("5")

        assert file_item.metadata_json["approx_page_count"] == 2