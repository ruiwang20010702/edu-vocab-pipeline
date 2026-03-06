"""FastAPI 依赖注入."""

from collections.abc import Generator
from typing import Callable

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from vocab_qc.core.db import SyncSessionLocal
from vocab_qc.core.models.user import User
from vocab_qc.core.services import auth_service
from vocab_qc.core.services.qc_service import QcService
from vocab_qc.core.services.review_service import ReviewService

security = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """从 Bearer token 解析当前用户。"""
    if credentials is None:
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    try:
        payload = auth_service.decode_jwt(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="认证令牌无效或已过期")

    user = db.query(User).filter_by(id=payload.get("user_id")).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已停用")
    return user


def require_role(*roles: str) -> Callable:
    """角色检查工厂函数。返回一个依赖，要求 current_user 拥有指定角色之一。"""

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="权限不足")
        return current_user

    return role_checker


def get_review_service() -> ReviewService:
    return ReviewService()


def get_qc_service() -> QcService:
    return QcService()
