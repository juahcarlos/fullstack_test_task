"""Unit-тесты FileService.

Репозитории и task_dispatcher замокированы (см. conftest.py) — тесты
проверяют бизнес-логику сервиса изолированно, без реальной БД и диска.
Работа с файловой системой (write_bytes/unlink/exists) мокается через
monkeypatch на уровне settings.storage_dir и Path-методов.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, UploadFile

from app.models import StoredFile
from app.services import FileService, sanitize_filename


def make_upload_file(filename: str, content: bytes, content_type: str = "text/plain") -> UploadFile:
    """Собирает объект UploadFile с заданным содержимым для теста.

    Args:
        filename (str): Имя файла, как если бы его прислал клиент.
        content (bytes): Содержимое файла.
        content_type (str): MIME-тип файла.

    Returns:
        UploadFile: Готовый к использованию в сервисе объект.
    """
    from io import BytesIO

    upload = UploadFile(filename=filename, file=BytesIO(content))
    upload.headers = {"content-type": content_type}
    return upload


class TestSanitizeFilename:
    """Тесты функции sanitize_filename."""

    def test_removes_path_components(self):
        """Компоненты пути должны отбрасываться, остаётся только имя файла."""
        assert sanitize_filename("../../etc/passwd") == "passwd"

    def test_replaces_unsafe_characters(self):
        """Недопустимые символы заменяются на подчёркивание."""
        assert sanitize_filename("my file!@#.txt") == "my_file_.txt"

    def test_empty_name_falls_back_to_unnamed(self):
        """Пустое после очистки имя заменяется на 'unnamed'."""
        assert sanitize_filename("///") == "unnamed"


class TestFileServiceGetFile:
    """Тесты FileService.get_file."""

    async def test_returns_file_when_found(self, mock_uow):
        """Если файл найден в репозитории, сервис возвращает его как есть."""
        expected = StoredFile(id="123", title="doc")
        mock_uow.files.get_by_id.return_value = expected

        service = FileService(uow=mock_uow)
        result = await service.get_file("123")

        assert result is expected
        mock_uow.files.get_by_id.assert_awaited_once_with("123")

    async def test_raises_404_when_not_found(self, mock_uow):
        """Если файл не найден, сервис бросает HTTPException 404."""
        mock_uow.files.get_by_id.return_value = None

        service = FileService(uow=mock_uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_file("missing")

        assert exc_info.value.status_code == 404


class TestFileServiceCreateFile:
    """Тесты FileService.create_file."""

    async def test_raises_400_on_empty_file(self, mock_uow):
        """Пустой файл должен приводить к ошибке 400, без похода в репозиторий."""
        upload = make_upload_file("empty.txt", b"")
        service = FileService(uow=mock_uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_file(title="Empty", upload_file=upload)

        assert exc_info.value.status_code == 400
        mock_uow.files.create.assert_not_called()

    async def test_raises_413_when_exceeds_max_size(self, mock_uow, monkeypatch):
        """Файл больше max_upload_size должен приводить к ошибке 413."""
        import app.services as services_module

        monkeypatch.setattr(services_module.settings, "max_upload_size", 5)
        upload = make_upload_file("big.txt", b"123456")
        service = FileService(uow=mock_uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_file(title="Big", upload_file=upload)

        assert exc_info.value.status_code == 413
        mock_uow.files.create.assert_not_called()

    async def test_creates_file_and_dispatches_task(self, mock_uow, mock_task_dispatcher, tmp_path, monkeypatch):
        """Успешная загрузка: файл пишется на диск, запись создаётся, таск ставится в очередь."""
        import app.services as services_module

        monkeypatch.setattr(services_module.settings, "storage_dir", tmp_path)
        monkeypatch.setattr(services_module.settings, "max_upload_size", 10 * 1024 * 1024)

        created = StoredFile(id="abc", title="Report", original_name="report.txt")
        mock_uow.files.create.return_value = created

        upload = make_upload_file("report.txt", b"hello world", content_type="text/plain")
        service = FileService(uow=mock_uow, task_dispatcher=mock_task_dispatcher)

        result = await service.create_file(title="Report", upload_file=upload)

        assert result is created
        mock_uow.files.create.assert_awaited_once()
        mock_task_dispatcher.assert_called_once_with("abc")

        stored_files = list(tmp_path.iterdir())
        assert len(stored_files) == 1
        assert stored_files[0].read_bytes() == b"hello world"

    async def test_does_not_dispatch_task_when_dispatcher_is_none(self, mock_uow, tmp_path, monkeypatch):
        """Если task_dispatcher не передан, задача не ставится в очередь (не падает)."""
        import app.services as services_module

        monkeypatch.setattr(services_module.settings, "storage_dir", tmp_path)
        monkeypatch.setattr(services_module.settings, "max_upload_size", 10 * 1024 * 1024)

        mock_uow.files.create.return_value = StoredFile(id="xyz", title="No dispatcher")

        upload = make_upload_file("f.txt", b"content")
        service = FileService(uow=mock_uow, task_dispatcher=None)

        result = await service.create_file(title="No dispatcher", upload_file=upload)

        assert result.id == "xyz"


class TestFileServiceUpdateFile:
    """Тесты FileService.update_file."""

    async def test_updates_title(self, mock_uow):
        """Название файла обновляется через репозиторий."""
        existing = StoredFile(id="1", title="Old")
        updated = StoredFile(id="1", title="New")
        mock_uow.files.get_by_id.return_value = existing
        mock_uow.files.update.return_value = updated

        service = FileService(uow=mock_uow)
        result = await service.update_file(file_id="1", title="New")

        assert result is updated
        mock_uow.files.update.assert_awaited_once_with(existing, title="New")

    async def test_raises_404_when_file_missing(self, mock_uow):
        """Обновление несуществующего файла бросает 404."""
        mock_uow.files.get_by_id.return_value = None
        service = FileService(uow=mock_uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.update_file(file_id="missing", title="New")

        assert exc_info.value.status_code == 404


class TestFileServiceDeleteFile:
    """Тесты FileService.delete_file."""

    async def test_deletes_file_and_stored_data(self, mock_uow, tmp_path, monkeypatch):
        """Удаление файла: физический файл удаляется с диска, запись — из репозитория."""
        import app.services as services_module

        monkeypatch.setattr(services_module.settings, "storage_dir", tmp_path)

        stored_name = "existing.txt"
        (tmp_path / stored_name).write_bytes(b"data")

        file_item = StoredFile(id="1", stored_name=stored_name)
        mock_uow.files.get_by_id.return_value = file_item

        service = FileService(uow=mock_uow)
        await service.delete_file("1")

        assert not (tmp_path / stored_name).exists()
        mock_uow.files.delete.assert_awaited_once_with(file_item)

    async def test_raises_404_when_file_missing(self, mock_uow):
        """Удаление несуществующего файла бросает 404, delete в репозитории не вызывается."""
        mock_uow.files.get_by_id.return_value = None
        service = FileService(uow=mock_uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.delete_file("missing")

        assert exc_info.value.status_code == 404
        mock_uow.files.delete.assert_not_called()