"""数据库连接管理."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from vocab_qc.core.config import settings


class Base(DeclarativeBase):
    pass


def _create_engine():
    url = settings.database_url_sync
    common = {"echo": settings.db_echo}
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool

        common["connect_args"] = {"check_same_thread": False}
        common["poolclass"] = StaticPool
    else:
        common["pool_size"] = 20
        common["max_overflow"] = 10
        common["pool_pre_ping"] = True
        common["pool_recycle"] = 1800
        common["pool_timeout"] = 30
        common["connect_args"] = {"connect_timeout": 10}
    return create_engine(url, **common)


# 同步引擎（Alembic + CLI + API 使用）
sync_engine = _create_engine()
SyncSessionLocal = sessionmaker(bind=sync_engine)


def get_sync_session() -> Session:
    return SyncSessionLocal()
