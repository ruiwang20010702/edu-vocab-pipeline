"""认证端点集成测试."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker
from vocab_qc.api.deps import get_db
from vocab_qc.api.main import app
from vocab_qc.api.routers.auth import limiter
from vocab_qc.core.config import settings
from vocab_qc.core.db import Base
from vocab_qc.core.models.user import User
from vocab_qc.core.services import auth_service


@pytest.fixture
def auth_app():
    """创建带测试数据库的认证测试客户端."""
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

    app.dependency_overrides[get_db] = override_get_db
    limiter.enabled = False

    # 创建测试用户
    session = test_session_factory()
    user = User(email="admin@test.com", name="Admin", role="admin")
    session.add(user)
    session.commit()
    session.close()

    client = TestClient(app)
    yield client, test_session_factory

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
        client, test_session_factory = auth_app
        # 先生成验证码
        session = test_session_factory()
        code = auth_service.generate_code(session, "admin@test.com")
        session.commit()
        session.close()

        resp = client.post("/api/auth/verify", json={"email": "admin@test.com", "code": code})
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_name"] == "Admin"
        assert data["user_role"] == "admin"
        # JWT 通过 httpOnly cookie 下发，不在 JSON body 中
        assert "access_token" not in data
        assert settings.cookie_name in resp.cookies

    def test_verify_wrong_code(self, auth_app):
        client, _ = auth_app
        resp = client.post("/api/auth/verify", json={"email": "admin@test.com", "code": "999999"})
        assert resp.status_code == 401

    def test_verify_unknown_user_auto_register(self, auth_app):
        """未知用户首次验证码正确时自动注册。"""
        client, test_session_factory = auth_app
        session = test_session_factory()
        code = auth_service.generate_code(session, "nobody@test.com")
        session.commit()
        session.close()

        resp = client.post("/api/auth/verify", json={"email": "nobody@test.com", "code": code})
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_name"] == "nobody"
        assert "access_token" not in data
        assert settings.cookie_name in resp.cookies

    def test_verify_sets_httponly_cookie(self, auth_app):
        """验证 Set-Cookie header 含 httponly 标志。"""
        client, test_session_factory = auth_app
        session = test_session_factory()
        code = auth_service.generate_code(session, "admin@test.com")
        session.commit()
        session.close()

        resp = client.post("/api/auth/verify", json={"email": "admin@test.com", "code": code})
        assert resp.status_code == 200
        set_cookie = resp.headers.get("set-cookie", "")
        assert "httponly" in set_cookie.lower()

    def test_cookie_auth_works(self, auth_app):
        """用 cookie 访问受保护端点。"""
        client, test_session_factory = auth_app
        session = test_session_factory()
        code = auth_service.generate_code(session, "admin@test.com")
        session.commit()
        session.close()

        resp = client.post("/api/auth/verify", json={"email": "admin@test.com", "code": code})
        token = resp.cookies[settings.cookie_name]

        # 用 cookie 访问 /users/me（不带 Authorization header）
        client.cookies.set(settings.cookie_name, token)
        resp2 = client.get("/api/users/me")
        assert resp2.status_code == 200
        assert resp2.json()["email"] == "admin@test.com"

    def test_logout_clears_cookie(self, auth_app):
        """/logout 后 cookie 被清除。"""
        client, test_session_factory = auth_app
        session = test_session_factory()
        code = auth_service.generate_code(session, "admin@test.com")
        session.commit()
        session.close()

        # 先登录
        resp = client.post("/api/auth/verify", json={"email": "admin@test.com", "code": code})
        assert settings.cookie_name in resp.cookies

        # 退出
        resp2 = client.post("/api/auth/logout")
        assert resp2.status_code == 200
        assert resp2.json()["message"] == "已退出"
        # 检查 Set-Cookie 中 max-age=0（删除 cookie）
        set_cookie = resp2.headers.get("set-cookie", "")
        assert 'max-age=0' in set_cookie.lower() or '="";' in set_cookie


class TestAdminEndpoints:
    def _get_token(self, client, test_session_factory):
        session = test_session_factory()
        code = auth_service.generate_code(session, "admin@test.com")
        session.commit()
        session.close()
        resp = client.post("/api/auth/verify", json={"email": "admin@test.com", "code": code})
        return resp.cookies[settings.cookie_name]

    def test_create_user(self, auth_app):
        client, test_session_factory = auth_app
        token = self._get_token(client, test_session_factory)
        resp = client.post(
            "/api/admin/users",
            json={"email": "new@test.com", "name": "New User", "role": "reviewer"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "new@test.com"

    def test_list_users(self, auth_app):
        client, test_session_factory = auth_app
        token = self._get_token(client, test_session_factory)
        resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_get_me(self, auth_app):
        client, test_session_factory = auth_app
        token = self._get_token(client, test_session_factory)
        resp = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "admin@test.com"

    def test_no_token_returns_401(self, auth_app):
        client, _ = auth_app
        resp = client.get("/api/users/me")
        assert resp.status_code == 401
