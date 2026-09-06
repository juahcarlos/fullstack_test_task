"""Repository-слой.
FileRepository/AlertRepository — независимые репозитории с конкретными
методами под свои модели. Никакого generic CRUD — для двух простых
сущностей он был избыточен. Commit/rollback сюда не входит — этим
управляет UnitOfWork (core/uow.py); здесь только flush().
"""
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Alert, StoredFile


class FileRepository:
    """Репозиторий для StoredFile."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id: Any) -> StoredFile | None:
        result = await self.session.execute(select(StoredFile).where(StoredFile.id == id))
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, id: Any) -> StoredFile | None:
        """Возвращает файл по id с блокировкой строки (SELECT ... FOR UPDATE).
        Используется там, где нужна защита от одновременной обработки
        одного и того же файла двумя параллельными запусками Celery-таска.
        """
        result = await self.session.execute(
            select(StoredFile).where(StoredFile.id == id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_multi(self, *, skip: int = 0, limit: int = 100) -> list[StoredFile]:
        query = select(StoredFile).order_by(StoredFile.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        *,
        id: str,
        title: str,
        original_name: str,
        stored_name: str,
        mime_type: str,
        size: int,
        processing_status: str,
    ) -> StoredFile:
        instance = StoredFile(
            id=id,
            title=title,
            original_name=original_name,
            stored_name=stored_name,
            mime_type=mime_type,
            size=size,
            processing_status=processing_status,
        )
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, instance: StoredFile, *, title: str) -> StoredFile:
        instance.title = title
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: StoredFile) -> None:
        await self.session.delete(instance)
        await self.session.flush()


class AlertRepository:
    """Репозиторий для Alert."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_multi(self, *, file_id: str | None = None, skip: int = 0, limit: int | None = 100) -> list[Alert]:
        query = select(Alert).order_by(Alert.created_at.desc())
        if file_id is not None:
            query = query.where(Alert.file_id == file_id)
        query = query.offset(skip)
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, *, file_id: str, level: str, message: str) -> Alert:
        instance = Alert(file_id=file_id, level=level, message=message)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: Alert) -> None:
        await self.session.delete(instance)
        await self.session.flush()