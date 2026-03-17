"""导出 API 路由."""

import json
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_db, require_role
from vocab_qc.api.routers.auth import limiter
from vocab_qc.core.models.user import User
from vocab_qc.core.services.export_service import ExportService, _iter_approved_batches

router = APIRouter(prefix="/api/export", tags=["导出"])


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
    """下载所有已通过词汇数据 (Excel)."""
    service = ExportService()
    buf = service.export_to_excel(db)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=vocab_export.xlsx"},
    )
