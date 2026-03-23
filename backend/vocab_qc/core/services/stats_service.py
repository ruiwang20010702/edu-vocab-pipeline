"""仪表板统计服务."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import cast, func, literal_column
from sqlalchemy.orm import Session

from vocab_qc.core.cache import TTLCache
from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.data_layer import Word
from vocab_qc.core.models.enums import QcStatus
from vocab_qc.core.models.quality_layer import AiUsageLog, QcRuleResult

# 终态集合：approved 或 rejected
_TERMINAL_STATUSES = [QcStatus.APPROVED.value, QcStatus.REJECTED.value]

# Stats 缓存（10s TTL，减少前端轮询对数据库的压力）
stats_cache = TTLCache(default_ttl=10.0)
_STATS_CACHE_KEY = "dashboard_stats"


def invalidate_stats_cache() -> None:
    """主动失效 stats 缓存（导入/生产/审核等写操作后调用）。"""
    stats_cache.invalidate(_STATS_CACHE_KEY)


def get_dashboard_stats(session: Session) -> dict:
    """聚合统计：总词数、已入库、待处理、未通过、通过率、Bad Case 分类。

    定义对齐总表：
    - 已入库(approved_count) = 所有 ContentItem 均为终态的词数
    - 待处理(pending_count) = total_words - approved_count（存在非终态项的词数）
    - 未通过(rejected_count) = 存在 layer1/2_failed 项的词数（信息性统计）
    """
    cached = stats_cache.get(_STATS_CACHE_KEY)
    if cached is not None:
        return cached

    total_words = session.query(func.count()).select_from(Word).scalar() or 0

    # 已入库 = 有 ContentItem 且全部为终态的词数
    # NOT EXISTS 比 NOT IN 更高效（避免子查询物化 + NULL 安全）
    from sqlalchemy import alias

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

    result = {
        "total_words": total_words,
        "approved_count": approved_count,
        "pending_count": pending_count,
        "rejected_count": rejected_count,
        "pass_rate": pass_rate,
        "issues": issues,
    }
    stats_cache.set(_STATS_CACHE_KEY, result)
    return result


def get_ai_usage_stats(session: Session, days: int = 7) -> dict:
    """AI 用量统计：总量 + 按维度×阶段分组 + 日趋势。"""
    cache_key = f"ai_usage_stats_{days}"
    cached = stats_cache.get(cache_key)
    if cached is not None:
        return cached

    since = datetime.now(UTC) - timedelta(days=days)

    # 聚合总量
    totals = session.query(
        func.coalesce(func.sum(AiUsageLog.total_tokens), 0),
        func.sum(AiUsageLog.estimated_cost_usd),
        func.count(),
    ).filter(AiUsageLog.created_at >= since).one()

    total_tokens = int(totals[0])
    total_cost = round(float(totals[1]), 6) if totals[1] is not None else None
    total_calls = int(totals[2])

    # 按维度 + 阶段分组
    by_dim_rows = (
        session.query(
            AiUsageLog.dimension,
            AiUsageLog.phase,
            func.coalesce(func.sum(AiUsageLog.total_tokens), 0).label("total_tokens"),
            func.sum(AiUsageLog.estimated_cost_usd).label("cost"),
            func.count().label("call_count"),
        )
        .filter(AiUsageLog.created_at >= since)
        .group_by(AiUsageLog.dimension, AiUsageLog.phase)
        .all()
    )
    by_dimension = [
        {
            "dimension": row.dimension,
            "phase": row.phase,
            "total_tokens": int(row.total_tokens),
            "estimated_cost_usd": round(float(row.cost), 6) if row.cost is not None else None,
            "call_count": int(row.call_count),
        }
        for row in by_dim_rows
    ]

    # 日趋势（兼容 PostgreSQL date_trunc 和 SQLite strftime）
    bind = session.bind
    dialect = bind.dialect.name if bind else "sqlite"
    if dialect == "postgresql":
        day_col = func.date_trunc(literal_column("'day'"), AiUsageLog.created_at).label("day")
    else:
        day_col = func.strftime("%Y-%m-%d", AiUsageLog.created_at).label("day")

    trend_rows = (
        session.query(
            day_col,
            func.coalesce(func.sum(AiUsageLog.total_tokens), 0).label("total_tokens"),
            func.count().label("call_count"),
        )
        .filter(AiUsageLog.created_at >= since)
        .group_by("day")
        .order_by("day")
        .all()
    )
    daily_trend = [
        {
            "date": str(row.day)[:10],
            "total_tokens": int(row.total_tokens),
            "call_count": int(row.call_count),
        }
        for row in trend_rows
    ]

    result = {
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "total_calls": total_calls,
        "by_dimension": by_dimension,
        "daily_trend": daily_trend,
    }
    stats_cache.set(cache_key, result)
    return result
