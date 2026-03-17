"""词汇查询 API 路由."""

from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_current_user, get_db, require_role
from vocab_qc.api.schemas.word import PaginatedWordResponse, WordDetailResponse
from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.enums import QcStatus, ReviewResolution, ReviewStatus
from vocab_qc.core.models.quality_layer import ReviewItem
from vocab_qc.core.models.user import User
from vocab_qc.core.services import word_service

router = APIRouter(prefix="/api/words", tags=["词汇"])


def _run_layer1_only(session: Session, content_item: ContentItem) -> bool:
    """仅运行 Layer 1 算法校验，返回是否全部通过（用于总表管理快速编辑）。"""
    from vocab_qc.core.models.data_layer import Meaning, Phonetic, Word
    from vocab_qc.core.qc.runner import Layer1Runner

    word = session.query(Word).filter_by(id=content_item.word_id).first()
    word_text = word.word if word else ""

    meaning_texts: dict[int, str] = {}
    extra: dict = {"content_cn": content_item.content_cn or ""}

    if content_item.meaning_id:
        meaning = session.query(Meaning).filter_by(id=content_item.meaning_id).first()
        if meaning:
            meaning_texts[meaning.id] = meaning.definition
            if meaning.pos:
                extra["pos"] = meaning.pos

    phonetic = session.query(Phonetic).filter_by(word_id=content_item.word_id).first()
    if phonetic:
        extra["ipa"] = phonetic.ipa
        extra["syllables"] = phonetic.syllables

    word_texts = {content_item.word_id: word_text}
    extra_kwargs = {content_item.id: extra}

    l1_runner = Layer1Runner()
    l1_runner.run(session, [content_item], word_texts, meaning_texts, extra_kwargs)

    return content_item.qc_status == QcStatus.LAYER1_PASSED.value


@router.get("", response_model=PaginatedWordResponse)
def list_words(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    q: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None, pattern="^(approved|in_progress)$"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """分页查询词汇列表。"""
    return word_service.list_words(db, page=page, limit=limit, q=q, status=status)


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
    _current_user: User = Depends(require_role("admin")),
):
    """直接对 ContentItem 重新生成 + 质检（仅管理员，用于 rejected 等非审核队列项）。"""
    from vocab_qc.core.services.batch_service import update_batch_progress
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
            update_batch_progress(db, review.batch_id)
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
            update_batch_progress(db, review.batch_id)
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
    force_approve: bool = False


@router.post("/content-items/{content_item_id}/manual-edit")
def manual_edit_content_item(
    content_item_id: int,
    body: ManualEditRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "reviewer")),
):
    """手动编辑 ContentItem 内容 + 自动质检（管理员或审核员）。"""
    from vocab_qc.core.services.audit_service import log_action
    from vocab_qc.core.services.batch_service import update_batch_progress
    from vocab_qc.core.services.review_service import ReviewService

    item = db.query(ContentItem).filter_by(id=content_item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="内容项不存在")

    # 并发检查：如果关联审核项已分配给其他人，拒绝编辑
    review = db.query(ReviewItem).filter_by(
        content_item_id=item.id, status=ReviewStatus.PENDING.value
    ).first()
    if review and review.assigned_to_id and review.assigned_to_id != current_user.id:
        raise HTTPException(status_code=409, detail="该审核项已分配给其他审核员")

    old_content = item.content

    # XSS 防护：拒绝包含 HTML 的输入
    from vocab_qc.core.security import reject_html_input
    reject_html_input(body.content, "content")
    if body.content_cn is not None:
        reject_html_input(body.content_cn, "content_cn")

    # 写入用户提供的内容
    item.content = body.content
    if body.content_cn is not None:
        item.content_cn = body.content_cn
    item.qc_status = QcStatus.PENDING.value
    db.flush()

    # 运行完整质检（Layer 1 + Layer 2）
    qc_passed = ReviewService._run_qc_for_item(db, item)

    # 强制通过：人工判断内容正确，跳过 QC 结果
    if body.force_approve:
        qc_passed = True

    if qc_passed:
        item.qc_status = QcStatus.APPROVED.value
        # resolve 关联的 pending review_item
        if review is None:
            review = db.query(ReviewItem).filter_by(
                content_item_id=item.id, status=ReviewStatus.PENDING.value
            ).first()
        if review:
            review.status = ReviewStatus.RESOLVED.value
            review.resolution = ReviewResolution.MANUAL_EDIT.value
            review.resolved_at = datetime.now(UTC)
            review.reviewer = current_user.name
            update_batch_progress(db, review.batch_id)
        message = "已强制通过" if body.force_approve else "保存成功，质检通过"
    else:
        message = "已保存，但质检未通过"

    # 审计日志
    log_action(
        db,
        entity_type="content_item",
        entity_id=item.id,
        action="force_approve" if body.force_approve else "manual_edit",
        actor=current_user.name,
        old_value={"content": old_content},
        new_value={"content": body.content},
    )

    # 查询最新质检失败问题
    from vocab_qc.core.models.quality_layer import QcRuleResult
    new_issues = []
    if item.last_qc_run_id and not qc_passed:
        failed_results = (
            db.query(QcRuleResult)
            .filter_by(content_item_id=item.id, run_id=item.last_qc_run_id, passed=False)
            .all()
        )
        new_issues = [
            {"rule_id": r.rule_id, "field": r.dimension, "message": r.detail or ""}
            for r in failed_results
        ]

    db.commit()
    return {
        "success": True,
        "qc_passed": qc_passed,
        "message": message,
        "new_status": item.qc_status,
        "new_content": item.content,
        "new_issues": new_issues,
    }
