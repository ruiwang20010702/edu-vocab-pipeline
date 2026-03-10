"""生产批次信息 Pydantic 模型（区别于审核批次）."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BatchInfoResponse(BaseModel):
    id: str
    name: str
    status: str
    total_words: int
    processed_words: int
    pass_rate: Optional[float]
    failed_count: int = 0
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}
