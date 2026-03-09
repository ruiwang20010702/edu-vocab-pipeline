"""质检相关 Pydantic 模型."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class QcRunRequest(BaseModel):
    layers: list[int] = Field(default=[1], description="要执行的质检层 [1, 2]")
    scope: Optional[str] = Field(default=None, description="范围筛选，如 'word_id:123'")
    dimension: Optional[str] = Field(default=None, description="维度筛选")
    strategy: Optional[str] = Field(default=None, description="AI 策略: per_rule/unified")


class QcRunResponse(BaseModel):
    run_id: Optional[str]
    total: int
    passed: int
    failed: int


class QcRunDetail(BaseModel):
    id: str
    layer: int
    scope: str
    status: str
    total_items: int
    passed_items: int
    failed_items: int
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    model_config = {"from_attributes": True}


class RuleResultResponse(BaseModel):
    id: int
    content_item_id: int
    rule_id: str
    dimension: str
    layer: int
    passed: bool
    detail: Optional[str]
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class QcSummaryItem(BaseModel):
    rule_id: str
    dimension: str
    total: int
    passed: int
    failed: int
    pass_rate: float
