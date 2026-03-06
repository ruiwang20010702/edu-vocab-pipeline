"""批次相关 Pydantic 模型."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BatchResponse(BaseModel):
    id: int
    user_id: int
    status: str
    word_count: int
    reviewed_count: int
    created_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class BatchWordItem(BaseModel):
    review_id: int
    content_item_id: int
    dimension: str
    reason: str
    status: str
    resolution: Optional[str]


class BatchWordResponse(BaseModel):
    word_id: int
    items: list[BatchWordItem]


class BatchDetailResponse(BaseModel):
    batch: BatchResponse
    words: list[BatchWordResponse]


class ReviewerStat(BaseModel):
    user_id: int
    batch_count: int
    reviewed_words: int


class BatchStatsResponse(BaseModel):
    pending_words: int
    reviewed_words: int
    reviewers: list[ReviewerStat]
