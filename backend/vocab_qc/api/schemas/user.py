"""用户相关 Pydantic 模型."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str
    role: str = "reviewer"


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    created_at: Optional[datetime]
    last_login_at: Optional[datetime]

    model_config = {"from_attributes": True}
