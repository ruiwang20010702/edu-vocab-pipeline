"""审核流程集成测试."""

import pytest
from vocab_qc.core.models import (
    AuditLogV2,
    ContentItem,
    QcStatus,
    ReviewReason,
    ReviewResolution,
    ReviewStatus,
)
from vocab_qc.core.services.review_service import ReviewService


@pytest.fixture
def review_service():
    return ReviewService(max_retries=3)


@pytest.fixture
def review_with_item(db_session, sample_word, review_service):
    """创建一个带审核项的 fixture."""
    chunk = sample_word["chunks"][0]
    chunk.qc_status = QcStatus.LAYER1_FAILED.value
    db_session.flush()

    review = review_service.create_review_item(db_session, chunk, ReviewReason.LAYER1_FAILED)
    return {"review": review, "content_item": chunk}


def test_create_review_item(db_session, sample_word, review_service):
    chunk = sample_word["chunks"][0]
    review = review_service.create_review_item(db_session, chunk, ReviewReason.LAYER1_FAILED)

    assert review.id is not None
    assert review.status == ReviewStatus.PENDING.value
    assert review.dimension == "chunk"
    assert review.reason == ReviewReason.LAYER1_FAILED.value


def test_approve(db_session, review_with_item, review_service):
    review = review_with_item["review"]
    result = review_service.approve(db_session, review.id, reviewer="tester")

    assert result.status == ReviewStatus.RESOLVED.value
    assert result.resolution == ReviewResolution.APPROVED.value
    assert result.reviewer == "tester"

    content_item = db_session.query(ContentItem).filter_by(id=review.content_item_id).one()
    assert content_item.qc_status == QcStatus.APPROVED.value

    # 验证审计日志
    logs = db_session.query(AuditLogV2).filter_by(entity_type="review_item").all()
    assert len(logs) >= 1


def test_regenerate_first_time(db_session, review_with_item, review_service):
    from unittest.mock import patch

    review = review_with_item["review"]

    # Mock AI 生成器，避免真实 API 调用
    def _fake_generate(self, *, word, meaning=None, pos=None, session=None):
        return {"content": f"mock chunk for {word}"}

    with patch(
        "vocab_qc.core.services.review_service.ReviewService._do_regenerate",
        side_effect=lambda session, ci: _mock_regenerate(ci),
    ):
        result = review_service.regenerate(db_session, review.id, reviewer="tester")

    assert result["success"] is True
    assert result["retry_count"] == 1

    content_item = db_session.query(ContentItem).filter_by(id=review.content_item_id).one()
    assert content_item.retry_count == 1


def _mock_regenerate(content_item):
    """模拟 _do_regenerate：填充假内容。"""
    content_item.content = "mock regenerated content"


def test_regenerate_max_retries(db_session, review_with_item, review_service):
    content_item = review_with_item["content_item"]

    # 手动设置计数到最大
    counter = review_service._get_or_create_counter(db_session, content_item)
    counter.count = 3
    content_item.retry_count = 3
    db_session.flush()

    # 再创建一个新的审核项
    review2 = review_service.create_review_item(db_session, content_item, ReviewReason.LAYER1_FAILED)
    result = review_service.regenerate(db_session, review2.id, reviewer="tester")

    assert result["success"] is False
    assert "最大重试次数" in result["message"]


def test_manual_edit(db_session, review_with_item, review_service):
    review = review_with_item["review"]
    result = review_service.manual_edit(
        db_session,
        review.id,
        reviewer="tester",
        new_content="be kind to others",
    )

    assert result["success"] is True
    assert "qc_passed" in result

    content_item = db_session.query(ContentItem).filter_by(id=review.content_item_id).one()
    assert content_item.content == "be kind to others"
    # 人工修改后自动质检，状态不再是 pending
    assert content_item.qc_status != QcStatus.PENDING.value


def test_get_pending_reviews(db_session, sample_word, review_service):
    # 创建多个审核项
    for chunk in sample_word["chunks"]:
        review_service.create_review_item(db_session, chunk, ReviewReason.LAYER1_FAILED)
    for sentence in sample_word["sentences"]:
        review_service.create_review_item(db_session, sentence, ReviewReason.SAMPLING)
    db_session.flush()

    # 获取全部
    all_pending, total = review_service.get_pending_reviews(db_session)
    assert len(all_pending) == 4
    assert total == 4

    # 按维度筛选
    chunk_reviews, chunk_total = review_service.get_pending_reviews(db_session, dimension="chunk")
    assert len(chunk_reviews) == 2
    assert chunk_total == 2

    sentence_reviews, sentence_total = review_service.get_pending_reviews(db_session, dimension="sentence")
    assert len(sentence_reviews) == 2
    assert sentence_total == 2
