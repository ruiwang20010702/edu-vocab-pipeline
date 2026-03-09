"""API 端点集成测试."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from vocab_qc.api.deps import get_current_user, get_db
from vocab_qc.api.main import app
from vocab_qc.core.db import Base
from vocab_qc.core.models import ContentItem, Meaning, Phonetic, ReviewItem, ReviewReason, Source, Word
from vocab_qc.core.models.user import User
from vocab_qc.core.services.review_service import ReviewService


@pytest.fixture
def test_app():
    """创建带测试数据库的 FastAPI 测试客户端."""
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

    # Mock admin 用户，绕过认证
    mock_user = User(id=1, email="admin@test.com", name="TestAdmin", role="admin", is_active=True)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # 插入测试数据
    session = TestSession()
    word = Word(word="kind")
    session.add(word)
    session.flush()

    phonetic = Phonetic(word_id=word.id, ipa="/kaɪnd/", syllables="kind")
    session.add(phonetic)

    meaning = Meaning(word_id=word.id, pos="adj.", definition="友好的")
    session.add(meaning)
    session.flush()

    Source(meaning_id=meaning.id, source_name="人教版")
    chunk = ContentItem(word_id=word.id, meaning_id=meaning.id, dimension="chunk", content="be kind to sb.")
    sentence = ContentItem(
        word_id=word.id,
        meaning_id=meaning.id,
        dimension="sentence",
        content="The teacher is always kind to every student.",
        content_cn="老师对每位同学总是很友好。",
    )
    session.add_all([chunk, sentence])
    session.commit()
    session.close()

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()
    engine.dispose()


def test_health(test_app):
    response = test_app.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_run_qc(test_app):
    response = test_app.post("/api/qc/run", json={"layers": [1], "dimension": "chunk"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["run_id"] is not None


def test_run_qc_no_items(test_app):
    response = test_app.post("/api/qc/run", json={"layers": [1], "dimension": "nonexistent"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0


def test_get_reviews_empty(test_app):
    response = test_app.get("/api/reviews")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_full_qc_and_review_flow(test_app):
    """完整流程: 质检 → 审核通过."""
    # Step 1: 运行质检
    run_response = test_app.post("/api/qc/run", json={"layers": [1]})
    assert run_response.status_code == 200
    run_data = run_response.json()
    assert run_data["total"] > 0
