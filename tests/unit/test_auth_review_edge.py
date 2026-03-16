"""认证与审核边界场景测试."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session
from vocab_qc.core.models import (
    ContentItem,
    QcStatus,
    ReviewItem,
    ReviewReason,
    ReviewStatus,
    Word,
)
from vocab_qc.core.models.user import User, VerificationCode
from vocab_qc.core.services.auth_service import _MAX_VERIFY_ATTEMPTS, _hash_code, verify_code
from vocab_qc.core.services.review_service import ReviewService

# ---------------------------------------------------------------------------
# L1: 验证码失败次数限制 —— 连续输错 5 次后，正确验证码也被拒绝
# ---------------------------------------------------------------------------


class TestVerificationCodeAttemptLimit:
    """验证码尝试次数上限测试。"""

    def _create_code(self, db_session: Session, email: str, plain_code: str) -> VerificationCode:
        """在数据库中插入一条未使用、未过期的验证码记录。"""
        record = VerificationCode(
            email=email,
            code=_hash_code(plain_code),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db_session.add(record)
        db_session.flush()
        return record

    def test_wrong_attempts_exhaust_limit(self, db_session: Session):
        """连续 5 次错误验证后，即使输入正确验证码也应被拒绝。"""
        email = "limit-test@example.com"
        correct_code = "123456"
        self._create_code(db_session, email, correct_code)

        # 连续输入 _MAX_VERIFY_ATTEMPTS 次错误验证码
        for i in range(_MAX_VERIFY_ATTEMPTS):
            result = verify_code(db_session, email, "000000")
            assert result is False, f"第 {i + 1} 次错误验证应返回 False"

        # 此时尝试次数已达上限，正确验证码也应被拒绝
        result = verify_code(db_session, email, correct_code)
        assert result is False, "尝试次数达上限后，正确验证码也应被拒绝"

    def test_correct_code_before_limit(self, db_session: Session):
        """在未达到上限前，正确验证码应通过。"""
        email = "before-limit@example.com"
        correct_code = "654321"
        self._create_code(db_session, email, correct_code)

        # 输入 4 次错误验证码（未达上限）
        for _ in range(_MAX_VERIFY_ATTEMPTS - 1):
            verify_code(db_session, email, "999999")

        # 第 5 次输入正确验证码，应通过
        result = verify_code(db_session, email, correct_code)
        assert result is True, "未达上限前，正确验证码应通过"

    def test_attempts_field_increments(self, db_session: Session):
        """每次验证尝试后 attempts 字段应递增。"""
        email = "increment@example.com"
        correct_code = "111111"
        record = self._create_code(db_session, email, correct_code)

        assert record.attempts == 0

        verify_code(db_session, email, "wrong1")
        db_session.refresh(record)
        assert record.attempts == 1

        verify_code(db_session, email, "wrong2")
        db_session.refresh(record)
        assert record.attempts == 2


# ---------------------------------------------------------------------------
# M12: manual_edit 更新 content_cn 字段
# ---------------------------------------------------------------------------


class TestManualEditContentCn:
    """审核服务 manual_edit 对 content_cn 的修改测试。"""

    def _setup_review(self, db_session: Session) -> tuple[ReviewItem, ContentItem]:
        """创建一个待审核的 ContentItem + ReviewItem。"""
        word = Word(word="apple")
        db_session.add(word)
        db_session.flush()

        content = ContentItem(
            word_id=word.id,
            meaning_id=None,
            dimension="sentence",
            content="I like apples.",
            content_cn="我喜欢苹果。",
            qc_status=QcStatus.LAYER1_FAILED.value,
        )
        db_session.add(content)
        db_session.flush()

        review = ReviewItem(
            content_item_id=content.id,
            word_id=word.id,
            meaning_id=None,
            dimension="sentence",
            reason=ReviewReason.LAYER1_FAILED.value,
            status=ReviewStatus.PENDING.value,
        )
        db_session.add(review)
        db_session.flush()

        return review, content

    def test_manual_edit_updates_content_cn(self, db_session: Session):
        """manual_edit 传入 new_content_cn 应更新 ContentItem.content_cn。"""
        review, content = self._setup_review(db_session)
        service = ReviewService()

        new_cn = "我非常喜欢苹果。"
        service.manual_edit(
            db_session,
            review_id=review.id,
            reviewer="editor@test.com",
            new_content="I really like apples.",
            new_content_cn=new_cn,
        )

        db_session.refresh(content)
        assert content.content_cn == new_cn
        assert content.content == "I really like apples."

    def test_manual_edit_without_content_cn_preserves_original(self, db_session: Session):
        """manual_edit 不传 new_content_cn 时，原 content_cn 应保持不变。"""
        review, content = self._setup_review(db_session)
        original_cn = content.content_cn
        service = ReviewService()

        service.manual_edit(
            db_session,
            review_id=review.id,
            reviewer="editor@test.com",
            new_content="I enjoy apples.",
        )

        db_session.refresh(content)
        assert content.content_cn == original_cn, "不传 new_content_cn 时原值应保持不变"

    def test_manual_edit_runs_qc(self, db_session: Session):
        """manual_edit 后自动运行质检，状态不再是 pending。"""
        review, content = self._setup_review(db_session)
        service = ReviewService()

        result = service.manual_edit(
            db_session,
            review_id=review.id,
            reviewer="editor@test.com",
            new_content="I enjoy apples.",
            new_content_cn="我享受苹果。",
        )

        assert result["success"] is True
        assert "qc_passed" in result
        db_session.refresh(content)
        assert content.qc_status != QcStatus.PENDING.value


# ---------------------------------------------------------------------------
# M15: 停用用户无法通过 verify 端点登录
# ---------------------------------------------------------------------------


class TestDeactivatedUserAccess:
    """停用用户访问限制测试。"""

    def test_deactivated_user_cannot_login_via_verify(self, db_session: Session):
        """is_active=False 的用户在 verify 端点应被拒绝（403）。"""
        from fastapi.testclient import TestClient
        from vocab_qc.api.main import app

        email = "deactivated@example.com"
        correct_code = "888888"

        # 创建停用用户
        user = User(email=email, name="Deactivated", role="reviewer", is_active=False)
        db_session.add(user)
        db_session.flush()

        # 创建有效验证码
        record = VerificationCode(
            email=email,
            code=_hash_code(correct_code),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db_session.add(record)
        db_session.flush()

        # 使用依赖覆盖注入测试数据库 session
        from vocab_qc.api.deps import get_db

        def _override_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_db
        try:
            client = TestClient(app)
            response = client.post("/api/auth/verify", json={"email": email, "code": correct_code})
            assert response.status_code == 403
            assert "停用" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_active_user_can_login_via_verify(self, db_session: Session):
        """is_active=True 的用户应能正常通过 verify 端点登录。"""
        from fastapi.testclient import TestClient
        from vocab_qc.api.main import app

        email = "active@example.com"
        correct_code = "777777"

        # 创建活跃用户
        user = User(email=email, name="Active", role="reviewer", is_active=True)
        db_session.add(user)
        db_session.flush()

        # 创建有效验证码
        record = VerificationCode(
            email=email,
            code=_hash_code(correct_code),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db_session.add(record)
        db_session.flush()

        from vocab_qc.api.deps import get_db

        def _override_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_db
        try:
            client = TestClient(app)
            response = client.post("/api/auth/verify", json={"email": email, "code": correct_code})
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["user_name"] == "Active"
        finally:
            app.dependency_overrides.clear()
