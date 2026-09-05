"""Unit-тесты AlertService.

Репозиторий alerts замокирован (см. conftest.py) — тест проверяет,
что сервис корректно делегирует вызов в репозиторий с нужными параметрами.
"""

from app.models import Alert
from app.services import AlertService


class TestAlertServiceListAlerts:
    """Тесты AlertService.list_alerts."""

    async def test_returns_alerts_from_repository(self, mock_uow):
        """Сервис возвращает то, что вернул репозиторий, без изменений."""
        expected = [
            Alert(id=1, file_id="a", level="info", message="ok"),
            Alert(id=2, file_id="b", level="warning", message="check"),
        ]
        mock_uow.alerts.get_multi.return_value = expected

        service = AlertService(uow=mock_uow)
        result = await service.list_alerts()

        assert result == expected

    async def test_passes_skip_and_limit_to_repository(self, mock_uow):
        """Параметры пагинации передаются в репозиторий без изменений."""
        mock_uow.alerts.get_multi.return_value = []

        service = AlertService(uow=mock_uow)
        await service.list_alerts(skip=10, limit=25)

        mock_uow.alerts.get_multi.assert_awaited_once_with(skip=10, limit=25)

    async def test_default_pagination_values(self, mock_uow):
        """При отсутствии явных skip/limit используются значения по умолчанию сервиса."""
        mock_uow.alerts.get_multi.return_value = []

        service = AlertService(uow=mock_uow)
        await service.list_alerts()

        mock_uow.alerts.get_multi.assert_awaited_once_with(skip=0, limit=50)