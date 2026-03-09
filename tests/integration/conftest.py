"""集成测试共享 fixture：统一 TestClient 创建模式."""

from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from vocab_qc.core.db import Base


def make_test_engine():
    """创建 SQLite 内存引擎 + 建表。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def make_db_override(session_factory):
    """创建 get_db 依赖覆盖函数。"""
    def override_get_db():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return override_get_db
