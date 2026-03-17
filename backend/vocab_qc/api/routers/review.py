"""审核 API 路由."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_current_user, get_db, get_review_service, require_role
from vocab_qc.api.routers.auth import limiter
from vocab_qc.api.schemas.review import (
    ApproveRequest,
    EmbeddedContentItem,
    EmbeddedIssue,
    EmbeddedWord,
    ManualEditRequest,
    RegenerateResponse,
    ReviewItemResponse,
    ReviewListResponse,
)
from vocab_qc.core.models import ContentItem, QcRuleResult, Word
from vocab_qc.core.models.user import User
from vocab_qc.core.security import reject_html_input
from vocab_qc.core.services.review_service import ReviewService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reviews", tags=["审核"])


def _build_review_response(
    review,
    content_items_map: dict[int, ContentItem],
    words_map: dict[int, Word],
    issues_map: dict[int, list[QcRuleResult]],
) -> ReviewItemResponse:
    """将 ORM ReviewItem 转为嵌套响应（使用预加载的数据）。"""
    content_item = content_items_map.get(review.content_item_id)
    word = words_map.get(review.word_id)
    issues = issues_map.get(review.content_item_id, [])

    return ReviewItemResponse(
        id=review.id,
        content_item_id=review.content_item_id,
        word_id=review.word_id,
        meaning_id=review.meaning_id,
        dimension=review.dimension,
        reason=review.reason,
        priority=review.priority,
        status=review.status,
        resolution=review.resolution,
        reviewer=review.reviewer,
        review_note=review.review_note,
        resolved_at=review.resolved_at,
        created_at=review.created_at,
        content_item=EmbeddedContentItem.model_validate(content_item) if content_item else None,
        word=EmbeddedWord.model_validate(word) if word else None,
        issues=[
            EmbeddedIssue(
                id=iss.id,
                content_item_id=iss.content_item_id,
                rule_code=iss.rule_id,
                field=iss.dimension,
                message=iss.detail or "",
                severity="error",
            )
            for iss in issues
        ],
    )


def _batch_enrich(db: Session, reviews: list) -> list[ReviewItemResponse]:
    """批量加载关联数据，避免 N+1 查询。"""
    if not reviews:
        return []

    content_item_ids = [r.content_item_id for r in reviews]
    word_ids = [r.word_id for r in reviews]

    content_items = db.query(ContentItem).filter(ContentItem.id.in_(content_item_ids)).all()
    content_items_map = {ci.id: ci for ci in content_items}

    words = db.query(Word).filter(Word.id.in_(word_ids)).all()
    words_map = {w.id: w for w in words}

    # 只显示最新一次质检的失败问题（排除重新生成前的旧记录）
    latest_run_ids = {
        ci.id: ci.last_qc_run_id for ci in content_items if ci.last_qc_run_id
    }
    all_issues = []
    if latest_run_ids:
        all_issues = (
            db.query(QcRuleResult)
            .filter(
                QcRuleResult.content_item_id.in_(content_item_ids),
                QcRuleResult.passed == False,  # noqa: E712
                QcRuleResult.run_id.in_(set(latest_run_ids.values())),
            )
            .all()
        )
    issues_map: dict[int, list[QcRuleResult]] = {}
    for iss in all_issues:
        issues_map.setdefault(iss.content_item_id, []).append(iss)

    return [_build_review_response(r, content_items_map, words_map, issues_map) for r in reviews]


def _enrich_review(db: Session, review) -> ReviewItemResponse:
    """单条 enrich（供 approve/edit 等单条操作使用）。"""
    return _batch_enrich(db, [review])[0]


@router.get("", response_model=ReviewListResponse)
def list_reviews(
    dimension: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
    _current_user: User = Depends(get_current_user),
):
    """获取待审核队列."""
    items, total = service.get_pending_reviews(db, dimension=dimension, limit=limit, offset=offset)
    return ReviewListResponse(
        items=_batch_enrich(db, items),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{review_id}/approve", response_model=ReviewItemResponse)
def approve_review(
    review_id: int,
    request: Optional[ApproveRequest] = None,
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
    current_user: User = Depends(require_role("admin", "reviewer")),
):
    """通过审核."""
    note = request.note if request else None
    try:
        result = service.approve(
            db, review_id, reviewer=current_user.name,
            note=note, user_id=current_user.id,
        )
        db.commit()
        return _enrich_review(db, result)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="审核项不存在")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception:
        logger.exception("审核通过操作失败 review_id=%s", review_id)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/{review_id}/regenerate", response_model=RegenerateResponse)
@limiter.limit("20/minute")
def regenerate(
    request: Request,
    review_id: int,
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
    current_user: User = Depends(require_role("admin", "reviewer")),
):
    """触发重新生成（≤3次）."""
    try:
        result = service.regenerate(db, review_id, reviewer=current_user.name, user_id=current_user.id)
        db.commit()
        return RegenerateResponse(**result)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="审核项不存在")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception:
        logger.exception("重新生成操作失败 review_id=%s", review_id)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/{review_id}/edit", response_model=RegenerateResponse)
def manual_edit(
    review_id: int,
    request: ManualEditRequest,
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
    current_user: User = Depends(require_role("admin", "reviewer")),
):
    """人工修改 + 自动质检."""
    reject_html_input(request.content, "content")
    reject_html_input(request.content_cn, "content_cn")
    try:
        result = service.manual_edit(
            db,
            review_id,
            reviewer=current_user.name,
            new_content=request.content,
            new_content_cn=request.content_cn,
            user_id=current_user.id,
        )
        db.commit()
        return RegenerateResponse(**result)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="审核项不存在")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception:
        logger.exception("人工修改操作失败 review_id=%s", review_id)
        raise HTTPException(status_code=500, detail="服务器内部错误")
