"""角色权限控制集成测试."""

import io
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from vocab_qc.api.deps import get_current_user, get_db
from vocab_qc.api.main import app
from vocab_qc.core.db import Base
from vocab_qc.core.models import ContentItem, Meaning, Package, Phonetic, ReviewItem, Word
from vocab_qc.core.models.user import User


def _make_app(role: str):
    """创建指定角色的测试客户端，预置完整测试数据。"""
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

    # 插入测试数据：Word, Phonetic, Meaning, ContentItem, Package, ReviewItem
    session = TestSession()

    # 用户记录（供 /api/users/me 使用）
    db_user = User(id=1, email=f"{role}@test.com", name=f"Test{role.title()}", role=role, is_active=True)
    session.add(db_user)
    session.flush()

    word = Word(word="test")
    session.add(word)
    session.flush()

    phonetic = Phonetic(word_id=word.id, ipa="/tɛst/", syllables="test")
    meaning = Meaning(word_id=word.id, pos="n.", definition="测试")
    session.add_all([phonetic, meaning])
    session.flush()

    chunk = ContentItem(word_id=word.id, meaning_id=meaning.id, dimension="chunk", content="a test")
    session.add(chunk)
    session.flush()

    # Package（供 POST /api/batches/{id}/produce 使用）
    package = Package(id=1, name="test-batch", status="pending", total_words=1)
    session.add(package)
    session.flush()

    # ReviewItem（供 POST /api/reviews/{id}/approve 使用）
    review_item = ReviewItem(
        content_item_id=chunk.id,
        word_id=word.id,
        meaning_id=meaning.id,
        dimension="chunk",
        reason="qc_fail",
        status="pending",
    )
    session.add(review_item)
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


# ---------------------------------------------------------------------------
# 辅助：构造 multipart 上传文件
# ---------------------------------------------------------------------------

def _make_upload_file(words: list[dict] | None = None) -> dict:
    """构造一个合法的 JSON 上传文件，用于 POST /api/import。"""
    if words is None:
        words = [{"word": "hello", "phonetics": [{"ipa": "/həˈloʊ/", "syllables": "hel·lo"}],
                  "meanings": [{"pos": "interj.", "definition": "你好"}]}]
    content = json.dumps(words).encode("utf-8")
    return {"file": ("words.json", io.BytesIO(content), "application/json")}


class TestUnauthenticated:
    """未认证应返回 401。"""

    def test_get_reviews_401(self, no_auth_client):
        assert no_auth_client.get("/api/reviews").status_code == 401

    def test_post_qc_run_401(self, no_auth_client):
        assert no_auth_client.post("/api/qc/run", json={"layers": [1]}).status_code == 401

    def test_export_readiness_401(self, no_auth_client):
        assert no_auth_client.get("/api/export/readiness").status_code == 401

    def test_import_upload_401(self, no_auth_client):
        resp = no_auth_client.post("/api/import", files=_make_upload_file())
        assert resp.status_code == 401

    def test_get_words_401(self, no_auth_client):
        assert no_auth_client.get("/api/words").status_code == 401

    def test_get_stats_401(self, no_auth_client):
        assert no_auth_client.get("/api/stats").status_code == 401

    def test_users_me_401(self, no_auth_client):
        assert no_auth_client.get("/api/users/me").status_code == 401

    def test_admin_create_user_401(self, no_auth_client):
        resp = no_auth_client.post("/api/admin/users", json={"email": "a@b.com", "name": "A", "role": "viewer"})
        assert resp.status_code == 401

    def test_export_download_401(self, no_auth_client):
        assert no_auth_client.get("/api/export/download").status_code == 401

    def test_batch_produce_401(self, no_auth_client):
        assert no_auth_client.post("/api/batches/1/produce").status_code == 401

    def test_review_approve_401(self, no_auth_client):
        assert no_auth_client.post("/api/reviews/1/approve").status_code == 401


class TestRolePermissions:
    """各角色权限矩阵测试。"""

    # --- 既有测试 ---

    def test_get_reviews(self, role_client):
        role, client = role_client
        resp = client.get("/api/reviews")
        # 所有角色都能读取审核列表
        assert resp.status_code == 200
        # 验证返回格式为 {items, total, ...}
        data = resp.json()
        assert "items" in data
        assert "total" in data

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

    # --- 新增测试 ---

    def test_import_upload(self, role_client):
        """POST /api/import — 仅 admin 可上传导入。"""
        role, client = role_client
        resp = client.post("/api/import", files=_make_upload_file())
        if role == "admin":
            assert resp.status_code == 200
        else:
            assert resp.status_code == 403

    def test_batch_produce(self, role_client):
        """POST /api/batches/{id}/produce — 仅 admin 可触发生产。"""
        role, client = role_client
        resp = client.post("/api/batches/1/produce")
        if role == "admin":
            # admin 能触发，返回 200 或 409（正在处理）
            assert resp.status_code in (200, 409)
        else:
            assert resp.status_code == 403

    def test_get_words(self, role_client):
        """GET /api/words — 所有角色可访问。"""
        role, client = role_client
        resp = client.get("/api/words")
        assert resp.status_code == 200

    def test_get_stats(self, role_client):
        """GET /api/stats — 所有角色可访问。"""
        role, client = role_client
        resp = client.get("/api/stats")
        assert resp.status_code == 200

    def test_review_approve(self, role_client):
        """POST /api/reviews/{id}/approve — admin + reviewer 可操作，viewer 403。"""
        role, client = role_client
        resp = client.post("/api/reviews/1/approve")
        if role in ("admin", "reviewer"):
            # 200 表示成功，404 表示数据不匹配（但权限通过），409 已处理
            assert resp.status_code in (200, 404, 409)
        else:
            assert resp.status_code == 403

    def test_export_download(self, role_client):
        """GET /api/export/download — 仅 admin 可下载。"""
        role, client = role_client
        resp = client.get("/api/export/download")
        if role == "admin":
            assert resp.status_code == 200
        else:
            assert resp.status_code == 403

    def test_admin_create_user(self, role_client):
        """POST /api/admin/users — 仅 admin 可创建用户。"""
        role, client = role_client
        resp = client.post(
            "/api/admin/users",
            json={"email": "new@example.com", "name": "NewUser", "role": "viewer"},
        )
        if role == "admin":
            # 200 成功创建，409 邮箱已存在
            assert resp.status_code in (200, 409)
        else:
            assert resp.status_code == 403

    def test_users_me(self, role_client):
        """GET /api/users/me — 所有认证角色可访问。"""
        role, client = role_client
        resp = client.get("/api/users/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == role
