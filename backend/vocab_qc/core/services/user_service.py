"""用户管理服务."""

from typing import Optional

from sqlalchemy.orm import Session

from vocab_qc.core.models.user import User


def create_user(session: Session, email: str, name: str, role: str = "reviewer") -> User:
    """创建用户。"""
    user = User(email=email, name=name, role=role)
    session.add(user)
    session.flush()
    return user


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    """按邮箱查询用户。"""
    return session.query(User).filter_by(email=email).first()


def list_users(session: Session) -> list[User]:
    """列出所有用户。"""
    return session.query(User).order_by(User.created_at).all()


def deactivate_user(session: Session, user_id: int) -> User:
    """停用用户。"""
    user = session.query(User).filter_by(id=user_id).one()
    user.is_active = False
    session.flush()
    return user
