"""审核 API 路由."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_db, get_review_service
from vocab_qc.api.schemas import ApproveRequest, ManualEditRequest, RegenerateResponse, ReviewItemResponse
from vocab_qc.core.services.review_service import ReviewService

router = APIRouter(prefix="/api/reviews", tags=["审核"])


@router.get("", response_model=list[ReviewItemResponse])
def list_reviews(
    dimension: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
):
    """获取待审核队列."""
    items = service.get_pending_reviews(db, dimension=dimension, limit=limit, offset=offset)
    return [ReviewItemResponse.model_validate(item) for item in items]


@router.post("/{review_id}/approve", response_model=ReviewItemResponse)
def approve_review(
    review_id: int,
    request: ApproveRequest,
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
):
    """通过审核."""
    try:
        result = service.approve(db, review_id, reviewer=request.reviewer, note=request.note)
        return ReviewItemResponse.model_validate(result)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{review_id}/regenerate", response_model=RegenerateResponse)
def regenerate(
    review_id: int,
    reviewer: str = Query(...),
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
):
    """触发重新生成（≤3次）."""
    try:
        result = service.regenerate(db, review_id, reviewer=reviewer)
        return RegenerateResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{review_id}/edit", response_model=ReviewItemResponse)
def manual_edit(
    review_id: int,
    request: ManualEditRequest,
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
):
    """人工修改."""
    try:
        result = service.manual_edit(
            db,
            review_id,
            reviewer=request.reviewer,
            new_content=request.new_content,
            new_content_cn=request.new_content_cn,
        )
        return ReviewItemResponse.model_validate(result)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
