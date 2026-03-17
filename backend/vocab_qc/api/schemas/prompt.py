"""Prompt API 响应模型."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

_DIMENSION_LITERAL = Literal[
    "meaning", "phonetic", "syllable", "chunk", "sentence",
    "mnemonic_root_affix", "mnemonic_word_in_word",
    "mnemonic_sound_meaning", "mnemonic_exam_app",
]


class PromptResponse(BaseModel):
    id: int
    name: str
    category: str
    dimension: str
    model: str
    content: str
    is_active: bool
    ai_api_base_url: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PromptCreateRequest(BaseModel):
    name: str
    category: Literal["generation", "quality"]
    dimension: _DIMENSION_LITERAL
    model: str = "gemini-3-flash-preview|efficiency"
    content: str = ""
    ai_api_base_url: Optional[str] = None


class PromptUpdateRequest(BaseModel):
    name: Optional[str] = None
    model: Optional[str] = None
    content: Optional[str] = None
    is_active: Optional[bool] = None
    ai_api_base_url: Optional[str] = None
