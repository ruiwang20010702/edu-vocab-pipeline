"""仪表板统计 API 路由."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_current_user, get_db, require_role
from vocab_qc.api.schemas.stats import (
    AiUsageStatsResponse,
    DashboardStatsResponse,
    ProductionRecordsResponse,
)
from vocab_qc.core.models.user import User
from vocab_qc.core.services import stats_service

router = APIRouter(prefix="/api", tags=["统计"])


@router.get("/stats", response_model=DashboardStatsResponse)
def get_stats(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """获取仪表板统计数据。"""
    return stats_service.get_dashboard_stats(db)


@router.get("/stats/ai-usage", response_model=AiUsageStatsResponse)
def get_ai_usage_stats(
    days: int = Query(default=7, ge=1, le=90, description="统计天数"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """获取 AI 用量统计数据。"""
    return stats_service.get_ai_usage_stats(db, days=days)


@router.get("/stats/production-records", response_model=ProductionRecordsResponse)
def get_production_records(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """获取按 Package 聚合的生产记录（JSON）。"""
    return stats_service.get_production_records(db)


@router.get("/stats/production-records/export")
def export_production_records(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """导出生产记录为 xlsx。"""
    buf = stats_service.export_production_records_xlsx(db)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=production-records.xlsx"},
    )


# ── 任务队列监控 ──────────────────────────────────────────────────


@router.get("/stats/task-queue")
def get_task_queue_stats(
    batch_key: Optional[str] = Query(default=None, description="按批次 key 过滤"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """任务队列总览：各状态数量、平均耗时."""
    from vocab_qc.core.models.ai_task_queue import AiTaskQueue, AiTaskStatus

    q = db.query(AiTaskQueue)
    if batch_key:
        q = q.filter_by(batch_key=batch_key)

    total = q.count()
    if total == 0:
        return {"total": 0, "by_status": {}, "avg_poll_count": 0, "avg_duration_s": None}

    by_status = {}
    for status in AiTaskStatus:
        by_status[status.value] = q.filter_by(status=status.value).count()

    # 平均轮询次数
    avg_poll = db.query(func.avg(AiTaskQueue.poll_count)).filter(
        AiTaskQueue.status == AiTaskStatus.COMPLETED.value,
    ).scalar() or 0

    # 平均耗时（提交到完成）
    from sqlalchemy import extract
    completed_tasks = q.filter(
        AiTaskQueue.submitted_at.isnot(None),
        AiTaskQueue.completed_at.isnot(None),
    )
    avg_dur = None
    if completed_tasks.count() > 0:
        durations = [
            (t.completed_at - t.submitted_at).total_seconds()
            for t in completed_tasks.limit(1000).all()
            if t.completed_at and t.submitted_at
        ]
        if durations:
            avg_dur = round(sum(durations) / len(durations), 1)

    return {
        "total": total,
        "by_status": by_status,
        "avg_poll_count": round(float(avg_poll), 1),
        "avg_duration_s": avg_dur,
    }


@router.get("/stats/task-queue/batch/{batch_key}")
def get_batch_progress(
    batch_key: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """指定批次的实时进度."""
    from vocab_qc.core.task_queue import TaskQueueService
    return TaskQueueService.batch_progress(db, batch_key)
