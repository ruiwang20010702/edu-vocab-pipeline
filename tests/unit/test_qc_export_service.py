"""QcService 与 ExportService 单元测试."""

import pytest
from sqlalchemy.orm import Session
from vocab_qc.core.models import ContentItem, Meaning, QcStatus, Word
from vocab_qc.core.services.export_service import ExportService
from vocab_qc.core.services.qc_service import QcService

# ---- helpers ----


def _make_word(session: Session, word_text: str) -> Word:
    word = Word(word=word_text)
    session.add(word)
    session.flush()
    return word


def _make_meaning(session: Session, word: Word, pos: str, definition: str) -> Meaning:
    meaning = Meaning(word_id=word.id, pos=pos, definition=definition)
    session.add(meaning)
    session.flush()
    return meaning


def _make_content(
    session: Session,
    word: Word,
    dimension: str,
    content: str,
    *,
    meaning: Meaning | None = None,
    qc_status: str = QcStatus.PENDING.value,
    content_cn: str | None = None,
) -> ContentItem:
    item = ContentItem(
        word_id=word.id,
        meaning_id=meaning.id if meaning else None,
        dimension=dimension,
        content=content,
        content_cn=content_cn,
        qc_status=qc_status,
    )
    session.add(item)
    session.flush()
    return item


# ---- QcService 测试 ----


class TestQcServiceInvalidScope:
    """run_layer1 使用不匹配任何项的 dimension 参数时的行为."""

    def test_dimension_matches_no_items(self, db_session: Session):
        """当 dimension 筛选匹配不到任何 ContentItem 时，返回零结果."""
        word = _make_word(db_session, "apple")
        meaning = _make_meaning(db_session, word, "n.", "苹果")
        _make_content(db_session, word, "chunk", "a red apple", meaning=meaning)

        svc = QcService()
        result = svc.run_layer1(db_session, dimension="sentence")

        assert result == {"run_id": None, "total": 0, "passed": 0, "failed": 0}

    def test_nonexistent_dimension(self, db_session: Session):
        """当 dimension 为完全不存在的值时，返回零结果."""
        word = _make_word(db_session, "banana")
        meaning = _make_meaning(db_session, word, "n.", "香蕉")
        _make_content(db_session, word, "chunk", "a banana", meaning=meaning)

        svc = QcService()
        result = svc.run_layer1(db_session, dimension="nonexistent_dim")

        assert result["run_id"] is None
        assert result["total"] == 0


class TestQcServiceTerminalStatusFiltering:
    """run_layer1 跳过 APPROVED / REJECTED 终态项."""

    def test_approved_items_are_skipped(self, db_session: Session):
        """APPROVED 状态的内容项不应被 run_layer1 处理."""
        word = _make_word(db_session, "cat")
        meaning = _make_meaning(db_session, word, "n.", "猫")
        _make_content(
            db_session, word, "chunk", "a lovely cat",
            meaning=meaning, qc_status=QcStatus.APPROVED.value,
        )

        svc = QcService()
        result = svc.run_layer1(db_session)

        assert result["total"] == 0
        assert result["run_id"] is None

    def test_rejected_items_are_skipped(self, db_session: Session):
        """REJECTED 状态的内容项不应被 run_layer1 处理."""
        word = _make_word(db_session, "dog")
        meaning = _make_meaning(db_session, word, "n.", "狗")
        _make_content(
            db_session, word, "chunk", "a big dog",
            meaning=meaning, qc_status=QcStatus.REJECTED.value,
        )

        svc = QcService()
        result = svc.run_layer1(db_session)

        assert result["total"] == 0
        assert result["run_id"] is None

    def test_mix_terminal_and_pending(self, db_session: Session):
        """混合终态与待处理项，仅待处理项被纳入质检."""
        word = _make_word(db_session, "run")
        meaning = _make_meaning(db_session, word, "v.", "跑")

        _make_content(
            db_session, word, "chunk", "run fast",
            meaning=meaning, qc_status=QcStatus.APPROVED.value,
        )
        _make_content(
            db_session, word, "chunk", "run away",
            meaning=meaning, qc_status=QcStatus.REJECTED.value,
        )
        _make_content(
            db_session, word, "chunk", "run a race",
            meaning=meaning, qc_status=QcStatus.PENDING.value,
        )

        svc = QcService()
        result = svc.run_layer1(db_session)

        # 只有 pending 的那一项被处理
        assert result["total"] == 1


