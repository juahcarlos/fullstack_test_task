"""HTTP-роуты для алертов (уведомлений о результатах обработки файлов)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.dependencies import AlertServiceDep
from app.schemas import AlertItem

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertItem])
async def list_alerts_view(
    service: AlertServiceDep,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Возвращает список алертов, отсортированный по дате создания (новые первыми)."""
    return await service.list_alerts(skip=skip, limit=limit)