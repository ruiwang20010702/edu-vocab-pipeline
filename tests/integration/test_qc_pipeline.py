"""质检流水线集成测试."""

from vocab_qc.core.models import QcRuleResult, QcRun, ReviewItem
from vocab_qc.core.services.qc_service import QcService


def test_full_layer1_pipeline(db_session, sample_word):
    """完整 Layer 1 流水线: 校验 → 入队 → 审核."""
    qc_service = QcService()

    # Step 1: 运行 Layer 1
    result = qc_service.run_layer1(db_session, dimension="chunk")
    assert result["total"] == 2
    assert result["run_id"] is not None

    # Step 2: 检查运行记录
    qc_run = db_session.query(QcRun).filter_by(id=result["run_id"]).first()
    assert qc_run.status == "completed"

    # Step 3: 入队失败项
    failed_count = qc_service.enqueue_failed_for_review(db_session, result["run_id"])

    # Step 4: 抽样通过项
    sampling_count = qc_service.enqueue_sampling(db_session, result["run_id"], sample_rate=1.0)

    # 总审核数 = 失败项 + 抽样项
    total_reviews = db_session.query(ReviewItem).count()
    assert total_reviews == failed_count + sampling_count


def test_layer1_with_scope(db_session, sample_word):
    """按 word_id 范围运行."""
    qc_service = QcService()
    word = sample_word["word"]

    result = qc_service.run_layer1(db_session, scope=f"word_id:{word.id}")
    assert result["total"] > 0


def test_layer1_sentence_with_translation(db_session, sample_word):
    """测试例句（含中文翻译）的 Layer 1 校验."""
    qc_service = QcService()

    result = qc_service.run_layer1(db_session, dimension="sentence")
    assert result["total"] == 2
    # 校验规则结果
    rule_results = db_session.query(QcRuleResult).filter_by(run_id=result["run_id"]).all()
    assert len(rule_results) > 0

    # E8 应该通过（有中文翻译）
    e8_results = [r for r in rule_results if r.rule_id == "E8"]
    assert all(r.passed for r in e8_results)


def test_layer1_no_items(db_session):
    """无内容项时应优雅处理."""
    qc_service = QcService()
    result = qc_service.run_layer1(db_session, dimension="nonexistent")
    assert result["total"] == 0
    assert result["run_id"] is None
