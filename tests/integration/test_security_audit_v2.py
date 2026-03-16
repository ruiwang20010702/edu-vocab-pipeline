"""第二轮安全审计修复的集成测试."""

from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker
from vocab_qc.api.deps import get_current_user, get_db
from vocab_qc.api.main import app
from vocab_qc.core.db import Base
from vocab_qc.core.models.user import User


def _make_client(user_id: int, role: str):
    """创建指定角色的测试客户端。"""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    test_session_factory = sessionmaker(bind=engine)

    def override_get_db():
        session = test_session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    mock_user = User(id=user_id, email=f"{role}@test.com", name=f"Test{role.title()}", role=role, is_active=True)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # 插入用户到 DB
    session = test_session_factory()
    db_user = User(id=user_id, email=f"{role}@test.com", name=f"Test{role.title()}", role=role, is_active=True)
    session.add(db_user)
    # 额外用户用于编辑测试
    if role == "admin":
        other = User(id=99, email="other@test.com", name="Other", role="reviewer", is_active=True)
        session.add(other)
    session.commit()
    session.close()

    return TestClient(app), engine


class TestAdminSelfDemotion:
    """S-H1: Admin 不能降级自身角色或停用自身。"""

    def test_admin_cannot_change_own_role(self):
        client, engine = _make_client(1, "admin")
        try:
            resp = client.patch("/api/admin/users/1", json={"role": "viewer"})
            assert resp.status_code == 403
            assert "自己的角色" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()
            engine.dispose()

    def test_admin_cannot_deactivate_self(self):
        client, engine = _make_client(1, "admin")
        try:
            resp = client.patch("/api/admin/users/1", json={"is_active": False})
            assert resp.status_code == 403
            assert "停用自己" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()
            engine.dispose()

    def test_admin_can_edit_own_name(self):
        client, engine = _make_client(1, "admin")
        try:
            resp = client.patch("/api/admin/users/1", json={"name": "新名字"})
            assert resp.status_code == 200
            assert resp.json()["name"] == "新名字"
        finally:
            app.dependency_overrides.clear()
            engine.dispose()

    def test_admin_can_change_others_role(self):
        client, engine = _make_client(1, "admin")
        try:
            resp = client.patch("/api/admin/users/99", json={"role": "viewer"})
            assert resp.status_code == 200
            assert resp.json()["role"] == "viewer"
        finally:
            app.dependency_overrides.clear()
            engine.dispose()

    def test_admin_can_deactivate_others(self):
        client, engine = _make_client(1, "admin")
        try:
            resp = client.patch("/api/admin/users/99", json={"is_active": False})
            assert resp.status_code == 200
            assert resp.json()["is_active"] is False
        finally:
            app.dependency_overrides.clear()
            engine.dispose()


class TestPromptApiPermission:
    """S-H3: Prompt API 限制为 admin-only。"""

    def test_reviewer_cannot_list_prompts(self):
        client, engine = _make_client(2, "reviewer")
        try:
            resp = client.get("/api/prompts")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
            engine.dispose()

    def test_viewer_cannot_list_prompts(self):
        client, engine = _make_client(3, "viewer")
        try:
            resp = client.get("/api/prompts")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
            engine.dispose()

    def test_reviewer_cannot_get_prompt(self):
        client, engine = _make_client(2, "reviewer")
        try:
            resp = client.get("/api/prompts/1")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
            engine.dispose()

    def test_admin_can_list_prompts(self):
        client, engine = _make_client(1, "admin")
        try:
            resp = client.get("/api/prompts")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()
            engine.dispose()
