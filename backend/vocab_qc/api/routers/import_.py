"""数据导入 API 路由."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_db, require_role
from vocab_qc.api.routers.auth import limiter
from vocab_qc.api.schemas.import_ import ImportResponse, PreviewResponse, PreviewRow
from vocab_qc.core.config import settings
from vocab_qc.core.models.user import User
from vocab_qc.core.services import import_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["导入"])

# 后台导入线程池（与生产线程池分离，互不阻塞）
_import_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="import")


@router.post("/import/preview", response_model=PreviewResponse)
@limiter.limit("20/minute")
def preview_file(
    request: Request,
    file: UploadFile,
    _current_user: User = Depends(require_role("admin", "reviewer")),
):
    """预览上传文件的前 5 条数据（不入库）。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    max_size = settings.max_upload_size_mb * 1024 * 1024
    content = file.file.read(max_size + 1)
    if len(content) > max_size:
        raise HTTPException(status_code=413, detail=f"文件大小超过 {settings.max_upload_size_mb}MB 限制")
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")

    safe_filename = Path(file.filename).name

    try:
        data = import_service.parse_upload(content, safe_filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 展平为行: 每个 meaning 一行
    rows: list[PreviewRow] = []
    for entry in data:
        word = entry.get("word", "")
        ipa_uk = entry.get("ipa_uk", "")
        ipa_us = entry.get("ipa_us", "")
        for m in entry.get("meanings", []):
            rows.append(PreviewRow(
                word=word,
                pos=m.get("pos", ""),
                definition=m.get("definition", ""),
                source=m.get("sources", [""])[0] if m.get("sources") else "",
                ipa_uk=ipa_uk,
                ipa_us=ipa_us,
            ))

    total_count = len(rows)
    return PreviewResponse(rows=rows[:5], total_count=total_count)


def _run_import_bg(data: list[dict[str, Any]], batch_name: str, force: bool) -> None:
    """后台线程执行导入，使用独立 Session。"""
    from vocab_qc.core.db import SyncSessionLocal

    session = SyncSessionLocal()
    try:
        import_service.import_from_json(session, data, batch_name, force=force)
        session.commit()
        logger.info("后台导入完成: batch_name=%s", batch_name)
    except Exception:
        session.rollback()
        logger.exception("后台导入失败: batch_name=%s", batch_name)
        # 尝试将 Package 标记为 failed（如果已创建）
        try:
            from vocab_qc.core.models.package_layer import Package
            pkg = session.query(Package).filter_by(name=batch_name).first()
            if pkg:
                pkg.status = "failed"
                session.commit()
        except Exception:
            session.rollback()
    finally:
        session.close()


@router.post("/import", response_model=ImportResponse)
@limiter.limit("10/minute")
def import_file(
    request: Request,
    file: UploadFile,
    batch_name: str = "",
    model: str = "gemini-3-flash-preview|efficiency",
    force: bool = False,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin", "reviewer")),
):
    """上传文件并导入词汇数据。

    小文件（<1000 词）同步执行立即返回结果。
    大文件（≥1000 词）后台异步执行，立即返回 batch_id 和 importing 状态。
    """
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
    batch_name = batch_name.strip()

    # 解析文件（同步，快速报错）
    try:
        data = import_service.parse_upload(content, safe_filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info("触发导入 filename=%s user=%s", safe_filename, _current_user.email)

    # 统计词数，决定同步还是异步
    word_count = len(data)
    _ASYNC_THRESHOLD = 1000  # ≥1000 词走后台

    if word_count >= _ASYNC_THRESHOLD:
        # 大文件：先创建 Package 占位（importing 状态），再后台导入
        from vocab_qc.core.models.package_layer import Package
        existing_pkg = db.query(Package).filter_by(name=batch_name).first()
        if existing_pkg and existing_pkg.status != "pending" and not force:
            raise HTTPException(
                status_code=409,
                detail=f"批次 '{batch_name}' 已在处理中（状态: {existing_pkg.status}），不可重复导入",
            )

        if not existing_pkg:
            pkg = Package(name=batch_name, status="importing", total_words=word_count)
            db.add(pkg)
            db.commit()
            pkg_id = pkg.id
        else:
            existing_pkg.status = "importing"
            existing_pkg.total_words = word_count
            db.commit()
            pkg_id = existing_pkg.id

        # 提交后台任务
        _import_executor.submit(_run_import_bg, data, batch_name, force)

        return ImportResponse(
            batch_id=str(pkg_id),
            word_count=word_count,
            message=f"已提交 {word_count} 个词汇的导入任务（后台处理中）",
        )

    # 小文件：同步执行
    try:
        result = import_service.import_from_json(db, data, batch_name, force=force)
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
