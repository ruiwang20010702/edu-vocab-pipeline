"""Layer 1 Runner 集成测试."""

from vocab_qc.core.models import ContentItem, QcRuleResult, QcRun, QcStatus, Word
from vocab_qc.core.qc.runner import Layer1Runner


def test_runner_check_item_chunk(sample_word):
    runner = Layer1Runner()
    chunk = sample_word["chunks"][0]  # "be kind to sb."
    word = sample_word["word"]

    result = runner.check_item(chunk, word.word, sample_word["meanings"][0].definition)
    assert result.all_passed
    assert len(result.results) > 0


def test_runner_check_item_sentence(sample_word):
    runner = Layer1Runner()
    sentence = sample_word["sentences"][0]
    word = sample_word["word"]

    result = runner.check_item(
        sentence,
        word.word,
        sample_word["meanings"][0].definition,
        content_cn=sentence.content_cn,
    )
    assert result.all_passed


def test_runner_check_item_detects_failure(db_session):
    word = Word(word="test")
    db_session.add(word)
    db_session.flush()

    # 语块只有 1 个词 → C2 失败
    item = ContentItem(word_id=word.id, dimension="chunk", content="test")
    db_session.add(item)
    db_session.flush()

    runner = Layer1Runner()
    result = runner.check_item(item, "test")
    assert not result.all_passed
    failed_ids = [r.rule_id for r in result.failed_rules]
    assert "C2" in failed_ids


def test_runner_batch_run(db_session, sample_word):
    runner = Layer1Runner()
    word = sample_word["word"]
    chunks = sample_word["chunks"]

    word_texts = {word.id: word.word}
    meaning_texts = {m.id: m.definition for m in sample_word["meanings"]}

    run_id = runner.run(db_session, chunks, word_texts, meaning_texts)

    # 验证 run 记录
    qc_run = db_session.query(QcRun).filter_by(id=run_id).first()
    assert qc_run is not None
    assert qc_run.status == "completed"
    assert qc_run.total_items == 2

    # 验证规则结果写入
    results = db_session.query(QcRuleResult).filter_by(run_id=run_id).all()
    assert len(results) > 0

    # 验证 content_item 状态更新
    for chunk in chunks:
        db_session.refresh(chunk)
        assert chunk.qc_status in (QcStatus.LAYER1_PASSED.value, QcStatus.LAYER1_FAILED.value)
