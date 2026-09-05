"""Integration-тесты API алертов.

Алерты создаются воркером как побочный эффект обработки файла — тест
загружает файл, ждёт обработки (wait_for_processing), затем проверяет
GET /alerts.
"""
import asyncio
import pytest

from helpers import wait_for_processing


class TestListAlerts:
    """Тесты GET /alerts."""

    async def test_returns_empty_list_when_no_alerts(self, client):
        """На чистой БД список алертов пуст."""
        response = await client.get("/alerts")

        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_alert_after_file_processed(self, client, session_maker):
        """После обработки чистого файла появляется info-алерт."""
        create_response = await client.post(
            "/files",
            data={"title": "Clean"},
            files={"file": ("clean.txt", b"just text", "text/plain")},
        )
        file_id = create_response.json()["id"]
        await wait_for_processing(session_maker, file_id)

        response = await client.get("/alerts")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["file_id"] == file_id
        assert body[0]["level"] == "info"

    async def test_returns_warning_alert_for_suspicious_file(self, client, session_maker):
        """После обработки подозрительного файла появляется warning-алерт."""
        create_response = await client.post(
            "/files",
            data={"title": "Bad"},
            files={"file": ("bad.exe", b"binary", "application/octet-stream")},
        )
        file_id = create_response.json()["id"]
        await wait_for_processing(session_maker, file_id)

        response = await client.get("/alerts")

        alerts = [a for a in response.json() if a["file_id"] == file_id]
        assert alerts[0]["level"] == "warning"

    async def test_pagination_limit(self, client, session_maker):
        """limit ограничивает количество записей в ответе."""
        for i in range(3):
            create_response = await client.post(
                "/files",
                data={"title": f"F{i}"},
                files={"file": (f"f{i}.txt", b"data", "text/plain")},
            )
            await wait_for_processing(session_maker, create_response.json()["id"])

        response = await client.get("/alerts", params={"limit": 2})

        assert response.status_code == 200
        assert len(response.json()) == 2