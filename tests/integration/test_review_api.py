"""review API 端点集成测试."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from vocab_qc.api.deps import get_current_user, get_db
from vocab_qc.api.main import app
from vocab_qc.core.db import Base
from vocab_qc.core.models import ContentItem, Meaning, Word
from vocab_qc.core.models.enums import QcStatus, ReviewReason, ReviewStatus
from vocab_qc.core.models.quality_layer import ReviewItem
from vocab_qc.core.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine_and_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)


def _override_db(TestSession):
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

    return override_get_db


def _seed_base_data(TestSession):
    """插入 Word + Meaning + ContentItem，返回各 id。"""
    session = TestSession()
    word = Word(word="happy")
    session.add(word)
    session.flush()

    meaning = Meaning(word_id=word.id, pos="adj.", definition="快乐的")
    session.add(meaning)
    session.flush()

    item = ContentItem(
        word_id=word.id,
        meaning_id=meaning.id,
        dimension="chunk",
        content="be happy with sth.",
        qc_status=QcStatus.LAYER1_FAILED.value,
    )
    session.add(item)
    session.flush()

    ids = {"word_id": word.id, "meaning_id": meaning.id, "item_id": item.id}
    session.commit()
    session.close()
    return ids


def _add_review_item(TestSession, ids, status=ReviewStatus.PENDING.value):
    """插入 ReviewItem，返回 review id。"""
    session = TestSession()
    review = ReviewItem(
        content_item_id=ids["item_id"],
        word_id=ids["word_id"],
        meaning_id=ids["meaning_id"],
        dimension="chunk",
        reason=ReviewReason.LAYER1_FAILED.value,
        status=status,
    )
    session.add(review)
    session.commit()
    review_id = review.id
    session.close()
    return review_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_client():
    """admin 角色 + 已有 ReviewItem 的测试客户端。"""
    engine, TestSession = _make_engine_and_session()
    ids = _seed_base_data(TestSession)

    admin = User(id=1, email="admin@test.com", name="Admin", role="admin", is_active=True)
    app.dependency_overrides[get_db] = _override_db(TestSession)
    app.dependency_overrides[get_current_user] = lambda: admin

    client = TestClient(app)
    yield client, ids, TestSession

    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def viewer_client():
    """viewer 角色测试客户端（无写权限）。"""
    engine, TestSession = _make_engine_and_session()
    ids = _seed_base_data(TestSession)

    viewer = User(id=2, email="viewer@test.com", name="Viewer", role="viewer", is_active=True)
    app.dependency_overrides[get_db] = _override_db(TestSession)
    app.dependency_overrides[get_current_user] = lambda: viewer

    client = TestClient(app)
    yield client, ids, TestSession

    app.dependency_overrides.clear()
    engine.dispose()


# ---------------------------------------------------------------------------
# GET /api/reviews
# ---------------------------------------------------------------------------

class TestListReviews:
    def test_empty_list(self, admin_client):
        """无审核项时返回空列表。"""
        client, _ids, _session = admin_client
        resp = client.get("/api/reviews")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_returns_pending_items(self, admin_client):
        """有 pending 审核项时返回列表。"""
        client, ids, TestSession = admin_client
        review_id = _add_review_item(TestSession, ids)

        resp = client.get("/api/reviews")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == review_id
        assert data["items"][0]["status"] == "pending"
        assert data["items"][0]["dimension"] == "chunk"

    def test_resolved_items_excluded(self, admin_client):
        """已处理的审核项不出现在列表中。"""
        client, ids, TestSession = admin_client
        _add_review_item(TestSession, ids, status=ReviewStatus.RESOLVED.value)

        resp = client.get("/api/reviews")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_filter_by_dimension(self, admin_client):
        """dimension 参数过滤生效。"""
        client, ids, TestSession = admin_client
        _add_review_item(TestSession, ids)

        resp = client.get("/api/reviews?dimension=chunk")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

        resp_miss = client.get("/api/reviews?dimension=sentence")
        assert resp_miss.status_code == 200
        assert resp_miss.json()["items"] == []


# ---------------------------------------------------------------------------
# POST /api/reviews/{id}/approve
# ---------------------------------------------------------------------------

class TestApproveReview:
    def test_approve_success(self, admin_client):
        """正常通过审核。"""
        client, ids, TestSession = admin_client
        review_id = _add_review_item(TestSession, ids)

        resp = client.post(f"/api/reviews/{review_id}/approve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "resolved"
        assert data["resolution"] == "approved"
        assert data["reviewer"] == "Admin"

    def test_approve_with_note(self, admin_client):
        """带备注的通过审核。"""
        client, ids, TestSession = admin_client
        review_id = _add_review_item(TestSession, ids)

        resp = client.post(
            f"/api/reviews/{review_id}/approve",
            json={"note": "内容正确，通过"},
        )
        assert resp.status_code == 200
        assert resp.json()["review_note"] == "内容正确，通过"

    def test_approve_404_not_found(self, admin_client):
        """不存在的 review_id 返回 404。"""
        client, _ids, _session = admin_client
        resp = client.post("/api/reviews/99999/approve")
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]

    def test_approve_409_already_resolved(self, admin_client):
        """已处理的审核项返回 409。"""
        client, ids, TestSession = admin_client
        review_id = _add_review_item(TestSession, ids, status=ReviewStatus.RESOLVED.value)

        resp = client.post(f"/api/reviews/{review_id}/approve")
        assert resp.status_code == 409

    def test_approve_403_viewer_forbidden(self, viewer_client):
        """viewer 角色无权通过审核，返回 403。"""
        client, ids, TestSession = viewer_client
        review_id = _add_review_item(TestSession, ids)

        resp = client.post(f"/api/reviews/{review_id}/approve")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/reviews/{id}/regenerate
# ---------------------------------------------------------------------------

class TestRegenerateReview:
    def test_regenerate_success(self, admin_client):
        """正常触发重生成。"""
        from unittest.mock import patch

        client, ids, TestSession = admin_client
        review_id = _add_review_item(TestSession, ids)

        def _mock_regen(session, ci):
            ci.content = "mock regenerated content"

        with patch(
            "vocab_qc.core.services.review_service.ReviewService._do_regenerate",
            side_effect=_mock_regen,
        ):
            resp = client.post(f"/api/reviews/{review_id}/regenerate")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["retry_count"] == 1
        assert "重新生成" in data["message"]

    def test_regenerate_404_not_found(self, admin_client):
        """不存在的 review_id 返回 404。"""
        client, _ids, _session = admin_client
        resp = client.post("/api/reviews/99999/regenerate")
        assert resp.status_code == 404

    def test_regenerate_409_already_resolved(self, admin_client):
        """已处理的审核项返回 409。"""
        client, ids, TestSession = admin_client
        review_id = _add_review_item(TestSession, ids, status=ReviewStatus.RESOLVED.value)

        resp = client.post(f"/api/reviews/{review_id}/regenerate")
        assert resp.status_code == 409

    def test_regenerate_403_viewer_forbidden(self, viewer_client):
        """viewer 角色无权触发重生成，返回 403。"""
        client, ids, TestSession = viewer_client
        review_id = _add_review_item(TestSession, ids)

        resp = client.post(f"/api/reviews/{review_id}/regenerate")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/reviews/{id}/edit
# ---------------------------------------------------------------------------

class TestManualEdit:
    def test_edit_success(self, admin_client):
        """正常人工修改内容。"""
        client, ids, TestSession = admin_client
        review_id = _add_review_item(TestSession, ids)

        resp = client.post(
            f"/api/reviews/{review_id}/edit",
            json={"content": "be very happy with sth.", "content_cn": None},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "qc_passed" in data
        assert "message" in data

    def test_edit_updates_content_item(self, admin_client):
        """修改后 ContentItem 的内容已更新。"""
        client, ids, TestSession = admin_client
        review_id = _add_review_item(TestSession, ids)

        new_content = "feel happy about sth."
        client.post(
            f"/api/reviews/{review_id}/edit",
            json={"content": new_content},
        )

        session = TestSession()
        item = session.query(ContentItem).filter_by(id=ids["item_id"]).one()
        assert item.content == new_content
        # manual_edit 后自动质检，状态不再是初始 pending
        assert item.qc_status != QcStatus.PENDING.value
        session.close()

    def test_edit_404_not_found(self, admin_client):
        """不存在的 review_id 返回 404。"""
        client, _ids, _session = admin_client
        resp = client.post(
            "/api/reviews/99999/edit",
            json={"content": "new content"},
        )
        assert resp.status_code == 404

    def test_edit_409_already_resolved(self, admin_client):
        """已处理的审核项返回 409。"""
        client, ids, TestSession = admin_client
        review_id = _add_review_item(TestSession, ids, status=ReviewStatus.RESOLVED.value)

        resp = client.post(
            f"/api/reviews/{review_id}/edit",
            json={"content": "some content"},
        )
        assert resp.status_code == 409

    def test_edit_403_viewer_forbidden(self, viewer_client):
        """viewer 角色无权人工修改，返回 403。"""
        client, ids, TestSession = viewer_client
        review_id = _add_review_item(TestSession, ids)

        resp = client.post(
            f"/api/reviews/{review_id}/edit",
            json={"content": "some content"},
        )
        assert resp.status_code == 403

    def test_edit_requires_content_field(self, admin_client):
        """缺少 content 字段应返回 422。"""
        client, ids, TestSession = admin_client
        review_id = _add_review_item(TestSession, ids)

        resp = client.post(
            f"/api/reviews/{review_id}/edit",
            json={"content_cn": "只有中文"},
        )
        assert resp.status_code == 422
