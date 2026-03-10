"""数据导入 API 路由."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_db, require_role
from vocab_qc.api.routers.auth import limiter
from vocab_qc.api.schemas.import_ import ImportResponse
from vocab_qc.core.config import settings
from vocab_qc.core.models.user import User
from vocab_qc.core.services import import_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["导入"])


@router.post("/import", response_model=ImportResponse)
@limiter.limit("10/minute")
def import_file(
    request: Request,
    file: UploadFile,
    batch_name: str = "",
    model: str = "gemini-3-flash-preview",
    force: bool = False,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin", "reviewer")),
):
    """上传文件并导入词汇数据。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    max_size = settings.max_upload_size_mb * 1024 * 1024
    content = file.file.read(max_size + 1)
    if len(content) > max_size:
        raise HTTPException(status_code=413, detail=f"文件大小超过 {settings.max_upload_size_mb}MB 限制")
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")

    # 文件名净化：去除路径遍历字符
    safe_filename = Path(file.filename).name

    # 内容嗅探：验证文件内容与扩展名匹配
    filename_lower = safe_filename.lower()
    if filename_lower.endswith(".json"):
        try:
            json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="文件内容不是有效的 JSON")
    elif filename_lower.endswith(".csv"):
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="文件内容不是有效的 CSV（非 UTF-8 编码）")

    if not batch_name.strip():
        batch_name = (safe_filename.rsplit(".", 1)[0])[:100] or "未命名批次"

    try:
        data = import_service.parse_upload(content, safe_filename)
        result = import_service.import_from_json(db, data, batch_name.strip(), force=force)
    except ValueError as e:
        status = 409 if "不可重复导入" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e))
    except Exception:
        logger.exception("导入失败")
        raise HTTPException(status_code=500, detail="导入失败，请稍后重试")

    db.commit()
    return ImportResponse(
        batch_id=result["batch_id"],
        word_count=result["word_count"],
        message=f"成功导入 {result['word_count']} 个词汇",
    )
