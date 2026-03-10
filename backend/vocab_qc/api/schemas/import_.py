"""导入相关 Pydantic 模型."""

from pydantic import BaseModel


class ImportResponse(BaseModel):
    batch_id: str
    word_count: int
    message: str


class PreviewRow(BaseModel):
    word: str
    pos: str
    definition: str
    source: str


class PreviewResponse(BaseModel):
    rows: list[PreviewRow]
    total_count: int
