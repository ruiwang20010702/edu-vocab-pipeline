"""导出 API 路由."""

from fastapi import APIRouter, Depends, HTTPException
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
        raise HTTPException(status_code=404, detail="Word not found")
    return data


@router.get("/readiness")
def export_readiness(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """检查导出就绪状态."""
    service = ExportService()
    return service.get_export_readiness(db)
