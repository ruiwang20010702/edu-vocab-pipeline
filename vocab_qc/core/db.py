"""数据库连接管理."""

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from vocab_qc.core.config import settings


class Base(DeclarativeBase):
    pass


# 同步引擎（Alembic + CLI 使用）
sync_engine = create_engine(settings.database_url_sync, echo=settings.db_echo)
SyncSessionLocal = sessionmaker(bind=sync_engine)

# 异步引擎（API 使用）
async_engine = create_async_engine(settings.database_url_async, echo=settings.db_echo)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, expire_on_commit=False)


def get_sync_session() -> Session:
    return SyncSessionLocal()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
