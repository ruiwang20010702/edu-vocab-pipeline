"""词汇查询 API 路由."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_current_user, get_db
from vocab_qc.api.schemas.word import PaginatedWordResponse, WordDetailResponse
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
