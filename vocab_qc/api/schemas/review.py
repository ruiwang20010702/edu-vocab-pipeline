"""审核相关 Pydantic 模型."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


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

    model_config = {"from_attributes": True}


class ApproveRequest(BaseModel):
    reviewer: str
    note: Optional[str] = None


class RegenerateResponse(BaseModel):
    success: bool
    retry_count: int
    message: str


class ManualEditRequest(BaseModel):
    reviewer: str
    new_content: str
    new_content_cn: Optional[str] = None
