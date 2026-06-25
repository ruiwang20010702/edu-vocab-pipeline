"""异步导出任务编排：建任务 / 跑任务 / 查任务 / 清理。

设计要点：
- 任务态存 DB（export_jobs），文件落容器本地盘，多 worker 凭 DB+盘 提供状态/下载。
- 并发去重：已有未完成任务则复用，防多人同时点击重复构建。
- 僵尸超时：running 超 JOB_TIMEOUT 仍无结果（worker 崩溃等）→ 判 failed。
- TTL 清理：删 FILE_TTL 之前的旧文件与记录，避免本地盘堆积。
"""

import logging
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from tempfile import gettempdir

from sqlalchemy import select
from sqlalchemy.orm import Session

from vocab_qc.core.models import EXPORT_TERMINAL_STATUSES, ExportJob, ExportJobStatus
from vocab_qc.core.services.export_service import ExportService

logger = logging.getLogger(__name__)

# 文件落盘目录（容器本地盘）。单容器部署，足够。
EXPORT_DIR = Path(gettempdir()) / "vocab_exports"
# 文件与记录保留时长，过期清理
FILE_TTL = timedelta(hours=24)
# running 超此时长无结果视为僵尸（worker 崩溃/重启），判 failed
JOB_TIMEOUT = timedelta(minutes=20)

_CST = timezone(timedelta(hours=8))


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(dt: datetime | None) -> datetime | None:
    """历史/SQLite 偶现 naive datetime，按 UTC 解释，避免比较时崩。"""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _reconcile_stale(session: Session, job: ExportJob) -> None:
    """running 超时的僵尸任务就地判 failed（调用方负责 commit）。"""
    if job.status != ExportJobStatus.RUNNING.value:
        return
    started = _as_utc(job.started_at) or _as_utc(job.created_at)
    if started is not None and _now() - started > JOB_TIMEOUT:
        job.status = ExportJobStatus.FAILED.value
        job.error_message = "导出超时（后台任务无响应）"
        job.finished_at = _now()


def create_job(session: Session, created_by: str) -> ExportJob:
    """建导出任务。已有未完成任务则复用（并发去重），否则新建 pending。

    Returns:
        ExportJob：可能是复用的进行中任务，也可能是新建的 pending 任务。
        调用方据 status 决定是否派发后台执行（仅 pending 需派发）。
    """
    unfinished = (
        session.execute(
            select(ExportJob)
            .where(ExportJob.status.notin_(list(EXPORT_TERMINAL_STATUSES)))
            .order_by(ExportJob.created_at.desc())
        )
        .scalars()
        .first()
    )
    if unfinished is not None:
        _reconcile_stale(session, unfinished)
        if unfinished.status not in EXPORT_TERMINAL_STATUSES:
            session.commit()
            logger.info("导出任务复用 id=%s status=%s", unfinished.id, unfinished.status)
            return unfinished
        session.commit()  # 僵尸已判 failed，落库后继续新建

    job = ExportJob(status=ExportJobStatus.PENDING.value, created_by=created_by)
    session.add(job)
    session.commit()
    session.refresh(job)
    logger.info("导出任务新建 id=%s by=%s", job.id, created_by)
    return job


def run_job(session: Session, job_id: int) -> None:
    """后台执行体：构建 Excel 落盘并更新任务态。session 由调用方（后台线程）独立创建。"""
    job = session.get(ExportJob, job_id)
    if job is None:
        logger.warning("导出任务不存在 id=%s", job_id)
        return
    if job.status != ExportJobStatus.PENDING.value:
        logger.info("导出任务非 pending，跳过执行 id=%s status=%s", job_id, job.status)
        return

    job.status = ExportJobStatus.RUNNING.value
    job.started_at = _now()
    session.commit()

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EXPORT_DIR / f"vocab_export_{job_id}.xlsx"
    try:
        ExportService().export_to_excel(session, out_path)
        job.status = ExportJobStatus.COMPLETED.value
        job.file_path = str(out_path)
        job.file_name = f"vocab_export_{_now().astimezone(_CST):%Y%m%d_%H%M}.xlsx"
        job.file_size = out_path.stat().st_size if out_path.exists() else None
        job.finished_at = _now()
        session.commit()
        logger.info("导出任务完成 id=%s size=%s", job_id, job.file_size)
    except Exception as exc:  # noqa: BLE001 — 后台任务须吞异常并落库，否则前端永远 running
        session.rollback()
        job = session.get(ExportJob, job_id)
        if job is not None:
            job.status = ExportJobStatus.FAILED.value
            job.error_message = str(exc)[:2000]
            job.finished_at = _now()
            session.commit()
        logger.exception("导出任务失败 id=%s", job_id)


def get_job(session: Session, job_id: int) -> ExportJob | None:
    """查任务，顺带把僵尸超时任务判 failed。"""
    job = session.get(ExportJob, job_id)
    if job is None:
        return None
    _reconcile_stale(session, job)
    if job in session.dirty:
        session.commit()
    return job


def cleanup_old(session: Session) -> int:
    """删 FILE_TTL 之前的旧任务文件与记录，返回清理条数。best-effort。"""
    cutoff = _now() - FILE_TTL
    stale = (
        session.execute(select(ExportJob).where(ExportJob.created_at < cutoff))
        .scalars()
        .all()
    )
    n = 0
    for job in stale:
        if job.file_path:
            try:
                Path(job.file_path).unlink(missing_ok=True)
            except OSError:
                logger.warning("清理导出文件失败 path=%s", job.file_path)
        session.delete(job)
        n += 1
    if n:
        session.commit()
        logger.info("清理过期导出任务 %d 条", n)
    return n
