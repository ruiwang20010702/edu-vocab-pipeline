"""export 端点集成测试."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from vocab_qc.api.deps import get_current_user, get_db
from vocab_qc.api.main import app
from vocab_qc.core.db import Base
from vocab_qc.core.models import ContentItem, Meaning, Phonetic, Source, Word
from vocab_qc.core.models.enums import QcStatus
from vocab_qc.core.models.user import User


@pytest.fixture
def test_app():
    """创建带测试数据库的 FastAPI 测试客户端（空库）."""
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

    mock_user = User(id=1, email="admin@test.com", name="TestAdmin", role="admin", is_active=True)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: mock_user

    client = TestClient(app)
    yield client, TestSession

    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def test_app_with_data():
    """创建带已审核内容的测试客户端."""
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

    mock_user = User(id=1, email="admin@test.com", name="TestAdmin", role="admin", is_active=True)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # 插入带 approved 内容的测试数据
    session = TestSession()
    word = Word(word="bright")
    session.add(word)
    session.flush()

    phonetic = Phonetic(word_id=word.id, ipa="/braɪt/", syllables="bright")
    session.add(phonetic)

    meaning = Meaning(word_id=word.id, pos="adj.", definition="明亮的")
    session.add(meaning)
    session.flush()

    source = Source(meaning_id=meaning.id, source_name="人教版七年级")
    chunk = ContentItem(
        word_id=word.id,
        meaning_id=meaning.id,
        dimension="chunk",
        content="a bright day",
        qc_status=QcStatus.APPROVED.value,
    )
    sentence = ContentItem(
        word_id=word.id,
        meaning_id=meaning.id,
        dimension="sentence",
        content="The sun is bright today.",
        content_cn="今天阳光明媚。",
        qc_status=QcStatus.APPROVED.value,
    )
    pending_item = ContentItem(
        word_id=word.id,
        meaning_id=meaning.id,
        dimension="chunk",
        content="pending chunk",
        qc_status=QcStatus.PENDING.value,
    )
    session.add_all([source, chunk, sentence, pending_item])
    session.commit()
    word_id = word.id
    session.close()

    client = TestClient(app)
    yield client, word_id

    app.dependency_overrides.clear()
    engine.dispose()


class TestExportReadiness:
    def test_readiness_empty_db(self, test_app):
        """空库时返回全零统计."""
        client, _ = test_app
        response = client.get("/api/export/readiness")
        assert response.status_code == 200
        data = response.json()
        assert data["total_items"] == 0
        assert data["approved"] == 0
        assert data["pending"] == 0
        assert data["not_approved"] == 0
        assert data["ready_rate"] == 0

    def test_readiness_with_data(self, test_app_with_data):
        """有数据时返回正确统计."""
        client, _ = test_app_with_data
        response = client.get("/api/export/readiness")
        assert response.status_code == 200
        data = response.json()
        assert data["total_items"] == 3       # 2 approved + 1 pending
        assert data["approved"] == 2
        assert data["pending"] == 1
        assert data["not_approved"] == 1      # total - approved
        assert data["ready_rate"] > 0

    def test_readiness_returns_required_keys(self, test_app):
        """响应包含所有必要字段."""
        client, _ = test_app
        response = client.get("/api/export/readiness")
        data = response.json()
        for key in ("total_items", "approved", "pending", "not_approved", "ready_rate"):
            assert key in data


class TestDownloadAll:
    def test_download_empty_db_returns_empty_list(self, test_app):
        """空库时返回空数组."""
        client, _ = test_app
        response = client.get("/api/export/download")
        assert response.status_code == 200
        assert response.json() == []

    def test_download_returns_content_disposition(self, test_app_with_data):
        """有 approved 内容时响应包含 Content-Disposition."""
        client, _ = test_app_with_data
        response = client.get("/api/export/download")
        assert response.status_code == 200
        assert "Content-Disposition" in response.headers
        assert "vocab_export.json" in response.headers["Content-Disposition"]

    def test_download_returns_approved_words(self, test_app_with_data):
        """有 approved 内容时返回词汇数据."""
        client, _ = test_app_with_data
        response = client.get("/api/export/download")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        word_data = data[0]
        assert word_data["word"] == "bright"
        assert word_data["ipa"] == "/braɪt/"

    def test_download_only_approved_content(self, test_app_with_data):
        """导出内容仅含 approved 状态，pending 不放行."""
        client, _ = test_app_with_data
        response = client.get("/api/export/download")
        data = response.json()
        # pending_item 不应出现在导出结果里
        for word_data in data:
            for meaning_data in word_data["meanings"]:
                # chunk 字段若有值，必须来自 approved 内容
                if meaning_data["chunk"] is not None:
                    assert meaning_data["chunk"] == "a bright day"

    def test_download_includes_meaning_fields(self, test_app_with_data):
        """导出词义包含 pos/def/sources/chunk/sentence/sentence_cn."""
        client, _ = test_app_with_data
        response = client.get("/api/export/download")
        meaning = response.json()[0]["meanings"][0]
        for key in ("pos", "def", "sources", "chunk", "sentence", "sentence_cn"):
            assert key in meaning


class TestExportWord:
    def test_export_existing_word(self, test_app_with_data):
        """正常返回单词数据."""
        client, word_id = test_app_with_data
        response = client.get(f"/api/export/word/{word_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["word"] == "bright"
        assert data["id"] == word_id
        assert "meanings" in data
        assert "mnemonics" in data

    def test_export_nonexistent_word_returns_404(self, test_app):
        """不存在的 word_id 返回 404."""
        client, _ = test_app
        response = client.get("/api/export/word/99999")
        assert response.status_code == 404
        assert "detail" in response.json()

    def test_export_word_structure(self, test_app_with_data):
        """返回数据结构包含必要字段."""
        client, word_id = test_app_with_data
        response = client.get(f"/api/export/word/{word_id}")
        data = response.json()
        for key in ("id", "word", "syllables", "ipa", "meanings", "mnemonics"):
            assert key in data

    def test_export_word_phonetic(self, test_app_with_data):
        """返回数据包含音标信息."""
        client, word_id = test_app_with_data
        response = client.get(f"/api/export/word/{word_id}")
        data = response.json()
        assert data["ipa"] == "/braɪt/"
        assert data["syllables"] == "bright"
