"""导出 API 路由."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_db, require_role
from vocab_qc.core.models.user import User
from vocab_qc.core.services.export_service import ExportService

router = APIRouter(prefix="/api/export", tags=["导出"])


@router.get("/word/{word_id}")
def export_word(
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
def export_readiness(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """检查导出就绪状态."""
    service = ExportService()
    return service.get_export_readiness(db)


@router.get("/download")
def download_all(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """下载所有已审核通过的词汇数据 (JSON)."""
    service = ExportService()
    data = service.export_all_approved(db)
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": "attachment; filename=vocab_export.json"},
    )
