"""批次派发 API 路由."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_current_user, get_db, require_role
from vocab_qc.api.schemas.batch import (
    BatchDetailResponse,
    BatchResponse,
    BatchStatsResponse,
    BatchWordItem,
    BatchWordResponse,
    ProduceResponse,
)
from vocab_qc.api.schemas.batch_info import BatchInfoResponse
from vocab_qc.core.models.package_layer import Package
from vocab_qc.core.models.user import User
import logging

from vocab_qc.core.services import batch_service
from vocab_qc.core.services.production_service import run_production

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/batches", tags=["批次"])


def _package_to_info(pkg: Package) -> BatchInfoResponse:
    return BatchInfoResponse(
        id=str(pkg.id),
        name=pkg.name,
        status=pkg.status,
        total_words=pkg.total_words,
        processed_words=pkg.processed_words,
        pass_rate=None,
        created_at=pkg.created_at,
    )


@router.get("", response_model=list[BatchInfoResponse])
def list_batches(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """获取生产批次列表（基于 Package）。"""
    packages = db.query(Package).order_by(Package.created_at.desc()).all()
    return [_package_to_info(pkg) for pkg in packages]


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
    return _package_to_info(pkg)


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


def _run_production_bg(batch_id: int) -> None:
    """后台执行生产流水线，使用独立 session。"""
    from vocab_qc.core.db import SyncSessionLocal

    session = SyncSessionLocal()
    try:
        run_production(session, batch_id)
        session.commit()
    except Exception:
        session.rollback()
        try:
            pkg = session.query(Package).filter_by(id=batch_id).first()
            if pkg:
                pkg.status = "failed"
                session.commit()
        except Exception:
            session.rollback()
        logger.exception("后台生产流水线失败 batch_id=%s", batch_id)
    finally:
        session.close()


@router.post("/{batch_id}/produce", response_model=ProduceResponse)
def produce_batch(
    batch_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """触发生产流水线（后台执行）: 生成内容→Layer1 质检→失败项入队审核。"""
    pkg = db.query(Package).filter_by(id=batch_id).first()
    if pkg is None:
        raise HTTPException(status_code=404, detail="批次不存在")
    if pkg.status == "processing":
        raise HTTPException(status_code=409, detail="该批次正在生产中")
    pkg.status = "processing"
    background_tasks.add_task(_run_production_bg, batch_id)
    return ProduceResponse(batch_id=batch_id, status="processing")


@router.get("/stats", response_model=BatchStatsResponse)
def get_stats(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """审核进度统计。"""
    return batch_service.get_stats(db)
