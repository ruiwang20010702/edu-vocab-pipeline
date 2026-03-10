"""认证端点集成测试."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from vocab_qc.api.deps import get_db
from vocab_qc.api.main import app
from vocab_qc.api.routers.auth import limiter
from vocab_qc.core.db import Base
from vocab_qc.core.models.user import User
from vocab_qc.core.services import auth_service


@pytest.fixture
def auth_app():
    """创建带测试数据库的认证测试客户端."""
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

    app.dependency_overrides[get_db] = override_get_db
    limiter.enabled = False

    # 创建测试用户
    session = TestSession()
    user = User(email="admin@test.com", name="Admin", role="admin")
    session.add(user)
    session.commit()
    session.close()

    client = TestClient(app)
    yield client, TestSession

    app.dependency_overrides.clear()
    limiter.enabled = True
    engine.dispose()


class TestSendCode:
    def test_send_code_success(self, auth_app):
        client, _ = auth_app
        with patch.object(auth_service, "send_email"):
            resp = client.post("/api/auth/send-code", json={"email": "admin@test.com"})
        assert resp.status_code == 200
        assert resp.json()["message"] == "验证码已发送"

    def test_send_code_domain_rejected(self, auth_app):
        client, _ = auth_app
        with patch.object(auth_service.settings, "allowed_email_domains", ["company.com"]):
            resp = client.post("/api/auth/send-code", json={"email": "user@other.com"})
        assert resp.status_code == 400


class TestVerify:
    def test_verify_success(self, auth_app):
        client, TestSession = auth_app
        # 先生成验证码
        session = TestSession()
        code = auth_service.generate_code(session, "admin@test.com")
        session.commit()
        session.close()

        resp = client.post("/api/auth/verify", json={"email": "admin@test.com", "code": code})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user_name"] == "Admin"
        assert data["user_role"] == "admin"

    def test_verify_wrong_code(self, auth_app):
        client, _ = auth_app
        resp = client.post("/api/auth/verify", json={"email": "admin@test.com", "code": "999999"})
        assert resp.status_code == 401

    def test_verify_unknown_user_auto_register(self, auth_app):
        """未知用户首次验证码正确时自动注册。"""
        client, TestSession = auth_app
        session = TestSession()
        code = auth_service.generate_code(session, "nobody@test.com")
        session.commit()
        session.close()

        resp = client.post("/api/auth/verify", json={"email": "nobody@test.com", "code": code})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user_name"] == "nobody"


class TestAdminEndpoints:
    def _get_token(self, client, TestSession):
        session = TestSession()
        code = auth_service.generate_code(session, "admin@test.com")
        session.commit()
        session.close()
        resp = client.post("/api/auth/verify", json={"email": "admin@test.com", "code": code})
        return resp.json()["access_token"]

    def test_create_user(self, auth_app):
        client, TestSession = auth_app
        token = self._get_token(client, TestSession)
        resp = client.post(
            "/api/admin/users",
            json={"email": "new@test.com", "name": "New User", "role": "reviewer"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "new@test.com"

    def test_list_users(self, auth_app):
        client, TestSession = auth_app
        token = self._get_token(client, TestSession)
        resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_get_me(self, auth_app):
        client, TestSession = auth_app
        token = self._get_token(client, TestSession)
        resp = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "admin@test.com"

    def test_no_token_returns_401(self, auth_app):
        client, _ = auth_app
        resp = client.get("/api/users/me")
        assert resp.status_code == 401
