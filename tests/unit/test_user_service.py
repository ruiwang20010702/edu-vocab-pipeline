"""用户管理服务单元测试."""

import pytest
from sqlalchemy.orm import Session

from vocab_qc.core.services import user_service


class TestCreateUser:
    def test_creates_user(self, db_session: Session):
        user = user_service.create_user(db_session, email="a@test.com", name="Alice", role="admin")
        assert user.id is not None
        assert user.email == "a@test.com"
        assert user.name == "Alice"
        assert user.role == "admin"
        assert user.is_active is True

    def test_default_role_is_reviewer(self, db_session: Session):
        user = user_service.create_user(db_session, email="b@test.com", name="Bob")
        assert user.role == "reviewer"


class TestGetUserByEmail:
    def test_found(self, db_session: Session):
        user_service.create_user(db_session, email="c@test.com", name="Charlie")
        result = user_service.get_user_by_email(db_session, "c@test.com")
        assert result is not None
        assert result.name == "Charlie"

    def test_not_found(self, db_session: Session):
        result = user_service.get_user_by_email(db_session, "nonexist@test.com")
        assert result is None


class TestListUsers:
    def test_returns_all(self, db_session: Session):
        user_service.create_user(db_session, email="d@test.com", name="Dave")
        user_service.create_user(db_session, email="e@test.com", name="Eve")
        users = user_service.list_users(db_session)
        emails = [u.email for u in users]
        assert "d@test.com" in emails
        assert "e@test.com" in emails


class TestDeactivateUser:
    def test_deactivates(self, db_session: Session):
        user = user_service.create_user(db_session, email="f@test.com", name="Frank")
        result = user_service.deactivate_user(db_session, user.id)
        assert result.is_active is False

    def test_nonexistent_raises(self, db_session: Session):
        from sqlalchemy.exc import NoResultFound

        with pytest.raises(NoResultFound):
            user_service.deactivate_user(db_session, 99999)
