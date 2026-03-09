"""数据库连接管理."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from vocab_qc.core.config import settings


class Base(DeclarativeBase):
    pass


# 同步引擎（Alembic + CLI + API 使用）
sync_engine = create_engine(settings.database_url_sync, echo=settings.db_echo)
SyncSessionLocal = sessionmaker(bind=sync_engine)


def get_sync_session() -> Session:
    return SyncSessionLocal()
