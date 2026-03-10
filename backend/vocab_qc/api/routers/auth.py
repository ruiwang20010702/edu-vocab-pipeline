"""认证 API 路由."""

from datetime import UTC, datetime

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_db
from vocab_qc.api.schemas.auth import SendCodeRequest, TokenResponse, VerifyRequest
from vocab_qc.core.config import settings
from vocab_qc.core.models.user import User
from vocab_qc.core.services import auth_service, user_service

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/send-code")
@limiter.limit("3/minute")
def send_code(request: Request, body: SendCodeRequest, db: Session = Depends(get_db)):
    """发送验证码。"""
    if not auth_service.validate_email_domain(body.email):
        raise HTTPException(status_code=400, detail="邮箱域名不在白名单中")

    code = auth_service.generate_code(db, body.email)

    # 开发环境：验证码输出到日志，不依赖邮件
    if settings.env == "development":
        logger.warning("【开发模式】验证码: %s (邮箱: %s)", code, body.email)

    try:
        auth_service.send_email(body.email, code)
    except Exception:
        logger.warning("验证码发送失败", exc_info=True)
        if settings.env != "development":
            raise HTTPException(status_code=503, detail="验证码发送失败，请稍后重试")
        # 开发环境下邮件发送失败不阻断，验证码已在日志中
    db.commit()
    return {"message": "验证码已发送"}


@router.post("/verify", response_model=TokenResponse)
@limiter.limit("5/minute")
def verify(request: Request, body: VerifyRequest, db: Session = Depends(get_db)):
    """验证码登录。"""
    if not auth_service.verify_code(db, body.email, body.code):
        raise HTTPException(status_code=401, detail="验证码无效或已过期")

    user = user_service.get_user_by_email(db, body.email)
    if user is None:
        # 首次登录自动注册；如果系统无用户则为 admin，否则为 reviewer
        has_any_user = db.query(User).first() is not None
        role = "reviewer" if has_any_user else "admin"
        name = body.email.split("@")[0]
        user = user_service.create_user(db, email=body.email, name=name, role=role)
        logger.info("自动注册新用户: %s (角色: %s)", body.email, role)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已停用")

    user.last_login_at = datetime.now(UTC)
    db.flush()

    token = auth_service.create_jwt(user)
    db.commit()
    return TokenResponse(
        access_token=token,
        user_name=user.name,
        user_role=user.role,
    )
