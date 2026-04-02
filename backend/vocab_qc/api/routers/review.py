"""审核 API 路由."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel
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
from vocab_qc.core.models.quality_layer import QcRun
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
    batch_id: Optional[int] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
    _current_user: User = Depends(get_current_user),
):
    """获取待审核队列."""
    items, total = service.get_pending_reviews(db, dimension=dimension, batch_id=batch_id, limit=limit, offset=offset)
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


@router.post("/{review_id}/mark-not-applicable", response_model=ReviewItemResponse)
def mark_not_applicable(
    review_id: int,
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
    current_user: User = Depends(require_role("admin", "reviewer")),
):
    """标记助记内容为不适用."""
    try:
        result = service.mark_not_applicable(
            db, review_id, reviewer=current_user.name, user_id=current_user.id,
        )
        db.commit()
        return _enrich_review(db, result)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="审核项不存在")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception:
        logger.exception("标记不适用失败 review_id=%s", review_id)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/{review_id}/regenerate", response_model=RegenerateResponse)
@limiter.limit("20/minute")
async def regenerate(
    request: Request,
    review_id: int,
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
    current_user: User = Depends(require_role("admin", "reviewer")),
):
    """触发重新生成（≤3次）."""
    try:
        result = await service.regenerate_async(db, review_id, reviewer=current_user.name, user_id=current_user.id)
        await asyncio.to_thread(db.commit)
        return RegenerateResponse(**result)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="审核项不存在")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception:
        logger.exception("重新生成操作失败 review_id=%s", review_id)
        raise HTTPException(status_code=500, detail="服务器内部错误")


# ---------------------------------------------------------------------------
# 批量重生成（后台异步）
# ---------------------------------------------------------------------------

class BatchRegenerateRequest(BaseModel):
    review_ids: list[int]


@router.post("/batch-regenerate")
async def batch_regenerate(
    body: BatchRegenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "reviewer")),
):
    """提交批量重生成到后台，立即返回 run_id 供轮询进度。"""
    run_id = f"batch-fix-{uuid.uuid4().hex[:8]}"
    qc_run = QcRun(
        id=run_id,
        layer=0,
        scope="batch_regenerate",
        status="running",
        total_items=len(body.review_ids),
        passed_items=0,
        failed_items=0,
        started_at=datetime.now(UTC),
    )
    db.add(qc_run)
    db.commit()

    background_tasks.add_task(
        _batch_regenerate_bg, run_id, body.review_ids,
        current_user.name, current_user.id,
    )
    return {"run_id": run_id}


async def _batch_regenerate_bg(
    run_id: str, review_ids: list[int], reviewer: str, user_id: int,
) -> None:
    """后台批量重生成：每 4 个并发，每个用独立 session。"""
    from vocab_qc.core.db import SyncSessionLocal

    def _update_run(status: str, passed: int = 0, failed: int = 0) -> None:
        s = SyncSessionLocal()
        try:
            qr = s.query(QcRun).filter_by(id=run_id).first()
            if qr:
                qr.passed_items = passed
                qr.failed_items = failed
                qr.status = status
                if status in ("completed", "failed"):
                    qr.finished_at = datetime.now(UTC)
            s.commit()
        finally:
            s.close()

    try:
        service = ReviewService()
        CONCURRENCY = 4
        passed = 0
        failed = 0

        for i in range(0, len(review_ids), CONCURRENCY):
            chunk = review_ids[i:i + CONCURRENCY]

            async def _process_one(rid: int) -> bool:
                session = SyncSessionLocal()
                try:
                    result = await service.regenerate_async(
                        session, rid, reviewer=reviewer, user_id=user_id,
                    )
                    await asyncio.to_thread(session.commit)
                    return result.get("qc_passed", False)
                except Exception:
                    await asyncio.to_thread(session.rollback)
                    logger.exception("batch regenerate failed review_id=%d", rid)
                    return False
                finally:
                    session.close()

            results = await asyncio.gather(
                *[_process_one(rid) for rid in chunk],
                return_exceptions=True,
            )
            for r in results:
                if r is True:
                    passed += 1
                else:
                    failed += 1

            _update_run("running", passed, failed)

        _update_run("completed", passed, failed)
        logger.info(
            "batch regenerate 完成 run_id=%s total=%d passed=%d failed=%d",
            run_id, len(review_ids), passed, failed,
        )
    except Exception:
        logger.exception("batch regenerate 后台任务崩溃 run_id=%s", run_id)
        _update_run("failed", passed, failed)


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
