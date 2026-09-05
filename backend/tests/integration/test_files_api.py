"""Integration-тесты API файлов.

Используют реальное HTTP-приложение с тестовыми Postgres/Redis
(testcontainers) и тестовым Celery-воркером (отдельный процесс, см.
conftest.py) — без моков очереди. Ожидание обработки файла воркером —
через wait_for_processing.
"""

import pytest

from helpers import wait_for_processing


class TestListFiles:
    """Тесты GET /files."""

    async def test_returns_empty_list_when_no_files(self, client):
        """На чистой БД список файлов пуст."""
        response = await client.get("/files")

        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_uploaded_files(self, client):
        """После загрузки файл появляется в списке."""
        await client.post(
            "/files",
            data={"title": "Report"},
            files={"file": ("report.txt", b"hello", "text/plain")},
        )

        response = await client.get("/files")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["title"] == "Report"

    async def test_pagination_limit(self, client):
        """limit ограничивает количество записей в ответе."""
        for i in range(3):
            await client.post(
                "/files",
                data={"title": f"File {i}"},
                files={"file": (f"f{i}.txt", b"data", "text/plain")},
            )

        response = await client.get("/files", params={"limit": 2})

        assert response.status_code == 200
        assert len(response.json()) == 2


class TestCreateFile:
    """Тесты POST /files."""

    async def test_creates_file_and_returns_201(self, client):
        """Успешная загрузка возвращает 201 и данные файла со статусом uploaded."""
        response = await client.post(
            "/files",
            data={"title": "New Report"},
            files={"file": ("report.txt", b"hello world", "text/plain")},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["title"] == "New Report"
        assert body["processing_status"] == "uploaded"

    async def test_rejects_empty_file(self, client):
        """Пустой файл отклоняется с 400."""
        response = await client.post(
            "/files",
            data={"title": "Empty"},
            files={"file": ("empty.txt", b"", "text/plain")},
        )

        assert response.status_code == 400

    async def test_worker_processes_file_end_to_end(self, client, session_maker):
        """Файл реально уходит в очередь, воркер его обрабатывает, статус меняется на processed."""
        response = await client.post(
            "/files",
            data={"title": "E2E"},
            files={"file": ("e2e.txt", b"line one\nline two\n", "text/plain")},
        )
        file_id = response.json()["id"]

        processed = await wait_for_processing(session_maker, file_id)

        assert processed.processing_status == "processed"
        assert processed.scan_status == "clean"
        assert processed.metadata_json["line_count"] == 2

    async def test_worker_flags_suspicious_extension(self, client, session_maker):
        """Файл с подозрительным расширением после обработки воркером помечен requires_attention."""
        response = await client.post(
            "/files",
            data={"title": "Suspicious"},
            files={"file": ("script.sh", b"#!/bin/sh\necho hi\n", "text/plain")},
        )
        file_id = response.json()["id"]

        processed = await wait_for_processing(session_maker, file_id)

        assert processed.scan_status == "suspicious"
        assert processed.requires_attention is True


class TestGetFile:
    """Тесты GET /files/{file_id}."""

    async def test_returns_file_by_id(self, client):
        """Существующий файл возвращается по id."""
        create_response = await client.post(
            "/files",
            data={"title": "Doc"},
            files={"file": ("doc.txt", b"content", "text/plain")},
        )
        file_id = create_response.json()["id"]

        response = await client.get(f"/files/{file_id}")

        assert response.status_code == 200
        assert response.json()["id"] == file_id

    async def test_returns_404_for_missing_file(self, client):
        """Несуществующий id даёт 404."""
        response = await client.get("/files/does-not-exist")

        assert response.status_code == 404


class TestUpdateFile:
    """Тесты PATCH /files/{file_id}."""

    async def test_updates_title(self, client):
        """Название файла обновляется через PATCH."""
        create_response = await client.post(
            "/files",
            data={"title": "Old"},
            files={"file": ("f.txt", b"data", "text/plain")},
        )
        file_id = create_response.json()["id"]

        response = await client.patch(f"/files/{file_id}", json={"title": "New"})

        assert response.status_code == 200
        assert response.json()["title"] == "New"

    async def test_returns_404_for_missing_file(self, client):
        """PATCH несуществующего файла даёт 404."""
        response = await client.patch("/files/does-not-exist", json={"title": "New"})

        assert response.status_code == 404


class TestDownloadFile:
    """Тесты GET /files/{file_id}/download."""

    async def test_downloads_file_content(self, client):
        """Скачивание возвращает исходное содержимое файла."""
        create_response = await client.post(
            "/files",
            data={"title": "Download me"},
            files={"file": ("dl.txt", b"exact content", "text/plain")},
        )
        file_id = create_response.json()["id"]

        response = await client.get(f"/files/{file_id}/download")

        assert response.status_code == 200
        assert response.content == b"exact content"

    async def test_returns_404_for_missing_file(self, client):
        """Скачивание несуществующего файла даёт 404."""
        response = await client.get("/files/does-not-exist/download")

        assert response.status_code == 404


class TestDeleteFile:
    """Тесты DELETE /files/{file_id}."""

    async def test_deletes_file(self, client):
        """Удалённый файл возвращает 204 и пропадает из списка."""
        create_response = await client.post(
            "/files",
            data={"title": "To delete"},
            files={"file": ("del.txt", b"data", "text/plain")},
        )
        file_id = create_response.json()["id"]

        response = await client.delete(f"/files/{file_id}")

        assert response.status_code == 204
        get_response = await client.get(f"/files/{file_id}")
        assert get_response.status_code == 404

    async def test_returns_404_for_missing_file(self, client):
        """Удаление несуществующего файла даёт 404."""
        response = await client.delete("/files/does-not-exist")

        assert response.status_code == 404