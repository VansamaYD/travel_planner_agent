from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SqlAlchemyUnitOfWork:
    """One short transaction per command handler.

    Repositories will be constructed from the private session as domain slices are added.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._committed = False

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("UnitOfWork has not been entered")
        return self._session

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        self._session = self._session_factory()
        self._committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None or not self._committed:
            await self._session.rollback()
        await self._session.close()
        self._session = None

    async def commit(self) -> None:
        await self.session.commit()
        self._committed = True

    async def rollback(self) -> None:
        await self.session.rollback()
        self._committed = False
