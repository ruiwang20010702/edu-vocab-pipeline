"""角色权限控制集成测试."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from vocab_qc.api.deps import get_current_user, get_db
from vocab_qc.api.main import app
from vocab_qc.core.db import Base
from vocab_qc.core.models import ContentItem, Meaning, Phonetic, Word
from vocab_qc.core.models.user import User


def _make_app(role: str):
    """创建指定角色的测试客户端。"""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSession()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    mock_user = User(id=1, email=f"{role}@test.com", name=f"Test{role.title()}", role=role, is_active=True)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # 插入最少测试数据
    session = TestSession()
    word = Word(word="test")
    session.add(word)
    session.flush()
    phonetic = Phonetic(word_id=word.id, ipa="/tɛst/", syllables="test")
    meaning = Meaning(word_id=word.id, pos="n.", definition="测试")
    session.add_all([phonetic, meaning])
    session.flush()
    chunk = ContentItem(word_id=word.id, meaning_id=meaning.id, dimension="chunk", content="a test")
    session.add(chunk)
    session.commit()
    session.close()

    return TestClient(app), engine


@pytest.fixture(params=["admin", "reviewer", "viewer"])
def role_client(request):
    role = request.param
    client, engine = _make_app(role)
    yield role, client
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def no_auth_client():
    """无认证的测试客户端。"""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSession()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # 只 override db，不 override get_current_user → 触发 401
    app.dependency_overrides[get_db] = override_get_db
    # 确保 get_current_user 不被 override
    app.dependency_overrides.pop(get_current_user, None)

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()
    engine.dispose()


class TestUnauthenticated:
    """未认证应返回 401。"""

    def test_get_reviews_401(self, no_auth_client):
        assert no_auth_client.get("/api/reviews").status_code == 401

    def test_post_qc_run_401(self, no_auth_client):
        assert no_auth_client.post("/api/qc/run", json={"layers": [1]}).status_code == 401

    def test_export_readiness_401(self, no_auth_client):
        assert no_auth_client.get("/api/export/readiness").status_code == 401


class TestRolePermissions:
    """各角色权限矩阵测试。"""

    def test_get_reviews(self, role_client):
        role, client = role_client
        resp = client.get("/api/reviews")
        # 所有角色都能读取审核列表
        assert resp.status_code == 200

    def test_post_qc_run(self, role_client):
        role, client = role_client
        resp = client.post("/api/qc/run", json={"layers": [1], "dimension": "chunk"})
        if role == "admin":
            assert resp.status_code == 200
        else:
            assert resp.status_code == 403

    def test_export_readiness(self, role_client):
        role, client = role_client
        resp = client.get("/api/export/readiness")
        if role == "admin":
            assert resp.status_code == 200
        else:
            assert resp.status_code == 403
