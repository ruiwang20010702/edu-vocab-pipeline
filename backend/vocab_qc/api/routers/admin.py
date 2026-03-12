"""管理员 API 路由."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_current_user, get_db, require_role
from vocab_qc.api.schemas.user import CreateUserRequest, UpdateUserRequest, UserResponse
from vocab_qc.core.models.user import User
from vocab_qc.core.services import user_service

router = APIRouter(prefix="/api/admin", tags=["管理"])

# /api/users 独立路由（非 admin 前缀）
user_router = APIRouter(prefix="/api/users", tags=["用户"])


@router.post("/users", response_model=UserResponse)
def create_user(
    request: CreateUserRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """创建用户（仅管理员）。"""
    existing = user_service.get_user_by_email(db, request.email)
    if existing:
        raise HTTPException(status_code=409, detail="邮箱已注册")
    user = user_service.create_user(db, email=request.email, name=request.name, role=request.role)
    db.commit()
    return UserResponse.model_validate(user)


@router.get("/users", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """列出所有用户（仅管理员）。"""
    users = user_service.list_users(db)
    return [UserResponse.model_validate(u) for u in users]


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    request: UpdateUserRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """编辑用户（仅管理员）。"""
    try:
        user = user_service.update_user(
            db,
            user_id,
            name=request.name,
            role=request.role,
            is_active=request.is_active,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.commit()
    return UserResponse.model_validate(user)


@user_router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息。"""
    return UserResponse.model_validate(current_user)
