"""Unit of Work — единая точка управления транзакцией.

Инкапсулирует сессию SQLAlchemy и репозитории, работающие с ней.
Коммит и rollback происходят в одном месте (здесь), а не в каждом
репозитории и не в FastAPI-зависимости по отдельности — репозитории
внутри используют только flush(), сами транзакцию не завершают.
"""

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Alert, StoredFile
from app.repositories import BaseRepository


class UnitOfWork:
    """Асинхронный контекстный менеджер над одной транзакцией БД."""

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        """Инициализирует UoW фабрикой сессий.

        Args:
            session_maker (async_sessionmaker[AsyncSession]): Фабрика сессий SQLAlchemy.
        """
        self._session_maker = session_maker
        self.session: AsyncSession | None = None
        self.files: BaseRepository[StoredFile] | None = None
        self.alerts: BaseRepository[Alert] | None = None

    async def __aenter__(self) -> "UnitOfWork":
        """Открывает сессию и инициализирует репозитории на её основе.

        Returns:
            UnitOfWork: Готовый к работе UoW с открытой сессией.
        """
        self.session = self._session_maker()
        self.files = BaseRepository(StoredFile, self.session)
        self.alerts = BaseRepository(Alert, self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Завершает транзакцию: commit при успехе, rollback при исключении.

        Args:
            exc_type (type[BaseException] | None): Тип возникшего исключения, если было.
            exc (BaseException | None): Само исключение, если было.
            tb (TracebackType | None): Traceback исключения, если было.

        Returns:
            None
        """
        assert self.session is not None
        try:
            if exc is None:
                await self.session.commit()
            else:
                await self.session.rollback()
        finally:
            await self.session.close()

    async def commit(self) -> None:
        """Явный коммит текущей транзакции (для операций, требующих промежуточного commit).

        Returns:
            None
        """
        assert self.session is not None
        await self.session.commit()