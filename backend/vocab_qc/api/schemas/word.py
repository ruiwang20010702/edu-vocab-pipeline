"""词汇查询 Pydantic 模型."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SourceResponse(BaseModel):
    id: int
    meaning_id: int
    source_name: str

    model_config = {"from_attributes": True}


class ContentItemResponse(BaseModel):
    id: int
    word_id: int
    meaning_id: Optional[int]
    dimension: str
    content: str
    content_cn: Optional[str]
    qc_status: str
    retry_count: int

    model_config = {"from_attributes": True}


class MeaningDetailResponse(BaseModel):
    id: int
    word_id: int
    pos: str
    definition: str
    sources: list[SourceResponse]
    chunk: Optional[ContentItemResponse] = None
    sentence: Optional[ContentItemResponse] = None
    mnemonics: list[ContentItemResponse] = []


class PhoneticResponse(BaseModel):
    id: int
    word_id: int
    ipa: str
    syllables: str

    model_config = {"from_attributes": True}


class QualityIssueResponse(BaseModel):
    id: int
    content_item_id: int
    rule_id: str
    field: str
    message: str
    severity: str


class WordDetailResponse(BaseModel):
    id: int
    word: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    phonetics: list[PhoneticResponse]
    syllable: Optional[ContentItemResponse] = None
    completion_status: str = "in_progress"
    meanings: list[MeaningDetailResponse]
    issues: list[QualityIssueResponse] = []


class StatusCountsResponse(BaseModel):
    approved: int
    in_progress: int
    total: int


class PaginatedWordResponse(BaseModel):
    items: list[WordDetailResponse]
    total: int
    page: int
    limit: int
    status_counts: Optional[StatusCountsResponse] = None
