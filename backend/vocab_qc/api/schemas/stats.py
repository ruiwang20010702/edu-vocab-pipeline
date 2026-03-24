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


# --- 生产记录（按 Package 聚合 AI 用量）---


class ProductionRecord(BaseModel):
    batch_id: int
    batch_name: str
    word_count: int
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    gemini_input_tokens: int = 0
    gemini_output_tokens: int = 0
    gpt_input_tokens: int = 0
    gpt_output_tokens: int = 0


class ProductionRecordTotals(BaseModel):
    words: int = 0
    gemini_input: int = 0
    gemini_output: int = 0
    gpt_input: int = 0
    gpt_output: int = 0


class ProductionRecordsResponse(BaseModel):
    records: list[ProductionRecord] = []
    totals: ProductionRecordTotals = ProductionRecordTotals()
