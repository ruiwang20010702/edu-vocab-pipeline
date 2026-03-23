"""仪表板统计 Pydantic 模型."""

from typing import Optional

from pydantic import BaseModel


class IssueCount(BaseModel):
    field: str
    dimension: str
    count: int


class DashboardStatsResponse(BaseModel):
    total_words: int
    approved_count: int
    pending_count: int
    rejected_count: int
    pass_rate: float
    issues: list[IssueCount] = []


# --- AI 用量统计 ---


class AiUsageByDimension(BaseModel):
    dimension: Optional[str]
    phase: str
    total_tokens: int
    estimated_cost_usd: Optional[float]
    call_count: int


class AiUsageDailyTrend(BaseModel):
    date: str
    total_tokens: int
    call_count: int


class AiUsageStatsResponse(BaseModel):
    total_tokens: int
    total_cost_usd: Optional[float]
    total_calls: int
    by_dimension: list[AiUsageByDimension] = []
    daily_trend: list[AiUsageDailyTrend] = []
