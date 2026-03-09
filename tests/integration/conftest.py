"""集成测试共享 fixture：统一 TestClient 创建模式.

提供两种使用方式:
1. pytest fixture: integration_engine, integration_session_factory, override_get_db
2. 工具函数（向后兼容）: make_test_engine(), make_db_override()
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from vocab_qc.api.deps import get_current_user, get_db
from vocab_qc.api.main import app
from vocab_qc.core.db import Base
from vocab_qc.core.models.user import User


# ── 工具函数（向后兼容，各测试文件如已直接使用可继续使用） ──


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
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return override_get_db


# ── pytest fixture 版本 ──


@pytest.fixture
def integration_engine():
    """创建集成测试用 SQLite 内存引擎。"""
    engine = make_test_engine()
    yield engine
    engine.dispose()


@pytest.fixture
def integration_session_factory(integration_engine):
    """基于集成测试引擎创建 session 工厂。"""
    return sessionmaker(bind=integration_engine)


@pytest.fixture
def override_get_db(integration_session_factory):
    """返回 get_db 依赖覆盖函数。"""
    return make_db_override(integration_session_factory)


@pytest.fixture
def admin_user():
    """Mock admin 用户。"""
    return User(id=1, email="admin@test.com", name="TestAdmin", role="admin", is_active=True)


@pytest.fixture
def admin_test_client(override_get_db, admin_user):
    """带 admin 权限的 TestClient（自动清理 dependency_overrides）。"""
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