# ---- ExportService 测试 ----


class TestExportServiceAllApproved:
    """export_all_approved 只导出 approved 内容."""

    def test_only_approved_items_exported(self, db_session: Session):
        """混合状态的内容项中，仅 approved 出现在导出结果里."""
        word = _make_word(db_session, "book")
        meaning = _make_meaning(db_session, word, "n.", "书")

        # approved chunk
        _make_content(
            db_session, word, "chunk", "read a book",
            meaning=meaning, qc_status=QcStatus.APPROVED.value,
        )
        # pending sentence — 不应导出
        _make_content(
            db_session, word, "sentence", "I read a book every day.",
            meaning=meaning, qc_status=QcStatus.PENDING.value,
            content_cn="我每天读一本书。",
        )
        # rejected chunk — 不应导出
        _make_content(
            db_session, word, "chunk", "bad chunk",
            meaning=meaning, qc_status=QcStatus.REJECTED.value,
        )

        svc = ExportService()
        results = svc.export_all_approved(db_session)

        assert len(results) == 1
        exported = results[0]
        assert exported["word"] == "book"

        # meanings 内的 chunk 应有值，sentence 应为 None（未 approved）
        assert len(exported["meanings"]) == 1
        m = exported["meanings"][0]
        assert m["chunk"] == "read a book"
        assert m["sentence"] is None

    def test_no_approved_items(self, db_session: Session):
        """没有任何 approved 项时返回空列表."""
        word = _make_word(db_session, "pen")
        meaning = _make_meaning(db_session, word, "n.", "笔")
        _make_content(
            db_session, word, "chunk", "a pen",
            meaning=meaning, qc_status=QcStatus.PENDING.value,
        )

        svc = ExportService()
        results = svc.export_all_approved(db_session)

        assert results == []

    def test_multiple_words_partial_approval(self, db_session: Session):
        """多词场景：仅有 approved 内容的词才出现在导出列表中."""
        word_a = _make_word(db_session, "sun")
        meaning_a = _make_meaning(db_session, word_a, "n.", "太阳")
        _make_content(
            db_session, word_a, "chunk", "the sun rises",
            meaning=meaning_a, qc_status=QcStatus.APPROVED.value,
        )

        word_b = _make_word(db_session, "moon")
        meaning_b = _make_meaning(db_session, word_b, "n.", "月亮")
        _make_content(
            db_session, word_b, "chunk", "the moon",
            meaning=meaning_b, qc_status=QcStatus.PENDING.value,
        )

        svc = ExportService()
        results = svc.export_all_approved(db_session)

        exported_words = [r["word"] for r in results]
        assert "sun" in exported_words
        assert "moon" not in exported_words

    def test_export_readiness_counts(self, db_session: Session):
        """get_export_readiness 正确统计各状态数量."""
        word = _make_word(db_session, "star")
        meaning = _make_meaning(db_session, word, "n.", "星星")
        _make_content(
            db_session, word, "chunk", "a star",
            meaning=meaning, qc_status=QcStatus.APPROVED.value,
        )
        _make_content(
            db_session, word, "sentence", "I see a star.",
            meaning=meaning, qc_status=QcStatus.PENDING.value,
            content_cn="我看到一颗星星。",
        )
        _make_content(
            db_session, word, "chunk", "bad star",
            meaning=meaning, qc_status=QcStatus.REJECTED.value,
        )

        svc = ExportService()
        readiness = svc.get_export_readiness(db_session)

        assert readiness["total_items"] == 3
        assert readiness["approved"] == 1
        assert readiness["pending"] == 1
        assert readiness["not_approved"] == 2
        assert readiness["ready_rate"] == pytest.approx(33.3, abs=0.1)
