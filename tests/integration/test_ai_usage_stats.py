"""AI 用量统计集成测试."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from vocab_qc.core.models.quality_layer import AiUsageLog
from vocab_qc.core.services.stats_service import get_ai_usage_stats, stats_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    """每个测试清空缓存。"""
    stats_cache.invalidate("ai_usage_stats_7")
    stats_cache.invalidate("ai_usage_stats_30")
    yield
    stats_cache.invalidate("ai_usage_stats_7")
    stats_cache.invalidate("ai_usage_stats_30")


class TestGetAiUsageStats:
    """get_ai_usage_stats 统计查询。"""

    def test_empty(self, db_session: Session):
        """无数据时返回零值。"""
        result = get_ai_usage_stats(db_session, days=7)
        assert result["total_tokens"] == 0
        assert result["total_cost_usd"] is None
        assert result["total_calls"] == 0
        assert result["by_dimension"] == []
        assert result["daily_trend"] == []

    def test_with_data(self, db_session: Session):
        """插入测试数据后验证聚合。"""
        db_session.add(AiUsageLog(
            phase="generation",
            dimension="chunk",
            ai_model="gemini-2.0-flash",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_cost_usd=0.00003,
        ))
        db_session.add(AiUsageLog(
            phase="qc_layer2",
            dimension=None,
            ai_model="gemini-2.0-flash",
            prompt_tokens=200,
            completion_tokens=80,
            total_tokens=280,
            estimated_cost_usd=0.00005,
        ))
        db_session.flush()

        result = get_ai_usage_stats(db_session, days=7)
        assert result["total_tokens"] == 430
        assert result["total_cost_usd"] is not None
        assert result["total_calls"] == 2
        assert len(result["by_dimension"]) == 2

    def test_old_data_excluded(self, db_session: Session):
        """超出时间范围的数据不计入。"""
        old_time = datetime.now(UTC) - timedelta(days=10)
        log = AiUsageLog(
            phase="generation",
            dimension="chunk",
            ai_model="test-model",
            prompt_tokens=999,
            completion_tokens=999,
            total_tokens=1998,
        )
        db_session.add(log)
        db_session.flush()
        # 手动修改 created_at（SQLite 不支持 server_default func.now() 在 UPDATE 中）
        db_session.execute(
            AiUsageLog.__table__.update()
            .where(AiUsageLog.__table__.c.id == log.id)
            .values(created_at=old_time)
        )
        db_session.flush()

        result = get_ai_usage_stats(db_session, days=7)
        assert result["total_tokens"] == 0
        assert result["total_calls"] == 0

    def test_daily_trend(self, db_session: Session):
        """日趋势分组正确。"""
        db_session.add(AiUsageLog(
            phase="generation",
            dimension="sentence",
            ai_model="test-model",
            prompt_tokens=50,
            completion_tokens=25,
            total_tokens=75,
        ))
        db_session.flush()

        result = get_ai_usage_stats(db_session, days=7)
        assert len(result["daily_trend"]) >= 1
        today_str = datetime.now(UTC).strftime("%Y-%m-%d")
        dates = [t["date"] for t in result["daily_trend"]]
        assert today_str in dates
