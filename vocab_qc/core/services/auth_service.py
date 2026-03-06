"""认证服务: 验证码生成/校验、JWT 签发/解析、邮件发送."""

import random
import smtplib
import string
from datetime import UTC, datetime, timedelta
from email.mime.text import MIMEText
from typing import Any

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from vocab_qc.core.config import settings
from vocab_qc.core.models.user import User, VerificationCode


def validate_email_domain(email: str) -> bool:
    """检查邮箱是否在白名单域名中。白名单为空时允许所有域名。"""
    if not settings.allowed_email_domains:
        return True
    domain = email.split("@")[-1]
    return domain in settings.allowed_email_domains


def generate_code(session: Session, email: str) -> str:
    """生成 6 位验证码并存入数据库。"""
    code = "".join(random.choices(string.digits, k=6))
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.verification_code_expire_minutes)
    record = VerificationCode(
        email=email,
        code=code,
        expires_at=expires_at,
    )
    session.add(record)
    session.flush()
    return code


def verify_code(session: Session, email: str, code: str) -> bool:
    """校验验证码（未过期 + 未使用）。成功则标记 used=True。"""
    now = datetime.now(UTC)
    record = (
        session.query(VerificationCode)
        .filter_by(email=email, code=code, used=False)
        .filter(VerificationCode.expires_at > now)
        .order_by(VerificationCode.created_at.desc())
        .first()
    )
    if record is None:
        return False
    record.used = True
    session.flush()
    return True


def create_jwt(user: User) -> str:
    """签发 JWT。"""
    expire = datetime.now(UTC) + timedelta(hours=settings.jwt_expire_hours)
    payload: dict[str, Any] = {
        "sub": user.email,
        "user_id": user.id,
        "role": user.role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_jwt(token: str) -> dict[str, Any]:
    """解析并验证 JWT。无效时抛出 JWTError。"""
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise


def send_email(to: str, code: str) -> None:
    """通过 SMTP 发送验证码邮件。"""
    if not settings.smtp_host:
        return

    subject = "词汇质检系统 - 登录验证码"
    body = f"您的验证码是：{code}\n\n有效期 {settings.verification_code_expire_minutes} 分钟。"
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email
    msg["To"] = to

    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as server:
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, [to], msg.as_string())
