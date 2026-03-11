"""词汇查询 API 路由."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_current_user, get_db
from vocab_qc.api.schemas.word import PaginatedWordResponse, WordDetailResponse
from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.enums import QcStatus, ReviewResolution, ReviewStatus
from vocab_qc.core.models.quality_layer import ReviewItem
from datetime import datetime, UTC
from vocab_qc.core.models.user import User
from vocab_qc.core.services import word_service

router = APIRouter(prefix="/api/words", tags=["词汇"])


@router.get("", response_model=PaginatedWordResponse)
def list_words(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    q: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """分页查询词汇列表。"""
    return word_service.list_words(db, page=page, limit=limit, q=q)


@router.get("/{word_id}", response_model=WordDetailResponse)
def get_word(
    word_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """获取单词详情。"""
    result = word_service.get_word_detail(db, word_id)
    if result is None:
        raise HTTPException(status_code=404, detail="单词不存在")
    return result


@router.post("/content-items/{content_item_id}/regenerate")
def regenerate_content_item(
    content_item_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """直接对 ContentItem 重新生成 + 质检（用于 rejected 等非审核队列项）。"""
    from vocab_qc.core.services.review_service import ReviewService

    item = db.query(ContentItem).filter_by(id=content_item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="内容项不存在")

    # 重置状态为 pending，触发生成
    item.qc_status = QcStatus.PENDING.value
    item.content = ""
    db.flush()

    # 调用生成器
    ReviewService._do_regenerate(db, item)

    # 如果生成器标记为 rejected（类型不适用），resolve 关联 review 并返回
    if item.qc_status == QcStatus.REJECTED.value:
        review = db.query(ReviewItem).filter_by(
            content_item_id=item.id, status=ReviewStatus.PENDING.value
        ).first()
        if review:
            review.status = ReviewStatus.RESOLVED.value
            review.resolution = ReviewResolution.REGENERATE.value
            review.resolved_at = datetime.now(UTC)
        db.commit()
        return {
            "success": True,
            "qc_passed": False,
            "message": "该助记类型不适用，已标记为不适用",
            "new_status": "rejected",
            "new_content": "",
        }

    # 重置为 pending 再跑质检
    item.qc_status = QcStatus.PENDING.value
    db.flush()

    qc_passed = ReviewService._run_qc_for_item(db, item)

    if qc_passed:
        item.qc_status = QcStatus.APPROVED.value
        # resolve 关联的 pending review_item
        review = db.query(ReviewItem).filter_by(
            content_item_id=item.id, status=ReviewStatus.PENDING.value
        ).first()
        if review:
            review.status = ReviewStatus.RESOLVED.value
            review.resolution = ReviewResolution.REGENERATE.value
            review.resolved_at = datetime.now(UTC)
        message = "重新生成成功，质检通过"
    else:
        message = "重新生成完成，但质检未通过"

    db.commit()
    return {
        "success": True,
        "qc_passed": qc_passed,
        "message": message,
        "new_status": item.qc_status,
        "new_content": item.content,
    }


class ManualEditRequest(BaseModel):
    content: str
    content_cn: Optional[str] = None


@router.post("/content-items/{content_item_id}/manual-edit")
def manual_edit_content_item(
    content_item_id: int,
    body: ManualEditRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """手动编辑 ContentItem 内容 + 自动质检（用于 rejected 等非审核队列项）。"""
    from vocab_qc.core.services.review_service import ReviewService

    item = db.query(ContentItem).filter_by(id=content_item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="内容项不存在")

    # 写入用户提供的内容
    item.content = body.content
    if body.content_cn is not None:
        item.content_cn = body.content_cn
    item.qc_status = QcStatus.PENDING.value
    db.flush()

    # 运行质检
    qc_passed = ReviewService._run_qc_for_item(db, item)

    if qc_passed:
        item.qc_status = QcStatus.APPROVED.value
        # resolve 关联的 pending review_item
        review = db.query(ReviewItem).filter_by(
            content_item_id=item.id, status=ReviewStatus.PENDING.value
        ).first()
        if review:
            review.status = ReviewStatus.RESOLVED.value
            review.resolution = ReviewResolution.MANUAL_EDIT.value
            review.resolved_at = datetime.now(UTC)
        message = "保存成功，质检通过"
    else:
        message = "已保存，但质检未通过"

    db.commit()
    return {
        "success": True,
        "qc_passed": qc_passed,
        "message": message,
        "new_status": item.qc_status,
        "new_content": item.content,
    }
