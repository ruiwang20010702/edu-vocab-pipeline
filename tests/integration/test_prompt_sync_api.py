"""PM-H3: Prompt 同步 API 测试."""

import pytest
from fastapi.testclient import TestClient
from vocab_qc.api.main import app
from vocab_qc.core.models.user import User
from vocab_qc.core.services.auth_service import create_jwt


@pytest.fixture
def client(db_session):
    from vocab_qc.api.deps import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def admin_headers(db_session):
    user = User(email="admin@test.com", name="Admin", role="admin", is_active=True)
    db_session.add(user)
    db_session.flush()
    token = create_jwt(user)
    return {"Authorization": f"Bearer {token}"}


class TestSyncPreviewAPI:
    def test_preview_returns_counts(self, client, admin_headers):
        resp = client.get("/api/prompts/sync/preview", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "created" in data
        assert "updated" in data
        assert "skipped" in data

    def test_preview_requires_admin(self, client):
        resp = client.get("/api/prompts/sync/preview")
        assert resp.status_code in (401, 403)


class TestSyncAPI:
    def test_sync_returns_counts(self, client, admin_headers):
        resp = client.post("/api/prompts/sync", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "created" in data
        assert "updated" in data
        assert "skipped" in data

    def test_sync_requires_admin(self, client):
        resp = client.post("/api/prompts/sync")
        assert resp.status_code in (401, 403)
