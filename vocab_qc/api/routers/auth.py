"""认证 API 路由."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_db
from vocab_qc.api.schemas.auth import SendCodeRequest, TokenResponse, VerifyRequest
from vocab_qc.core.services import auth_service, user_service

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/send-code")
def send_code(request: SendCodeRequest, db: Session = Depends(get_db)):
    """发送验证码。"""
    if not auth_service.validate_email_domain(request.email):
        raise HTTPException(status_code=400, detail="邮箱域名不在白名单中")

    code = auth_service.generate_code(db, request.email)
    auth_service.send_email(request.email, code)
    return {"message": "验证码已发送"}


@router.post("/verify", response_model=TokenResponse)
def verify(request: VerifyRequest, db: Session = Depends(get_db)):
    """验证码登录。"""
    if not auth_service.verify_code(db, request.email, request.code):
        raise HTTPException(status_code=401, detail="验证码无效或已过期")

    user = user_service.get_user_by_email(db, request.email)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在，请联系管理员添加")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已停用")

    user.last_login_at = datetime.now(UTC)
    db.flush()

    token = auth_service.create_jwt(user)
    return TokenResponse(
        access_token=token,
        user_name=user.name,
        user_role=user.role,
    )
