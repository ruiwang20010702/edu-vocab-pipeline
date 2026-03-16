"""Layer 2 失败路径测试.

覆盖:
- AI 返回 passed=False → ContentItem.qc_status 变为 LAYER2_FAILED
- LAYER2_FAILED 的 item 被入队到 ReviewItem
- AI 调用抛异常 → 错误被正确处理（fail-safe: 不自动通过）
"""

from unittest.mock import MagicMock

from vocab_qc.core.models import ContentItem, Meaning, ReviewItem, Word
from vocab_qc.core.models.enums import QcStatus, ReviewReason, ReviewStatus
from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.layer2.runner import Layer2Runner
from vocab_qc.core.services.qc_service import QcService


def _create_layer1_passed_item(db_session, word, meaning, dimension="chunk", content="eat an apple"):
    """创建一个 Layer1 已通过的 ContentItem。"""
    item = ContentItem(
        word_id=word.id,
        meaning_id=meaning.id if meaning else None,
        dimension=dimension,
        content=content,
        qc_status=QcStatus.LAYER1_PASSED.value,
    )
    db_session.add(item)
    db_session.flush()
    return item


class TestLayer2Failure:
    """Layer 2 AI 质检失败路径测试。"""

    def test_layer2_failed_sets_status(self, db_session):
        """Layer 2 AI 返回 passed=False 时，ContentItem 状态应为 LAYER2_FAILED。"""
        word = Word(word="apple")
        db_session.add(word)
        db_session.flush()

        meaning = Meaning(word_id=word.id, pos="n.", definition="苹果")
        db_session.add(meaning)
        db_session.flush()

        item = _create_layer1_passed_item(db_session, word, meaning)

        # 创建 mock AI client，返回 failed 结果
        mock_client = MagicMock()
        mock_client.model = "test-model"

        # mock Layer2Runner 的 _collect_ai_results，返回失败结果
        runner = Layer2Runner(client=mock_client)

        failed_result = RuleResult(rule_id="L2_C1", passed=False, detail="语块不符合搭配规范")
        results_map = {item.id: [failed_result]}

        # 直接调用 _save_results 验证状态写入
        import uuid
        run_id = str(uuid.uuid4())

        from vocab_qc.core.models.enums import AiStrategy
        from vocab_qc.core.models.quality_layer import QcRun

        qc_run = QcRun(
            id=run_id, layer=2, scope="batch",
            ai_strategy=AiStrategy.PER_RULE.value,
            ai_model="test-model", total_items=1, status="running",
        )
        db_session.add(qc_run)
        db_session.flush()

        passed, failed = runner._save_results(
            db_session, [item], results_map, AiStrategy.PER_RULE, run_id,
        )
        db_session.flush()

        assert failed == 1
        assert passed == 0
        assert item.qc_status == QcStatus.LAYER2_FAILED.value
        assert item.last_qc_run_id == run_id

    def test_layer2_failed_enqueued_for_review(self, db_session):
        """Layer 2 失败的 item 应被入队审核，reason == LAYER2_FAILED。"""
        word = Word(word="book")
        db_session.add(word)
        db_session.flush()

        meaning = Meaning(word_id=word.id, pos="n.", definition="书")
        db_session.add(meaning)
        db_session.flush()

        item = _create_layer1_passed_item(
            db_session, word, meaning,
            dimension="sentence",
            content="I read a book.",
        )

        # 模拟 Layer2 已将 item 标记为 LAYER2_FAILED
        import uuid
        run_id = str(uuid.uuid4())
        item.qc_status = QcStatus.LAYER2_FAILED.value
        item.last_qc_run_id = run_id
        db_session.flush()

        # 调用 enqueue_layer2_failed_for_review
        qc_service = QcService()
        enqueued = qc_service.enqueue_layer2_failed_for_review(db_session, run_id)

        assert enqueued == 1

        # 验证 ReviewItem 被正确创建
        review = db_session.query(ReviewItem).filter_by(content_item_id=item.id).first()
        assert review is not None
        assert review.reason == ReviewReason.LAYER2_FAILED.value
        assert review.status == ReviewStatus.PENDING.value
        assert review.word_id == word.id
        assert review.dimension == "sentence"

    def test_layer2_failed_no_duplicate_enqueue(self, db_session):
        """已有 pending ReviewItem 时不应重复入队。"""
        word = Word(word="cat")
        db_session.add(word)
        db_session.flush()

        meaning = Meaning(word_id=word.id, pos="n.", definition="猫")
        db_session.add(meaning)
        db_session.flush()

        item = _create_layer1_passed_item(db_session, word, meaning)

        import uuid
        run_id = str(uuid.uuid4())
        item.qc_status = QcStatus.LAYER2_FAILED.value
        item.last_qc_run_id = run_id
        db_session.flush()

        qc_service = QcService()

        # 第一次入队
        count1 = qc_service.enqueue_layer2_failed_for_review(db_session, run_id)
        assert count1 == 1

        # 第二次入队（同一 run_id），不应重复创建
        count2 = qc_service.enqueue_layer2_failed_for_review(db_session, run_id)
        assert count2 == 1  # create_review_item 内部防重复

        total = db_session.query(ReviewItem).filter_by(content_item_id=item.id).count()
        assert total == 1

    def test_layer2_ai_exception_failsafe(self, db_session):
        """AI 调用抛异常时，item 不应被自动标记为通过（fail-safe）。"""
        word = Word(word="dog")
        db_session.add(word)
        db_session.flush()

        meaning = Meaning(word_id=word.id, pos="n.", definition="狗")
        db_session.add(meaning)
        db_session.flush()

        item = _create_layer1_passed_item(db_session, word, meaning)

        mock_client = MagicMock()
        mock_client.model = "test-model"

        runner = Layer2Runner(client=mock_client)

        # 空的 results_map 模拟所有 AI 调用失败（被 gather 捕获为异常后跳过）
        empty_results_map: dict[int, list[RuleResult]] = {}

        import uuid

        from vocab_qc.core.models.enums import AiStrategy

        run_id = str(uuid.uuid4())

        from vocab_qc.core.models.quality_layer import QcRun

        qc_run = QcRun(
            id=run_id, layer=2, scope="batch",
            ai_strategy=AiStrategy.PER_RULE.value,
            ai_model="test-model", total_items=1, status="running",
        )
        db_session.add(qc_run)
        db_session.flush()

        passed, failed = runner._save_results(
            db_session, [item], empty_results_map, AiStrategy.PER_RULE, run_id,
        )
        db_session.flush()

        # fail-safe: 无结果时不自动通过
        assert passed == 0
        assert failed == 0
        assert item.qc_status == QcStatus.LAYER1_PASSED.value  # 保持原状态

    def test_layer2_mixed_results(self, db_session):
        """多个 item 中部分通过部分失败，状态应正确区分。"""
        word = Word(word="run")
        db_session.add(word)
        db_session.flush()

        m1 = Meaning(word_id=word.id, pos="v.", definition="跑")
        m2 = Meaning(word_id=word.id, pos="v.", definition="运行")
        db_session.add_all([m1, m2])
        db_session.flush()

        item1 = _create_layer1_passed_item(db_session, word, m1, content="run fast")
        item2 = _create_layer1_passed_item(db_session, word, m2, content="run a program")

        mock_client = MagicMock()
        mock_client.model = "test-model"
        runner = Layer2Runner(client=mock_client)

        # item1 通过，item2 失败
        results_map = {
            item1.id: [RuleResult(rule_id="L2_C1", passed=True, detail="OK")],
            item2.id: [RuleResult(rule_id="L2_C1", passed=False, detail="搭配不当")],
        }

        import uuid

        from vocab_qc.core.models.enums import AiStrategy
        from vocab_qc.core.models.quality_layer import QcRun

        run_id = str(uuid.uuid4())
        qc_run = QcRun(
            id=run_id, layer=2, scope="batch",
            ai_strategy=AiStrategy.PER_RULE.value,
            ai_model="test-model", total_items=2, status="running",
        )
        db_session.add(qc_run)
        db_session.flush()

        passed, failed = runner._save_results(
            db_session, [item1, item2], results_map, AiStrategy.PER_RULE, run_id,
        )
        db_session.flush()

        assert passed == 1
        assert failed == 1
        assert item1.qc_status == QcStatus.LAYER2_PASSED.value
        assert item2.qc_status == QcStatus.LAYER2_FAILED.value
