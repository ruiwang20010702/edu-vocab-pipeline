"""仪表板统计 API 路由."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_current_user, get_db
from vocab_qc.api.schemas.stats import AiUsageStatsResponse, DashboardStatsResponse
from vocab_qc.core.models.user import User
from vocab_qc.core.services import stats_service

router = APIRouter(prefix="/api", tags=["统计"])


@router.get("/stats", response_model=DashboardStatsResponse)
def get_stats(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """获取仪表板统计数据。"""
    return stats_service.get_dashboard_stats(db)


@router.get("/stats/ai-usage", response_model=AiUsageStatsResponse)
def get_ai_usage_stats(
    days: int = Query(default=7, ge=1, le=90, description="统计天数"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """获取 AI 用量统计数据。"""
    return stats_service.get_ai_usage_stats(db, days=days)
