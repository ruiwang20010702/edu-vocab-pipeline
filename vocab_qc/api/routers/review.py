"""审核 API 路由."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_current_user, get_db, get_review_service, require_role
from vocab_qc.api.schemas.review import (
    ApproveRequest,
    EmbeddedContentItem,
    EmbeddedIssue,
    EmbeddedWord,
    ManualEditRequest,
    RegenerateResponse,
    ReviewItemResponse,
)
from vocab_qc.core.models import ContentItem, QcRuleResult, Word
from vocab_qc.core.models.user import User
from vocab_qc.core.services.review_service import ReviewService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reviews", tags=["审核"])


def _enrich_review(db: Session, review) -> ReviewItemResponse:
    """将 ORM ReviewItem 转为嵌套响应。"""
    content_item = db.query(ContentItem).filter_by(id=review.content_item_id).first()
    word = db.query(Word).filter_by(id=review.word_id).first()
    issues = (
        db.query(QcRuleResult)
        .filter_by(content_item_id=review.content_item_id, passed=False)
        .all()
    )

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


@router.get("", response_model=list[ReviewItemResponse])
def list_reviews(
    dimension: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
    _current_user: User = Depends(get_current_user),
):
    """获取待审核队列."""
    items = service.get_pending_reviews(db, dimension=dimension, limit=limit, offset=offset)
    return [_enrich_review(db, item) for item in items]


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
        result = service.approve(db, review_id, reviewer=current_user.name, note=note, user_id=current_user.id)
        return _enrich_review(db, result)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="审核项不存在")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception:
        logger.exception("审核通过操作失败 review_id=%s", review_id)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/{review_id}/regenerate", response_model=RegenerateResponse)
def regenerate(
    review_id: int,
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
    current_user: User = Depends(require_role("admin", "reviewer")),
):
    """触发重新生成（≤3次）."""
    try:
        result = service.regenerate(db, review_id, reviewer=current_user.name, user_id=current_user.id)
        return RegenerateResponse(**result)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="审核项不存在")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception:
        logger.exception("重新生成操作失败 review_id=%s", review_id)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/{review_id}/edit", response_model=ReviewItemResponse)
def manual_edit(
    review_id: int,
    request: ManualEditRequest,
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
    current_user: User = Depends(require_role("admin", "reviewer")),
):
    """人工修改."""
    try:
        result = service.manual_edit(
            db,
            review_id,
            reviewer=current_user.name,
            new_content=request.content,
            new_content_cn=request.content_cn,
            user_id=current_user.id,
        )
        return _enrich_review(db, result)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="审核项不存在")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception:
        logger.exception("人工修改操作失败 review_id=%s", review_id)
        raise HTTPException(status_code=500, detail="服务器内部错误")
