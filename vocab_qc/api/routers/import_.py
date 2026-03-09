"""数据导入 API 路由."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_db, require_role
from vocab_qc.api.schemas.import_ import ImportResponse
from vocab_qc.core.models.user import User
from vocab_qc.core.services import import_service

router = APIRouter(prefix="/api", tags=["导入"])


@router.post("/import", response_model=ImportResponse)
async def import_file(
    file: UploadFile,
    batch_name: str = "",
    model: str = "gpt-4o-mini",
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """上传文件并导入词汇数据。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")

    if not batch_name.strip():
        batch_name = file.filename.rsplit(".", 1)[0]

    try:
        data = import_service.parse_upload(content, file.filename)
        result = import_service.import_from_json(db, data, batch_name.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")

    return ImportResponse(
        batch_id=result["batch_id"],
        word_count=result["word_count"],
        message=f"成功导入 {result['word_count']} 个词汇",
    )
