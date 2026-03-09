"""Prompt API 响应模型."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PromptResponse(BaseModel):
    id: int
    name: str
    category: str
    dimension: str
    model: str
    content: str
    is_active: bool
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PromptCreateRequest(BaseModel):
    name: str
    category: str  # generation / qa
    dimension: str  # chunk / sentence / mnemonic
    model: str = "gpt-4o-mini"
    content: str = ""


class PromptUpdateRequest(BaseModel):
    name: Optional[str] = None
    model: Optional[str] = None
    content: Optional[str] = None
    is_active: Optional[bool] = None
