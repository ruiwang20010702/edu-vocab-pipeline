"""仪表板统计服务."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.data_layer import Word
from vocab_qc.core.models.enums import QcStatus


def get_dashboard_stats(session: Session) -> dict:
    """聚合统计：总词数、已通过、待审核、未通过、通过率。"""
    total_words = session.query(func.count()).select_from(Word).scalar() or 0

    approved_count = (
        session.query(func.count(func.distinct(ContentItem.word_id)))
        .filter(ContentItem.qc_status == QcStatus.APPROVED.value)
        .scalar()
        or 0
    )

    pending_count = (
        session.query(func.count(func.distinct(ContentItem.word_id)))
        .filter(
            ContentItem.qc_status.in_([
                QcStatus.PENDING.value,
                QcStatus.LAYER1_PASSED.value,
                QcStatus.LAYER2_PASSED.value,
            ])
        )
        .scalar()
        or 0
    )

    rejected_count = (
        session.query(func.count(func.distinct(ContentItem.word_id)))
        .filter(
            ContentItem.qc_status.in_([
                QcStatus.LAYER1_FAILED.value,
                QcStatus.LAYER2_FAILED.value,
                QcStatus.REJECTED.value,
            ])
        )
        .scalar()
        or 0
    )

    pass_rate = round(approved_count / total_words * 100, 1) if total_words > 0 else 0.0

    return {
        "total_words": total_words,
        "approved_count": approved_count,
        "pending_count": pending_count,
        "rejected_count": rejected_count,
        "pass_rate": pass_rate,
    }
