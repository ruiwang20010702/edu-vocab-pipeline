"""认证服务单元测试."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from vocab_qc.core.models.user import User, VerificationCode
from vocab_qc.core.services import auth_service


class TestGenerateCode:
    def test_generates_6_digit_code(self, db_session: Session):
        code = auth_service.generate_code(db_session, "test@example.com")
        assert len(code) == 6
        assert code.isdigit()

    def test_stores_hashed_code_in_db(self, db_session: Session):
        code = auth_service.generate_code(db_session, "test@example.com")
        record = db_session.query(VerificationCode).filter_by(email="test@example.com").first()
        assert record is not None
        assert record.used is False
        # DB stores hash, not plaintext
        assert record.code != code
        assert record.code == auth_service._hash_code(code)


class TestVerifyCode:
    def test_valid_code(self, db_session: Session):
        code = auth_service.generate_code(db_session, "test@example.com")
        result = auth_service.verify_code(db_session, "test@example.com", code)
        assert result is True

    def test_marks_code_as_used(self, db_session: Session):
        code = auth_service.generate_code(db_session, "test@example.com")
        auth_service.verify_code(db_session, "test@example.com", code)
        code_hash = auth_service._hash_code(code)
        record = db_session.query(VerificationCode).filter_by(email="test@example.com", code=code_hash).first()
        assert record.used is True

    def test_replay_rejected(self, db_session: Session):
        """同一个验证码不能二次使用。"""
        code = auth_service.generate_code(db_session, "test@example.com")
        auth_service.verify_code(db_session, "test@example.com", code)
        result = auth_service.verify_code(db_session, "test@example.com", code)
        assert result is False

    def test_wrong_code(self, db_session: Session):
        auth_service.generate_code(db_session, "test@example.com")
        result = auth_service.verify_code(db_session, "test@example.com", "000000")
        assert result is False

    def test_expired_code(self, db_session: Session):
        code = auth_service.generate_code(db_session, "test@example.com")
        # 手动将过期时间设为过去
        code_hash = auth_service._hash_code(code)
        record = db_session.query(VerificationCode).filter_by(email="test@example.com", code=code_hash).first()
        record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db_session.flush()

        result = auth_service.verify_code(db_session, "test@example.com", code)
        assert result is False


class TestJwt:
    def test_create_and_decode(self, db_session: Session):
        user = User(id=1, email="test@example.com", name="Test", role="admin")
        token = auth_service.create_jwt(user)
        payload = auth_service.decode_jwt(token)
        assert payload["sub"] == "test@example.com"
        assert payload["user_id"] == 1
        assert payload["role"] == "admin"

    def test_invalid_token_raises(self):
        from jwt.exceptions import InvalidTokenError

        with pytest.raises(InvalidTokenError):
            auth_service.decode_jwt("invalid.token.here")


class TestEmailDomainValidation:
    def test_empty_whitelist_allows_all(self):
        with patch.object(auth_service.settings, "allowed_email_domains", []):
            assert auth_service.validate_email_domain("any@domain.com") is True

    def test_whitelisted_domain_allowed(self):
        with patch.object(auth_service.settings, "allowed_email_domains", ["company.com"]):
            assert auth_service.validate_email_domain("user@company.com") is True

    def test_non_whitelisted_domain_rejected(self):
        with patch.object(auth_service.settings, "allowed_email_domains", ["company.com"]):
            assert auth_service.validate_email_domain("user@other.com") is False
