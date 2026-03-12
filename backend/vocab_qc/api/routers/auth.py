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

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

router = APIRouter(prefix="/api/auth", tags=["认证"])


def _key_by_email(request: Request) -> str:
    """按邮箱限速：解析请求体中的 email 字段。"""
    import json as _json
    try:
        raw = getattr(request, "_body", None) or b""
        if not raw:
            return get_remote_address(request)
        body = _json.loads(raw)
        return body.get("email", get_remote_address(request))
    except Exception:
        return get_remote_address(request)


@router.post("/send-code")
@limiter.limit("3/minute")
@limiter.limit("3/minute", key_func=_key_by_email)
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
@limiter.limit("5/minute", key_func=_key_by_email)
def verify(request: Request, body: VerifyRequest, db: Session = Depends(get_db)):
    """验证码登录。"""
    if not auth_service.verify_code(db, body.email, body.code):
        raise HTTPException(status_code=401, detail="验证码无效或已过期")

    user = user_service.get_user_by_email(db, body.email)
    if user is None:
        # 首次登录自动注册为 reviewer；admin 须通过 CLI `vocab create-admin` 创建
        name = body.email.split("@")[0]
        user = user_service.create_user(db, email=body.email, name=name, role="reviewer")
        logger.info("自动注册新用户: %s (角色: reviewer)", body.email)
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
