"""异步导出端点集成测试：发起 / 去重 / 轮询状态 / 下载 / 404·409。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker
from vocab_qc.api.deps import get_current_user, get_db
from vocab_qc.api.main import app
from vocab_qc.core.db import Base
from vocab_qc.core.models import ExportJob
from vocab_qc.core.models.user import User
from vocab_qc.core.services import export_job_service as svc


@pytest.fixture
def client_factory(monkeypatch, tmp_path):
    """admin TestClient + 内存库 factory。后台任务被 patch 成 no-op，避免连真库。"""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override_get_db():
        s = factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    mock_user = User(id=1, email="admin@test.com", name="A", role="admin", is_active=True)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: mock_user
    monkeypatch.setattr(svc, "EXPORT_DIR", tmp_path / "exports")

    async def _noop(job_id):
        return None

    monkeypatch.setattr("vocab_qc.api.routers.export._run_export_job_bg_async", _noop)

    client = TestClient(app)
    yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()


def test_start_export_returns_pending(client_factory):
    client, _ = client_factory
    r = client.post("/api/export/excel/async")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    assert isinstance(body["id"], int)
    assert body["download_ready"] is False


def test_start_export_dedupe(client_factory):
    client, factory = client_factory
    id1 = client.post("/api/export/excel/async").json()["id"]
    id2 = client.post("/api/export/excel/async").json()["id"]
    assert id1 == id2
    with factory() as s:
        assert s.query(ExportJob).count() == 1


def test_status_and_download(client_factory):
    client, factory = client_factory
    job_id = client.post("/api/export/excel/async").json()["id"]
    # 后台任务被 patch 掉，这里直接在测试库上把任务跑完
    with factory() as s:
        svc.run_job(s, job_id)

    r = client.get(f"/api/export/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
    assert r.json()["download_ready"] is True

    d = client.get(f"/api/export/jobs/{job_id}/download")
    assert d.status_code == 200
    assert "spreadsheet" in d.headers["content-type"]


def test_download_not_ready_returns_409(client_factory):
    client, _ = client_factory
    job_id = client.post("/api/export/excel/async").json()["id"]
    assert client.get(f"/api/export/jobs/{job_id}/download").status_code == 409


def test_job_not_found_returns_404(client_factory):
    client, _ = client_factory
    assert client.get("/api/export/jobs/999999").status_code == 404
    assert client.get("/api/export/jobs/999999/download").status_code == 404
