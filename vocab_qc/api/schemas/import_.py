"""导入相关 Pydantic 模型."""

from pydantic import BaseModel


class ImportResponse(BaseModel):
    batch_id: str
    word_count: int
    message: str
