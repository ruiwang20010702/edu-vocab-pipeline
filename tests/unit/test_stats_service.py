"""stats_service 单元测试."""

import pytest

from vocab_qc.core.models import ContentItem, QcStatus, Word
from vocab_qc.core.services import stats_service
from vocab_qc.core.services.stats_service import invalidate_stats_cache


class TestGetDashboardStats:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        invalidate_stats_cache()
        yield
        invalidate_stats_cache()

    def test_empty_db(self, db_session):
        result = stats_service.get_dashboard_stats(db_session)
        assert result["total_words"] == 0
        assert result["pass_rate"] == 0.0

    def test_with_sample_data(self, db_session, sample_word):
        result = stats_service.get_dashboard_stats(db_session)
        assert result["total_words"] == 1
        assert result["pending_count"] >= 1

    def test_approved_counted(self, db_session):
        word = Word(word="test_approved")
        db_session.add(word)
        db_session.flush()

        item = ContentItem(
            word_id=word.id,
            dimension="chunk",
            content="test",
            qc_status=QcStatus.APPROVED.value,
        )
        db_session.add(item)
        db_session.flush()

        result = stats_service.get_dashboard_stats(db_session)
        assert result["approved_count"] >= 1
        assert result["pass_rate"] > 0

    def test_pending_includes_failed(self, db_session):
        """layer1/2_failed 的词应计入 pending_count，不计入 approved_count."""
        word = Word(word="test_failed")
        db_session.add(word)
        db_session.flush()

        # 该词有 2 个 ContentItem：一个 approved，一个 layer2_failed
        db_session.add(ContentItem(
            word_id=word.id, dimension="chunk", content="ok",
            qc_status=QcStatus.APPROVED.value,
        ))
        db_session.add(ContentItem(
            word_id=word.id, dimension="sentence", content="fail",
            qc_status=QcStatus.LAYER2_FAILED.value,
        ))
        db_session.flush()

        result = stats_service.get_dashboard_stats(db_session)
        # 该词存在非终态项 → 不算已入库，算待处理
        assert result["approved_count"] == 0
        assert result["pending_count"] == 1
        assert result["rejected_count"] == 1

    def test_all_terminal_is_approved(self, db_session):
        """所有 ContentItem 都是终态 → 计入 approved_count."""
        word = Word(word="test_done")
        db_session.add(word)
        db_session.flush()

        db_session.add(ContentItem(
            word_id=word.id, dimension="chunk", content="ok",
            qc_status=QcStatus.APPROVED.value,
        ))
        db_session.add(ContentItem(
            word_id=word.id, dimension="sentence", content="na",
            qc_status=QcStatus.REJECTED.value,
        ))
        db_session.flush()

        result = stats_service.get_dashboard_stats(db_session)
        assert result["approved_count"] == 1
        assert result["pending_count"] == 0
