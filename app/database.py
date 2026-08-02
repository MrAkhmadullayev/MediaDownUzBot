from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    def __init__(self, url: str) -> None:
        engine_options: dict[str, object] = {"pool_pre_ping": True}
        if not url.startswith("sqlite"):
            engine_options.update(pool_size=10, max_overflow=20, pool_recycle=1800)
        self.engine: AsyncEngine = create_async_engine(url, **engine_options)
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def close(self) -> None:
        await self.engine.dispose()
