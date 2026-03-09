"""新端点集成测试: /api/stats, /api/words, /api/import, /api/batches 列表."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from vocab_qc.api.deps import get_current_user, get_db
from vocab_qc.api.main import app
from vocab_qc.core.db import Base
from vocab_qc.core.models import ContentItem, Meaning, Phonetic, QcStatus, Source, Word
from vocab_qc.core.models.package_layer import Package, PackageMeaning
from vocab_qc.core.models.user import User


@pytest.fixture
def test_app():
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

    # 插入测试数据
    session = TestSession()
    word = Word(word="happy")
    session.add(word)
    session.flush()

    phonetic = Phonetic(word_id=word.id, ipa="/ˈhæpi/", syllables="hap·py")
    session.add(phonetic)

    meaning = Meaning(word_id=word.id, pos="adj.", definition="快乐的")
    session.add(meaning)
    session.flush()

    source = Source(meaning_id=meaning.id, source_name="人教七上")
    session.add(source)

    chunk = ContentItem(
        word_id=word.id, meaning_id=meaning.id, dimension="chunk",
        content="be happy about", qc_status=QcStatus.APPROVED.value,
    )
    sentence = ContentItem(
        word_id=word.id, meaning_id=meaning.id, dimension="sentence",
        content="I am happy to see you.", content_cn="我很高兴见到你。",
        qc_status=QcStatus.PENDING.value,
    )
    session.add_all([chunk, sentence])

    pkg = Package(name="测试词包")
    session.add(pkg)
    session.flush()
    pm = PackageMeaning(package_id=pkg.id, meaning_id=meaning.id)
    session.add(pm)

    session.commit()
    session.close()

    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
    engine.dispose()


class TestStatsEndpoint:
    def test_get_stats(self, test_app):
        resp = test_app.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_words"] == 1
        assert data["approved_count"] >= 1
        assert "pass_rate" in data

    def test_stats_requires_auth(self):
        """未认证时被拒。"""
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        app.dependency_overrides.clear()
        client = TestClient(app)
        resp = client.get("/api/stats")
        assert resp.status_code == 401
        engine.dispose()


class TestWordsEndpoint:
    def test_list_words(self, test_app):
        resp = test_app.get("/api/words")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["page"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["word"] == "happy"

    def test_list_words_search(self, test_app):
        resp = test_app.get("/api/words?q=happy")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

        resp = test_app.get("/api/words?q=nonexistent")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_words_pagination(self, test_app):
        resp = test_app.get("/api/words?page=1&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10

    def test_word_detail(self, test_app):
        resp = test_app.get("/api/words")
        word_id = resp.json()["items"][0]["id"]

        resp = test_app.get(f"/api/words/{word_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["word"] == "happy"
        assert len(data["phonetics"]) == 1
        assert len(data["meanings"]) == 1

    def test_word_detail_not_found(self, test_app):
        resp = test_app.get("/api/words/99999")
        assert resp.status_code == 404


class TestBatchListEndpoint:
    def test_list_batches(self, test_app):
        resp = test_app.get("/api/batches")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["name"] == "测试词包"

    def test_batch_info(self, test_app):
        resp = test_app.get("/api/batches")
        batch_id = resp.json()[0]["id"]

        resp = test_app.get(f"/api/batches/info/{batch_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "测试词包"


class TestImportEndpoint:
    def test_import_json(self, test_app):
        data = [
            {
                "word": "world",
                "meanings": [
                    {"pos": "n.", "definition": "世界", "sources": ["课本1"]}
                ],
            }
        ]
        content = json.dumps(data).encode("utf-8")
        resp = test_app.post(
            "/api/import",
            data={"batch_name": "import_test"},
            files={"file": ("words.json", content, "application/json")},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["word_count"] == 1
        assert result["batch_id"]

    def test_import_csv(self, test_app):
        csv = "word,pos,definition,source\ngood,adj.,好的,src1"
        resp = test_app.post(
            "/api/import",
            data={"batch_name": "csv_test"},
            files={"file": ("words.csv", csv.encode(), "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["word_count"] == 1

    def test_import_empty_file(self, test_app):
        resp = test_app.post(
            "/api/import",
            data={"batch_name": "empty"},
            files={"file": ("test.json", b"", "application/json")},
        )
        assert resp.status_code == 400

    def test_import_unsupported_format(self, test_app):
        resp = test_app.post(
            "/api/import",
            data={"batch_name": "bad"},
            files={"file": ("test.xlsx", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 400
