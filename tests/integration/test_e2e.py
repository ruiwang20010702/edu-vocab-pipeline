"""端到端测试: 导入 → 质检 → 审核 → 导出 完整闭环."""

import pytest
from vocab_qc.core.models import (
    ContentItem,
    Meaning,
    Phonetic,
    QcStatus,
    ReviewItem,
    Source,
    Word,
)
from vocab_qc.core.services.export_service import ExportService
from vocab_qc.core.services.qc_service import QcService
from vocab_qc.core.services.review_service import ReviewService


@pytest.fixture
def full_word_data(db_session):
    """创建包含完整五维内容的单词数据."""
    word = Word(word="happy")
    db_session.add(word)
    db_session.flush()

    phonetic = Phonetic(word_id=word.id, ipa="/ˈhæp·i/", syllables="hap\u00b7py")
    db_session.add(phonetic)

    meaning = Meaning(word_id=word.id, pos="adj.", definition="快乐的；幸福的")
    db_session.add(meaning)
    db_session.flush()

    source = Source(meaning_id=meaning.id, source_name="人教版三年级英语上册")
    db_session.add(source)

    chunk = ContentItem(
        word_id=word.id,
        meaning_id=meaning.id,
        dimension="chunk",
        content="happy birthday",
    )
    sentence = ContentItem(
        word_id=word.id,
        meaning_id=meaning.id,
        dimension="sentence",
        content="I am very happy to see you today.",
        content_cn="今天见到你我很高兴。",
    )
    db_session.add_all([chunk, sentence])
    db_session.flush()

    return {"word": word, "meaning": meaning, "phonetic": phonetic, "chunk": chunk, "sentence": sentence}


def test_e2e_full_pipeline(db_session, full_word_data):
    """完整闭环: 质检 → 审核 → 导出."""
    word = full_word_data["word"]
    full_word_data["chunk"]
    full_word_data["sentence"]

    qc_service = QcService()
    review_service = ReviewService()
    export_service = ExportService()

    # === Step 1: 运行 Layer 1 质检 ===
    result = qc_service.run_layer1(db_session, scope=f"word_id:{word.id}")
    assert result["total"] == 2  # chunk + sentence

    # === Step 2: 检查导出就绪状态（应该未就绪）===
    readiness = export_service.get_export_readiness(db_session)
    assert readiness["approved"] == 0

    # === Step 3: 将失败项入队 ===
    qc_service.enqueue_failed_for_review(db_session, result["run_id"])

    # === Step 4: 对通过项直接审核通过 ===
    passed_items = (
        db_session.query(ContentItem)
        .filter_by(word_id=word.id, qc_status=QcStatus.LAYER1_PASSED.value)
        .all()
    )

    for item in passed_items:
        review = review_service.create_review_item(
            db_session,
            item,
            reason=__import__("vocab_qc.core.models.enums", fromlist=["ReviewReason"]).ReviewReason.SAMPLING,
        )
        review_service.approve(db_session, review.id, reviewer="test_reviewer")

    # === Step 5: 对失败项进行人工修改或重新生成 ===
    failed_items = (
        db_session.query(ContentItem)
        .filter_by(word_id=word.id, qc_status=QcStatus.LAYER1_FAILED.value)
        .all()
    )

    for item in failed_items:
        reviews = db_session.query(ReviewItem).filter_by(content_item_id=item.id, status="pending").all()
        for review in reviews:
            # 人工修改内容
            review_service.manual_edit(
                db_session,
                review.id,
                reviewer="test_reviewer",
                new_content=item.content,
            )
            # 修改后重跑 Layer 1
            qc_service.run_layer1(db_session, scope=f"word_id:{word.id}", dimension=item.dimension)
            # 通过后审核
            db_session.refresh(item)
            if item.qc_status == QcStatus.LAYER1_PASSED.value:
                review2 = review_service.create_review_item(
                    db_session,
                    item,
                    reason=__import__("vocab_qc.core.models.enums", fromlist=["ReviewReason"]).ReviewReason.SAMPLING,
                )
                review_service.approve(db_session, review2.id, reviewer="test_reviewer")

    # === Step 6: 检查导出 ===
    data = export_service.export_word(db_session, word.id)
    assert data is not None
    assert data["word"] == "happy"
    assert data["ipa"] == "/ˈhæp·i/"

    # 验证导出就绪
    readiness = export_service.get_export_readiness(db_session)
    assert readiness["approved"] > 0


def test_e2e_retry_limit(db_session, full_word_data):
    """测试重试次数限制: 3次后必须人工修改."""
    from unittest.mock import patch

    chunk = full_word_data["chunk"]
    review_service = ReviewService(max_retries=3)

    from vocab_qc.core.models.enums import ReviewReason

    def _mock_regen(session, ci):
        ci.content = "mock regenerated content"

    # Mock AI 生成器，避免真实 API 调用
    with patch(
        "vocab_qc.core.services.review_service.ReviewService._do_regenerate",
        side_effect=_mock_regen,
    ):
        # 模拟3次重新生成
        for i in range(3):
            review = review_service.create_review_item(db_session, chunk, ReviewReason.LAYER1_FAILED)
            result = review_service.regenerate(db_session, review.id, reviewer="tester")
            assert result["success"] is True
            assert result["retry_count"] == i + 1

        # 第4次应该被拒绝
        review4 = review_service.create_review_item(db_session, chunk, ReviewReason.LAYER1_FAILED)
        result4 = review_service.regenerate(db_session, review4.id, reviewer="tester")

    assert result4["success"] is False
    assert "最大重试次数" in result4["message"]

    # 此时只能人工修改
    review_service.manual_edit(db_session, review4.id, reviewer="tester", new_content="be happy today")
    db_session.refresh(chunk)
    assert chunk.content == "be happy today"


def test_e2e_export_only_approved(db_session, full_word_data):
    """导出门禁: 只有 approved 的内容才会导出."""
    word = full_word_data["word"]
    export_service = ExportService()

    # 未审核通过 → 导出数据中内容为 None
    data = export_service.export_word(db_session, word.id)
    assert data["meanings"][0]["chunk"] is None
    assert data["meanings"][0]["sentence"] is None
    assert data["meanings"][0].get("mnemonics", []) == []

    # 手动设为 approved
    chunk = full_word_data["chunk"]
    chunk.qc_status = QcStatus.APPROVED.value
    db_session.flush()

    data2 = export_service.export_word(db_session, word.id)
    assert data2["meanings"][0]["chunk"] == "happy birthday"
    # sentence 仍为 None（未 approved）
    assert data2["meanings"][0]["sentence"] is None
