"""stats_service 单元测试."""

from vocab_qc.core.models import ContentItem, QcStatus, Word
from vocab_qc.core.services import stats_service


class TestGetDashboardStats:
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
