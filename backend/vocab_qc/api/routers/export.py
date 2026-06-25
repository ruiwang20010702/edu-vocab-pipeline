"""导出 API 路由."""

import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from vocab_qc.api.deps import get_db, require_role
from vocab_qc.api.routers.auth import limiter
from vocab_qc.api.schemas.export import ExportJobOut
from vocab_qc.core.models import ExportJob, ExportJobStatus
from vocab_qc.core.models.user import User
from vocab_qc.core.services import export_job_service
from vocab_qc.core.services.export_service import ExportService, _iter_approved_batches

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/export", tags=["导出"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# 导出构建重且内容相同，串行即可（max_workers=1）。后台线程内开独立 session。
_export_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="export")


def _run_export_job_bg(job_id: int) -> None:
    """后台线程体：独立 session 跑导出，顺带清理过期文件。"""
    from vocab_qc.core.db import SyncSessionLocal

    session = SyncSessionLocal()
    try:
        try:
            export_job_service.cleanup_old(session)
        except Exception:  # noqa: BLE001 — 清理失败不应阻断导出
            logger.warning("导出过期文件清理失败", exc_info=True)
        export_job_service.run_job(session, job_id)
    finally:
        session.close()


async def _run_export_job_bg_async(job_id: int) -> None:
    """线程池包装，避免阻塞事件循环。"""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_export_executor, _run_export_job_bg, job_id)


def _to_job_out(job: ExportJob) -> ExportJobOut:
    out = ExportJobOut.model_validate(job)
    out.download_ready = (
        job.status == ExportJobStatus.COMPLETED.value
        and bool(job.file_path)
        and Path(job.file_path).exists()
    )
    return out


@router.get("/word/{word_id}")
@limiter.limit("30/minute")
def export_word(
    request: Request,
    word_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """导出单个词."""
    service = ExportService()
    data = service.export_word(db, word_id)
    if not data:
        raise HTTPException(status_code=404, detail="单词不存在")
    return data


@router.get("/readiness")
@limiter.limit("30/minute")
def export_readiness(
    request: Request,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """检查导出就绪状态."""
    service = ExportService()
    return service.get_export_readiness(db)


def _stream_json(session: Session) -> Iterator[str]:
    """流式输出 JSON 数组，避免全量加载到内存。"""
    yield "["
    first = True
    for item in _iter_approved_batches(session):
        if not first:
            yield ","
        first = False
        yield json.dumps(item, ensure_ascii=False)
    yield "]"


@router.get("/download")
@limiter.limit("5/minute")
def download_all(
    request: Request,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """下载所有已审核通过的词汇数据 (JSON 流式导出)."""
    logger.info("导出下载 format=json user=%s", _current_user.email)
    return StreamingResponse(
        _stream_json(db),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=vocab_export.json"},
    )


@router.get("/excel")
@limiter.limit("5/minute")
def download_excel(
    request: Request,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin", "reviewer")),
):
    """下载所有已通过词汇数据 (Excel)。

    P-M2/M3: export_to_excel 落盘到临时 xlsx 文件并返回 Path；FileResponse 流式
    读盘下发；BackgroundTask 在响应完成后清理临时文件。避免在内存中持有完整
    xlsx 二进制（27w 义项约 200MB+）。
    """
    logger.info("导出下载 format=excel user=%s", _current_user.email)
    service = ExportService()
    path = service.export_to_excel(db)
    return FileResponse(
        path=str(path),
        filename="vocab_export.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=BackgroundTask(os.unlink, str(path)),
    )


# ── 异步导出（推荐）：点击发起任务 → 后台构建 → 轮询 → 下载，避免同步导出撞 120s 超时 ──


@router.post("/excel/async", response_model=ExportJobOut)
@limiter.limit("10/minute")
def start_excel_export(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin", "reviewer")),
):
    """发起异步 Excel 导出。已有未完成任务则复用（并发去重），仅 pending 派发后台执行。"""
    logger.info("发起异步导出 user=%s", _current_user.email)
    job = export_job_service.create_job(db, _current_user.email)
    if job.status == ExportJobStatus.PENDING.value:
        background_tasks.add_task(_run_export_job_bg_async, job.id)
    return _to_job_out(job)


@router.get("/jobs/{job_id}", response_model=ExportJobOut)
@limiter.limit("120/minute")
def get_export_job(
    request: Request,
    job_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin", "reviewer")),
):
    """查导出任务状态（前端轮询）。"""
    job = export_job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="导出任务不存在")
    return _to_job_out(job)


@router.get("/jobs/{job_id}/download")
@limiter.limit("20/minute")
def download_export_job(
    request: Request,
    job_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin", "reviewer")),
):
    """下载已完成的导出文件（可重复下载，TTL 内有效）。"""
    job = export_job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="导出任务不存在")
    if job.status != ExportJobStatus.COMPLETED.value:
        raise HTTPException(status_code=409, detail="导出尚未完成")
    if not job.file_path or not Path(job.file_path).exists():
        raise HTTPException(status_code=410, detail="导出文件已过期或不存在，请重新导出")
    logger.info("下载导出文件 job=%s user=%s", job_id, _current_user.email)
    return FileResponse(
        path=job.file_path,
        filename=job.file_name or "vocab_export.xlsx",
        media_type=_XLSX_MEDIA,
    )
