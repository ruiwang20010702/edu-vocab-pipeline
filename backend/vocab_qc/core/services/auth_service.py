"""认证服务: 验证码生成/校验、JWT 签发/解析、邮件发送."""

import hashlib
import secrets
import smtplib
import string
from datetime import UTC, datetime, timedelta
from email.mime.text import MIMEText
from typing import Any

import jwt
from jwt.exceptions import InvalidTokenError as JWTError  # noqa: F401
from sqlalchemy import update
from sqlalchemy.orm import Session

from vocab_qc.core.config import settings
from vocab_qc.core.models.user import User, VerificationCode


def _hash_code(code: str) -> str:
    """SHA-256 哈希验证码。"""
    return hashlib.sha256(code.encode()).hexdigest()


_warned_empty_whitelist = False


def validate_email_domain(email: str) -> bool:
    """检查邮箱是否在白名单域名中。白名单为空时允许所有域名（并发出警告）。"""
    global _warned_empty_whitelist  # noqa: PLW0603
    if not settings.allowed_email_domains:
        if not _warned_empty_whitelist:
            import logging
            logging.getLogger(__name__).warning(
                "ALLOWED_EMAIL_DOMAINS 为空，所有邮箱域名均可注册登录"
            )
            _warned_empty_whitelist = True
        return True
    domain = email.split("@")[-1]
    return domain in settings.allowed_email_domains


def generate_code(session: Session, email: str) -> str:
    """生成 6 位验证码，hash 后存入数据库，返回明文用于发送。"""
    # 清理该邮箱的过期验证码
    now = datetime.now(UTC)
    session.query(VerificationCode).filter(
        VerificationCode.email == email,
        VerificationCode.expires_at < now,
    ).delete(synchronize_session=False)

    code = "".join(secrets.choice(string.digits) for _ in range(6))
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.verification_code_expire_minutes)
    record = VerificationCode(
        email=email,
        code=_hash_code(code),
        expires_at=expires_at,
    )
    session.add(record)
    session.flush()
    return code


_MAX_VERIFY_ATTEMPTS = 5


def verify_code(session: Session, email: str, code: str) -> bool:
    """校验验证码（hash 比对 + 未过期 + 未使用 + 尝试次数限制）。成功则标记 used=True。"""
    now = datetime.now(UTC)

    # 获取最近一条未使用、未过期的验证码
    record = (
        session.query(VerificationCode)
        .filter_by(email=email, used=False)
        .filter(VerificationCode.expires_at > now)
        .order_by(VerificationCode.created_at.desc())
        .first()
    )
    if record is None:
        return False

    # 原子递增尝试次数 + 上限检查
    result = session.execute(
        update(VerificationCode)
        .where(VerificationCode.id == record.id, VerificationCode.attempts < _MAX_VERIFY_ATTEMPTS)
        .values(attempts=VerificationCode.attempts + 1)
    )
    if result.rowcount == 0:
        return False
    session.flush()

    code_hash = _hash_code(code)
    if record.code != code_hash:
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
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_jwt(token: str) -> dict[str, Any]:
    """解析并验证 JWT。无效时抛出 JWTError。"""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def send_email(to: str, code: str) -> None:
    """通过 SMTP 发送验证码邮件。"""
    if not settings.smtp_host:
        raise RuntimeError("SMTP 未配置，无法发送验证码")

    subject = "词汇质检系统 - 登录验证码"
    body = f"您的验证码是：{code}\n\n有效期 {settings.verification_code_expire_minutes} 分钟。"
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email
    msg["To"] = to

    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, [to], msg.as_string())
