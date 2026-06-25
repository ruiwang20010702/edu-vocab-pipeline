"""AI 用量统计 API 集成测试."""

from fastapi.testclient import TestClient
from vocab_qc.api.deps import get_current_user, get_db
from vocab_qc.api.main import app

from .conftest import make_db_override, make_test_engine


class TestAiUsageStatsApi:
    """GET /api/stats/ai-usage 端点测试。"""

    def test_unauthenticated(self):
        """未登录返回 401。"""
        engine = make_test_engine()
        session_factory = __import__("sqlalchemy.orm", fromlist=["sessionmaker"]).sessionmaker(bind=engine)
        app.dependency_overrides[get_db] = make_db_override(session_factory)
        app.dependency_overrides.pop(get_current_user, None)

        client = TestClient(app)
        resp = client.get("/api/stats/ai-usage")
        assert resp.status_code == 401
        app.dependency_overrides.clear()
        engine.dispose()

    def test_with_auth(self, admin_test_client: TestClient):
        """登录后返回正确格式。"""
        resp = admin_test_client.get("/api/stats/ai-usage?days=7")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_tokens" in data
        assert "total_cost_usd" in data
        assert "total_calls" in data
        assert "by_dimension" in data
        assert "daily_trend" in data
        assert data["total_tokens"] == 0
        assert data["total_calls"] == 0

    def test_invalid_days(self, admin_test_client: TestClient):
        """days 参数校验。"""
        resp = admin_test_client.get("/api/stats/ai-usage?days=0")
        assert resp.status_code == 422
        resp = admin_test_client.get("/api/stats/ai-usage?days=100")
        assert resp.status_code == 422
