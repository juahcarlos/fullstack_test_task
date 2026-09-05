"""Repository-слой.

BaseRepository — обобщённый CRUD поверх произвольной модели (bound=Base),
устраняет дублирование одинаковых операций (get/list/create/update/delete)
между репозиториями разных моделей. Сам commit/rollback сюда не входит —
этим управляет UnitOfWork (core/uow.py); здесь только flush().
FileRepository/AlertRepository — тонкие подклассы под конкретные модели,
с местом для специфичных запросов, если они появятся.
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, Base, StoredFile

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Базовый репозиторий с общими CRUD-операциями для всех моделей."""

    def __init__(self, model: type[ModelType], session: AsyncSession) -> None:
        """Инициализирует репозиторий.

        Args:
            model (type[ModelType]): ORM-модель, с которой работает репозиторий.
            session (AsyncSession): Сессия SQLAlchemy, привязанная к текущей транзакции.
        """
        self.model = model
        self.session = session

    async def get_by_id(self, id: Any) -> ModelType | None:
        """Возвращает запись по первичному ключу.

        Args:
            id (Any): Значение первичного ключа.

        Returns:
            ModelType | None: Найденная запись или None.
        """
        result = await self.session.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
    ) -> list[ModelType]:
        """Возвращает страницу записей с пагинацией и необязательными фильтрами.

        Args:
            skip (int): Количество записей, пропускаемых от начала выборки.
            limit (int): Максимальное количество записей в ответе.
            filters (dict[str, Any] | None): Пары поле-значение для точного фильтра (равенство).

        Returns:
            list[ModelType]: Список записей текущей страницы.
        """
        query = select(self.model)
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key) and value is not None:
                    query = query.where(getattr(self.model, key) == value)
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Считает количество записей, удовлетворяющих фильтрам.

        Args:
            filters (dict[str, Any] | None): Пары поле-значение для точного фильтра (равенство).

        Returns:
            int: Количество подходящих записей.
        """
        query = select(func.count()).select_from(self.model)
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key) and value is not None:
                    query = query.where(getattr(self.model, key) == value)
        result = await self.session.execute(query)
        return result.scalar_one()

    async def create(self, **data: Any) -> ModelType:
        """Создаёт новую запись.

        Args:
            **data (Any): Поля создаваемой записи.

        Returns:
            ModelType: Созданная запись (после flush и refresh).
        """
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, instance: ModelType, **data: Any) -> ModelType:
        """Обновляет существующую запись.

        Args:
            instance (ModelType): Запись, подлежащая обновлению.
            **data (Any): Поля для изменения.

        Returns:
            ModelType: Обновлённая запись (после flush и refresh).
        """
        for key, value in data.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelType) -> None:
        """Удаляет запись.

        Args:
            instance (ModelType): Запись, подлежащая удалению.

        Returns:
            None
        """
        await self.session.delete(instance)
        await self.session.flush()

    async def exists(self, **filters: Any) -> bool:
        """Проверяет наличие хотя бы одной записи, удовлетворяющей фильтрам.

        Args:
            **filters (Any): Пары поле-значение для точного фильтра (равенство).

        Returns:
            bool: True, если запись найдена.
        """
        query = select(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.where(getattr(self.model, key) == value)
        result = await self.session.execute(query.limit(1))
        return result.scalar_one_or_none() is not None


class FileRepository(BaseRepository[StoredFile]):
    """Репозиторий для StoredFile — место для специфичных запросов, если появятся."""

    def __init__(self, session: AsyncSession) -> None:
        """Инициализирует репозиторий файлов.

        Args:
            session (AsyncSession): Сессия SQLAlchemy, привязанная к текущей транзакции.
        """
        super().__init__(StoredFile, session)


class AlertRepository(BaseRepository[Alert]):
    """Репозиторий для Alert — место для специфичных запросов, если появятся."""

    def __init__(self, session: AsyncSession) -> None:
        """Инициализирует репозиторий алертов.

        Args:
            session (AsyncSession): Сессия SQLAlchemy, привязанная к текущей транзакции.
        """
        super().__init__(Alert, session)