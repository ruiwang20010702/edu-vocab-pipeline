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
    reviewer: Optional[str] = None
    note: Optional[str] = None


class RegenerateResponse(BaseModel):
    success: bool
    retry_count: int
    message: str


class ManualEditRequest(BaseModel):
    reviewer: Optional[str] = None
    new_content: Optional[str] = None
    new_content_cn: Optional[str] = None
    # 兼容前端字段名
    content: Optional[str] = None
    content_cn: Optional[str] = None

    @property
    def resolved_content(self) -> str:
        """优先使用 content，其次 new_content。"""
        return self.content or self.new_content or ""

    @property
    def resolved_content_cn(self) -> Optional[str]:
        return self.content_cn or self.new_content_cn
