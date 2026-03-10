"""批次派发 API 路由."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_current_user, get_db, require_role
from vocab_qc.api.routers.auth import limiter
from vocab_qc.api.schemas.batch import (
    BatchDetailResponse,
    BatchResponse,
    BatchStatsResponse,
    BatchWordItem,
    BatchWordResponse,
    ProduceResponse,
)
from vocab_qc.api.schemas.batch_info import BatchInfoResponse
from vocab_qc.core.models.batch_layer import ReviewBatch
from vocab_qc.core.models.package_layer import Package
from vocab_qc.core.models.user import User
import logging

from vocab_qc.core.services import batch_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/batches", tags=["批次"])

# 线程池用于在后台执行同步生产任务，避免阻塞事件循环
_production_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="production")


def _package_to_info(pkg: Package, db: Session | None = None) -> BatchInfoResponse:
    pass_rate = None
    failed_count = 0

    if db is not None:
        from sqlalchemy import distinct, func
        from vocab_qc.core.models import ContentItem, QcStatus
        from vocab_qc.core.models.package_layer import PackageMeaning

        # 找到该 package 关联的所有 word_id
        word_ids_q = (
            db.query(distinct(ContentItem.word_id))
            .join(PackageMeaning, PackageMeaning.meaning_id == ContentItem.meaning_id)
            .filter(PackageMeaning.package_id == pkg.id)
        )
        word_ids = [r[0] for r in word_ids_q.all()]

        if word_ids:
            total = db.query(func.count(ContentItem.id)).filter(ContentItem.word_id.in_(word_ids)).scalar() or 0
            approved = db.query(func.count(ContentItem.id)).filter(
                ContentItem.word_id.in_(word_ids),
                ContentItem.qc_status == QcStatus.APPROVED.value,
            ).scalar() or 0
            failed = db.query(func.count(ContentItem.id)).filter(
                ContentItem.word_id.in_(word_ids),
                ContentItem.qc_status.in_([
                    QcStatus.LAYER1_FAILED.value,
                    QcStatus.LAYER2_FAILED.value,
                    QcStatus.REJECTED.value,
                ]),
            ).scalar() or 0

            if total > 0:
                pass_rate = round(approved / total * 100, 1)
            failed_count = failed

    return BatchInfoResponse(
        id=str(pkg.id),
        name=pkg.name,
        status=pkg.status,
        total_words=pkg.total_words,
        processed_words=pkg.processed_words,
        pass_rate=pass_rate,
        failed_count=failed_count,
        created_at=pkg.created_at,
    )


@router.get("", response_model=list[BatchInfoResponse])
def list_batches(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """获取生产批次列表（基于 Package）。"""
    packages = db.query(Package).order_by(Package.created_at.desc()).all()
    return [_package_to_info(pkg, db) for pkg in packages]


@router.get("/info/{batch_id}", response_model=BatchInfoResponse)
def get_batch_info(
    batch_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """获取单个生产批次的信息。"""
    pkg = db.query(Package).filter_by(id=batch_id).first()
    if pkg is None:
        raise HTTPException(status_code=404, detail="批次不存在")
    return _package_to_info(pkg, db)


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
    db.commit()
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
    current_user: User = Depends(get_current_user),
):
    """获取批次中的单词和审核项。"""
    # 权限校验：reviewer 只能查看自己的批次，admin 可查看所有
    if current_user.role != "admin":
        review_batch = db.query(ReviewBatch).filter_by(id=batch_id).first()
        if review_batch and review_batch.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权查看此批次")

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


@router.get("/stats", response_model=BatchStatsResponse)
def get_stats(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """审核进度统计。"""
    return batch_service.get_stats(db)


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
    db.commit()
    return {"message": "已跳过"}


def _run_production_bg(batch_id: int) -> None:
    """后台执行生产流水线，每步使用独立 session 避免长事务占用连接。

    流程拆分为 3 步，每步独立事务：
    1. 生成内容 → commit
    2. Layer 1 质检 + 失败项入队 → commit
    3. Layer 2 AI 质检 + 失败项入队 → commit
    """
    from vocab_qc.core.db import SyncSessionLocal
    from vocab_qc.core.services.production_service import (
        step_generate,
        step_qc_layer1,
        step_qc_layer2,
        step_finalize,
    )

    steps = [
        ("generate", step_generate),
        ("qc_layer1", step_qc_layer1),
        ("qc_layer2", step_qc_layer2),
    ]

    for step_name, step_fn in steps:
        session = SyncSessionLocal()
        try:
            step_fn(session, batch_id)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception(
                "后台生产流水线失败 batch_id=%s step=%s", batch_id, step_name
            )
            # 标记 Package 为 failed
            try:
                pkg = session.query(Package).filter_by(id=batch_id).first()
                if pkg:
                    pkg.status = "failed"
                    session.commit()
            except Exception:
                session.rollback()
            finally:
                session.close()
            return
        finally:
            session.close()

    # 所有步骤成功 → 标记完成
    session = SyncSessionLocal()
    try:
        step_finalize(session, batch_id)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("后台生产流水线 finalize 失败 batch_id=%s", batch_id)
    finally:
        session.close()


async def _run_production_bg_async(batch_id: int) -> None:
    """将同步生产任务包装到线程池执行，避免阻塞事件循环。"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_production_executor, _run_production_bg, batch_id)


@router.post("/{batch_id}/produce", response_model=ProduceResponse)
@limiter.limit("5/minute")
def produce_batch(
    request: Request,
    batch_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin", "reviewer")),
):
    """触发生产流水线（后台执行）: 生成内容→Layer1 质检→失败项入队审核。"""
    pkg = db.query(Package).filter_by(id=batch_id).first()
    if pkg is None:
        raise HTTPException(status_code=404, detail="批次不存在")
    if pkg.status == "processing":
        raise HTTPException(status_code=409, detail="该批次正在生产中")
    pkg.status = "processing"
    db.commit()
    background_tasks.add_task(_run_production_bg_async, batch_id)
    return ProduceResponse(batch_id=batch_id, status="processing")
