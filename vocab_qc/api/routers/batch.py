"""批次派发 API 路由."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_current_user, get_db, require_role
from vocab_qc.api.schemas.batch import (
    BatchDetailResponse,
    BatchResponse,
    BatchStatsResponse,
    BatchWordItem,
    BatchWordResponse,
)
from vocab_qc.core.models.user import User
from vocab_qc.core.services import batch_service

router = APIRouter(prefix="/api/batches", tags=["批次"])


@router.post("/assign", response_model=BatchResponse | None)
def assign_batch(
    batch_size: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "reviewer")),
):
    """领取下一批待审单词。"""
    batch = batch_service.assign_batch(db, user_id=current_user.id, batch_size=batch_size)
    if batch is None:
        return None
    return BatchResponse.model_validate(batch)


@router.get("/current", response_model=BatchResponse | None)
def get_current_batch(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "reviewer")),
):
    """获取我当前的批次。"""
    batch = batch_service.get_my_current_batch(db, user_id=current_user.id)
    if batch is None:
        return None
    return BatchResponse.model_validate(batch)


@router.get("/{batch_id}/words", response_model=BatchDetailResponse)
def get_batch_words(
    batch_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """获取批次中的单词和审核项。"""
    try:
        data = batch_service.get_batch_words(db, batch_id)
    except Exception:
        raise HTTPException(status_code=404, detail="批次不存在")

    batch_resp = BatchResponse.model_validate(data["batch"])
    words_resp = []
    for word_id, items in data["words"].items():
        words_resp.append(
            BatchWordResponse(
                word_id=word_id,
                items=[
                    BatchWordItem(
                        review_id=item.id,
                        content_item_id=item.content_item_id,
                        dimension=item.dimension,
                        reason=item.reason,
                        status=item.status,
                        resolution=item.resolution,
                    )
                    for item in items
                ],
            )
        )
    return BatchDetailResponse(batch=batch_resp, words=words_resp)


@router.post("/{batch_id}/words/{word_id}/skip")
def skip_word(
    batch_id: int,
    word_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "reviewer")),
):
    """跳过某词，释放回池中。"""
    try:
        batch_service.skip_word(db, batch_id, word_id, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "已跳过"}


@router.get("/stats", response_model=BatchStatsResponse)
def get_stats(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """审核进度统计。"""
    return batch_service.get_stats(db)
