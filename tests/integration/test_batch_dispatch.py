"""批次派发集成测试: 多用户并发 + API 端点."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from vocab_qc.api.deps import get_current_user, get_db
from vocab_qc.api.main import app
from vocab_qc.core.db import Base
from vocab_qc.core.models import ContentItem, Meaning, Phonetic, ReviewItem, ReviewReason, Word
from vocab_qc.core.models.user import User
from vocab_qc.core.services import batch_service
from vocab_qc.core.services.review_service import ReviewService


def _setup_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    return engine, TestSession


def _seed_words(session: Session, n: int = 10) -> list[Word]:
    """创建 n 个词，每个词有 2 个 pending ReviewItem。"""
    words = []
    service = ReviewService()
    for i in range(n):
        word = Word(word=f"word_{i}")
        session.add(word)
        session.flush()

        phonetic = Phonetic(word_id=word.id, ipa=f"/w{i}/", syllables=f"word_{i}")
        meaning = Meaning(word_id=word.id, pos="n.", definition=f"定义{i}")
        session.add_all([phonetic, meaning])
        session.flush()

        for dim in ("chunk", "sentence"):
            content = ContentItem(
                word_id=word.id,
                meaning_id=meaning.id,
                dimension=dim,
                content=f"content {dim} {i}",
            )
            session.add(content)
            session.flush()
            service.create_review_item(session, content, ReviewReason.LAYER1_FAILED)

        words.append(word)

    session.commit()
    return words


class TestMultiUserDispatch:
    """多用户并发领取集成测试。"""

    def test_three_users_no_overlap(self):
        engine, TestSession = _setup_db()
        session = TestSession()

        # 创建 3 个用户 + 9 个词
        users = []
        for i in range(3):
            u = User(email=f"r{i}@test.com", name=f"Reviewer{i}", role="reviewer")
            session.add(u)
            session.flush()
            users.append(u)

        _seed_words(session, 9)

        # 每人领 3 个词
        batches = []
        for u in users:
            b = batch_service.assign_batch(session, u.id, batch_size=3)
            assert b is not None
            batches.append(b)

        # 验证不重叠
        all_word_sets = []
        for b in batches:
            data = batch_service.get_batch_words(session, b.id)
            all_word_sets.append(set(data["words"].keys()))

        for i in range(len(all_word_sets)):
            for j in range(i + 1, len(all_word_sets)):
                assert all_word_sets[i].isdisjoint(all_word_sets[j])

        session.close()
        engine.dispose()


class TestBatchApi:
    """批次 API 端点集成测试。"""

    @pytest.fixture
    def batch_app(self):
        engine, TestSession = _setup_db()

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

        # 创建 admin 用户
        session = TestSession()
        admin = User(email="admin@test.com", name="Admin", role="admin")
        session.add(admin)
        session.flush()
        admin_id = admin.id
        _seed_words(session, 5)
        session.close()

        mock_user = User(id=admin_id, email="admin@test.com", name="Admin", role="admin", is_active=True)
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: mock_user

        client = TestClient(app)
        yield client

        app.dependency_overrides.clear()
        engine.dispose()

    def test_assign_and_current(self, batch_app):
        # 领取
        resp = batch_app.post("/api/batches/assign?batch_size=3")
        assert resp.status_code == 200
        data = resp.json()
        assert data["word_count"] == 3

        # 查看当前批次
        resp = batch_app.get("/api/batches/current")
        assert resp.status_code == 200
        assert resp.json()["id"] == data["id"]

    def test_get_batch_words(self, batch_app):
        resp = batch_app.post("/api/batches/assign?batch_size=2")
        batch_id = resp.json()["id"]

        resp = batch_app.get(f"/api/batches/{batch_id}/words")
        assert resp.status_code == 200
        words = resp.json()["words"]
        assert len(words) == 2

    def test_skip_word(self, batch_app):
        resp = batch_app.post("/api/batches/assign?batch_size=2")
        batch_id = resp.json()["id"]

        # 获取第一个词的 word_id
        resp = batch_app.get(f"/api/batches/{batch_id}/words")
        word_id = resp.json()["words"][0]["word_id"]

        resp = batch_app.post(f"/api/batches/{batch_id}/words/{word_id}/skip")
        assert resp.status_code == 200

    def test_stats(self, batch_app):
        batch_app.post("/api/batches/assign?batch_size=2")
        resp = batch_app.get("/api/batches/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "pending_words" in data
        assert "reviewed_words" in data

    def test_empty_pool(self, batch_app):
        # 领取所有（batch_size 上限 50）
        batch_app.post("/api/batches/assign?batch_size=50")
        # 此时已有一个 in_progress 批次，再次领取应返回已有的
        resp2 = batch_app.post("/api/batches/assign?batch_size=50")
        assert resp2.status_code == 200
