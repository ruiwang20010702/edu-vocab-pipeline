"""仪表板统计 Pydantic 模型."""

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
