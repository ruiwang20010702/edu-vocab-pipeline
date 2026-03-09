"""审核相关 Pydantic 模型."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class EmbeddedWord(BaseModel):
    id: int
    word: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EmbeddedContentItem(BaseModel):
    id: int
    word_id: int
    meaning_id: Optional[int]
    dimension: str
    content: str
    content_cn: Optional[str]
    qc_status: str
    retry_count: int

    model_config = {"from_attributes": True}


class EmbeddedIssue(BaseModel):
    id: int
    content_item_id: int
    rule_code: str
    field: str
    message: str
    severity: str


class ReviewItemResponse(BaseModel):
    id: int
    content_item_id: int
    word_id: int
    meaning_id: Optional[int]
    dimension: str
    reason: str
    priority: int
    status: str
    resolution: Optional[str]
    reviewer: Optional[str]
    review_note: Optional[str]
    resolved_at: Optional[datetime]
    created_at: Optional[datetime]

    # 嵌套对象 — 供前端直接使用
    content_item: Optional[EmbeddedContentItem] = None
    word: Optional[EmbeddedWord] = None
    issues: list[EmbeddedIssue] = []

    model_config = {"from_attributes": True}


class ApproveRequest(BaseModel):
    note: Optional[str] = None


class RegenerateResponse(BaseModel):
    success: bool
    retry_count: int
    message: str


class ReviewListResponse(BaseModel):
    items: list[ReviewItemResponse]
    total: int
    limit: int
    offset: int


class ManualEditRequest(BaseModel):
    content: str
    content_cn: Optional[str] = None
