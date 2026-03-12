"""仪表板统计服务."""

from sqlalchemy import func, and_, not_
from sqlalchemy.orm import Session

from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.data_layer import Word
from vocab_qc.core.models.enums import QcStatus
from vocab_qc.core.models.quality_layer import QcRuleResult

# 终态集合：approved 或 rejected
_TERMINAL_STATUSES = [QcStatus.APPROVED.value, QcStatus.REJECTED.value]


def get_dashboard_stats(session: Session) -> dict:
    """聚合统计：总词数、已入库、待处理、未通过、通过率、Bad Case 分类。

    定义对齐总表：
    - 已入库(approved_count) = 所有 ContentItem 均为终态的词数
    - 待处理(pending_count) = total_words - approved_count（存在非终态项的词数）
    - 未通过(rejected_count) = 存在 layer1/2_failed 项的词数（信息性统计）
    """
    total_words = session.query(func.count()).select_from(Word).scalar() or 0

    # 已入库 = 有 ContentItem 且全部为终态的词数
    # NOT EXISTS 比 NOT IN 更高效（避免子查询物化 + NULL 安全）
    from sqlalchemy import exists, alias

    ci1 = alias(ContentItem.__table__, name="ci1")
    ci2 = alias(ContentItem.__table__, name="ci2")

    # 有内容的 word_id（去重）
    has_content_q = session.query(ci1.c.word_id.distinct())
    # 存在非终态项的子查询
    non_terminal_exists = (
        session.query(ci2.c.id)
        .filter(
            ci2.c.word_id == ci1.c.word_id,
            ~ci2.c.qc_status.in_(_TERMINAL_STATUSES),
        )
        .exists()
    )
    approved_count = (
        has_content_q.filter(~non_terminal_exists).count()
    )

    pending_count = total_words - approved_count

    rejected_count = (
        session.query(func.count(func.distinct(ContentItem.word_id)))
        .filter(
            ContentItem.qc_status.in_([
                QcStatus.LAYER1_FAILED.value,
                QcStatus.LAYER2_FAILED.value,
            ])
        )
        .scalar()
        or 0
    )

    pass_rate = round(approved_count / total_words * 100, 1) if total_words > 0 else 0.0

    # Bad Case 分类：按 rule_id + dimension 聚合失败数（仅统计最新质检结果）
    issue_rows = (
        session.query(
            QcRuleResult.rule_id,
            QcRuleResult.dimension,
            func.count().label("count"),
        )
        .join(ContentItem, ContentItem.id == QcRuleResult.content_item_id)
        .filter(
            QcRuleResult.passed == False,  # noqa: E712
            QcRuleResult.run_id == ContentItem.last_qc_run_id,
        )
        .group_by(QcRuleResult.rule_id, QcRuleResult.dimension)
        .all()
    )
    issues = [
        {"field": row.rule_id, "dimension": row.dimension, "count": row.count}
        for row in issue_rows
    ]

    return {
        "total_words": total_words,
        "approved_count": approved_count,
        "pending_count": pending_count,
        "rejected_count": rejected_count,
        "pass_rate": pass_rate,
        "issues": issues,
    }
