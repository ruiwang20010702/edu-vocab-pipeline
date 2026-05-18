"""批次派发 API 路由."""

import asyncio
import logging
import time as _time
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
    ProducePreviewResponse,
    ProduceRequest,
    ProduceResponse,
)
from vocab_qc.api.schemas.batch_info import BatchInfoResponse
from vocab_qc.core.models.batch_layer import ReviewBatch
from vocab_qc.core.models.package_layer import Package
from vocab_qc.core.models.user import User
from vocab_qc.core.services import batch_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/batches", tags=["批次"])

# 线程池用于在后台执行同步生产任务，避免阻塞事件循环
_production_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="production")


def _bulk_query_package_stats(
    db: Session, package_ids: list[int],
) -> dict[int, tuple[int, int, int]]:
    """批量查询所有 package 的 total/approved/failed 统计，返回 {pkg_id: (total, approved, failed)}。

    只统计本次生产运行产生的数据（ContentItem.updated_at >= Package.started_at），
    避免将历史批次的 QC 失败计入新批次的异常拦截。
    """
    from sqlalchemy import case, func

    from vocab_qc.core.models import ContentItem, QcStatus
    from vocab_qc.core.models.package_layer import PackageWord

    if not package_ids:
        return {}

    rows = (
        db.query(
            PackageWord.package_id,
            func.count(ContentItem.id).label("total"),
            func.sum(case(
                (ContentItem.qc_status == QcStatus.APPROVED.value, 1),
                else_=0,
            )).label("approved"),
            func.sum(case(
                (ContentItem.qc_status.in_([
                    QcStatus.LAYER1_FAILED.value,
                    QcStatus.LAYER2_FAILED.value,
                ]), 1),
                else_=0,
            )).label("failed"),
        )
        .join(PackageWord, PackageWord.word_id == ContentItem.word_id)
        .join(Package, Package.id == PackageWord.package_id)
        .filter(
            PackageWord.package_id.in_(package_ids),
            ContentItem.qc_status != QcStatus.REJECTED.value,
            Package.started_at.isnot(None),
            ContentItem.updated_at >= Package.started_at,
        )
        .group_by(PackageWord.package_id)
        .all()
    )

    return {
        row.package_id: (row.total or 0, int(row.approved or 0), int(row.failed or 0))
        for row in rows
    }


def _package_to_info(
    pkg: Package,
    stats: tuple[int, int, int] | None = None,
) -> BatchInfoResponse:
    pass_rate = None
    failed_count = 0

    if stats is not None:
        total, approved, failed = stats
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
    pkg_ids = [pkg.id for pkg in packages]
    stats_map = _bulk_query_package_stats(db, pkg_ids)
    return [_package_to_info(pkg, stats_map.get(pkg.id)) for pkg in packages]


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
    stats_map = _bulk_query_package_stats(db, [batch_id])
    return _package_to_info(pkg, stats_map.get(batch_id))


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
    logger.info("领取批次 batch_id=%s user=%s batch_size=%d", batch.id, current_user.email, batch_size)
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
    except ValueError:
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


@router.post("/{batch_id}/release")
def release_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "reviewer")),
):
    """释放批次，将未处理的审核项回池。"""
    try:
        batch_service.release_batch(db, batch_id, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return {"message": "批次已释放"}


def _handle_batch_failure(
    session,
    batch_id: int,
    word_ids: set[int],
) -> None:
    """善后处理：将指定词的僵尸 ContentItem 标记为 LAYER1_FAILED 并入队审核。"""
    from vocab_qc.core.models import ContentItem, QcStatus
    from vocab_qc.core.models.enums import ReviewReason
    from vocab_qc.core.services.review_service import ReviewService

    if not word_ids:
        return

    zombie_items = (
        session.query(ContentItem)
        .filter(
            ContentItem.word_id.in_(word_ids),
            ContentItem.qc_status == QcStatus.PENDING.value,
            ContentItem.content == "",
        )
        .all()
    )
    review_svc = ReviewService()
    for item in zombie_items:
        item.qc_status = QcStatus.LAYER1_FAILED.value
        review_svc.create_review_item(
            session, item, ReviewReason.LAYER1_FAILED, priority=10
        )


def _build_smart_batches(
    session, all_word_ids: list[int], settings,
) -> list[list[int]]:
    """按每词 ContentItem 数量贪心分批，确保单批 AI 调用不超限。

    如果无法查到 ContentItem 信息（如首次导入后尚未创建占位），
    回退到按固定词数分批。
    """
    from sqlalchemy import func

    from vocab_qc.core.models.content_layer import ContentItem
    from vocab_qc.core.models.enums import QcStatus

    max_items = settings.production_max_items_per_batch
    fallback_size = settings.production_batch_size

    # 分批 IN 查询每个词的 pending ContentItem 数量
    word_item_counts: dict[int, int] = {}
    for i in range(0, len(all_word_ids), 900):
        chunk = all_word_ids[i:i + 900]
        rows = (
            session.query(ContentItem.word_id, func.count(ContentItem.id))
            .filter(
                ContentItem.word_id.in_(chunk),
                ContentItem.qc_status == QcStatus.PENDING.value,
            )
            .group_by(ContentItem.word_id)
            .all()
        )
        for wid, cnt in rows:
            word_item_counts[wid] = cnt

    # 如果查不到 ContentItem 数据，回退固定分批
    if not word_item_counts:
        return [
            all_word_ids[i:i + fallback_size]
            for i in range(0, len(all_word_ids), fallback_size)
        ]

    # 贪心分批：累加到阈值时开新批（同一个词的所有 item 不会拆分）
    batches: list[list[int]] = []
    current_batch: list[int] = []
    current_count = 0
    for wid in all_word_ids:
        cnt = word_item_counts.get(wid, 7)  # 默认 7 维度
        if current_count + cnt > max_items and current_batch:
            batches.append(current_batch)
            current_batch, current_count = [], 0
        current_batch.append(wid)
        current_count += cnt
    if current_batch:
        batches.append(current_batch)

    logger.info(
        "智能分批: %d 词 → %d 批 (max_items=%d, 平均 %.0f items/批)",
        len(all_word_ids), len(batches), max_items,
        sum(word_item_counts.get(w, 7) for w in all_word_ids) / max(len(batches), 1),
    )
    return batches


def _run_production_bg(batch_id: int, dimensions: set[str] | None = None) -> None:
    """后台执行生产流水线，按词分批处理避免超时。

    每批词独立走完 generate→L1→L2→commit，单批在 1200s 超时内可完成。
    单批失败不影响其他批次，天然支持断点恢复。

    Args:
        dimensions: 可选，仅处理指定维度（None ⇒ 全维度，向后兼容）。
    """
    from vocab_qc.core.circuit_breaker import CircuitBreaker
    from vocab_qc.core.config import settings
    from vocab_qc.core.db import SyncSessionLocal
    from vocab_qc.core.generators.base import _generator_circuit_breaker
    from vocab_qc.core.services.production_service import (
        _get_word_ids_for_package,
        step_finalize,
        step_generate,
        step_qc_layer1,
        step_qc_layer2,
    )

    # 获取全部 word_ids 并排序（确保分批稳定）
    session = SyncSessionLocal()
    try:
        all_word_ids = sorted(_get_word_ids_for_package(session, batch_id))
        # 智能分批：按每词 ContentItem 数量贪心分组，避免多义词导致单批 AI 调用爆炸
        word_batches = _build_smart_batches(session, all_word_ids, settings)
    finally:
        session.close()

    total_batches = len(word_batches)

    steps = [
        ("generate", step_generate),
        ("qc_layer1", step_qc_layer1),
        ("qc_layer2", step_qc_layer2),
    ]

    any_failed = False
    consecutive_failures = 0  # 连续失败批次计数
    max_consecutive_failures = 3  # 连续失败超过此数则终止整个生产

    for batch_idx in range(total_batches):
        word_batch = set(word_batches[batch_idx])

        # 熔断器打开时等待冷却，避免下一批立刻白白失败
        if _generator_circuit_breaker.state == CircuitBreaker.OPEN:
            wait_sec = settings.ai_circuit_breaker_recovery + 5  # 多等 5s 留余量
            logger.warning(
                "熔断器已打开，等待 %ds 冷却后继续 batch %d/%d",
                wait_sec, batch_idx + 1, total_batches,
            )
            _time.sleep(wait_sec)

        logger.info(
            "生产进度: batch %d/%d (%d词) batch_id=%s",
            batch_idx + 1, total_batches, len(word_batch), batch_id,
        )

        batch_ok = True
        for step_name, step_fn in steps:
            session = SyncSessionLocal()
            try:
                step_fn(session, batch_id, word_ids=word_batch, dimensions=dimensions)
                session.commit()
            except Exception:
                session.rollback()
                logger.exception(
                    "生产失败 batch_id=%s sub_batch=%d/%d step=%s",
                    batch_id, batch_idx + 1, total_batches, step_name,
                )
                # 善后：标记本批僵尸项
                try:
                    _handle_batch_failure(session, batch_id, word_batch)
                    session.commit()
                except Exception:
                    session.rollback()
                    logger.exception(
                        "善后处理僵尸 ContentItem 失败 batch_id=%s sub_batch=%d",
                        batch_id, batch_idx + 1,
                    )
                batch_ok = False
                break  # 本批失败，跳到下一批
            finally:
                session.close()

        # 每批完成后更新 processed_words，用绝对值避免重试时重复累加
        if batch_ok:
            completed_words = sum(len(word_batches[i]) for i in range(batch_idx + 1))
            session = SyncSessionLocal()
            try:
                pkg = session.query(Package).filter_by(id=batch_id).first()
                if pkg:
                    pkg.processed_words = completed_words
                session.commit()
            except Exception:
                session.rollback()
                logger.exception(
                    "更新生产进度失败 batch_id=%s sub_batch=%d/%d",
                    batch_id, batch_idx + 1, total_batches,
                )
            finally:
                session.close()

        if not batch_ok:
            any_failed = True
            consecutive_failures += 1
            if consecutive_failures >= max_consecutive_failures:
                logger.error(
                    "连续 %d 批失败，终止生产 batch_id=%s",
                    consecutive_failures, batch_id,
                )
                break
            continue  # 继续下一批
        else:
            consecutive_failures = 0  # 成功则重置计数

    # 全部批次完成 → finalize（有失败批次时标记 failed）
    session = SyncSessionLocal()
    try:
        if any_failed:
            pkg = session.query(Package).filter_by(id=batch_id).first()
            if pkg:
                pkg.status = "failed"
            session.commit()
        else:
            step_finalize(session, batch_id)
            session.commit()
    except Exception:
        session.rollback()
        logger.exception("后台生产流水线 finalize 失败 batch_id=%s", batch_id)
    finally:
        session.close()


async def _run_production_bg_async(batch_id: int, dimensions: set[str] | None = None) -> None:
    """将同步生产任务包装到线程池执行，避免阻塞事件循环。"""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_production_executor, _run_production_bg, batch_id, dimensions)


@router.post("/{batch_id}/produce", response_model=ProduceResponse)
@limiter.limit("5/minute")
def produce_batch(
    request: Request,
    batch_id: int,
    background_tasks: BackgroundTasks,
    body: ProduceRequest | None = None,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin", "reviewer")),
):
    """触发生产流水线（后台执行）: 生成内容→Layer1 质检→失败项入队审核。

    Body 可选：
    - 无 body / body.dimensions=None：维持旧行为，只生成 PENDING ContentItem。
    - body.dimensions=[...]：先重置指定维度（覆盖 approved/failed），再触发生产。
    """
    from datetime import datetime, timedelta, timezone

    from vocab_qc.core.config import settings
    from vocab_qc.core.services.production_service import reset_dimensions_for_regen

    pkg = db.query(Package).filter_by(id=batch_id).first()
    if pkg is None:
        raise HTTPException(status_code=404, detail="批次不存在")

    # 导入中的批次不能触发生产
    if pkg.status == "importing":
        raise HTTPException(status_code=409, detail="批次仍在导入中，请稍候后重试")

    # P3: processing 超时保护——卡住超过阈值时强制重置为 failed
    if pkg.status == "processing":
        if pkg.updated_at and (
            datetime.now(timezone.utc)
            - pkg.updated_at.replace(tzinfo=timezone.utc)
            > timedelta(hours=settings.package_processing_timeout_hours)
        ):
            logger.warning("Package %d processing 超时，强制重置为 failed", batch_id)
            pkg.status = "failed"
            db.commit()
        else:
            raise HTTPException(status_code=409, detail="该批次正在生产中")

    # P4: failed 状态下重置僵尸项，支持断点恢复
    if pkg.status == "failed":
        from vocab_qc.core.models import ContentItem, QcStatus
        from vocab_qc.core.services.production_service import _get_word_ids_for_package

        word_ids = _get_word_ids_for_package(db, batch_id)
        if word_ids:
            db.query(ContentItem).filter(
                ContentItem.word_id.in_(word_ids),
                ContentItem.qc_status == QcStatus.LAYER1_FAILED.value,
                ContentItem.content == "",
            ).update(
                {ContentItem.qc_status: QcStatus.PENDING.value},
                synchronize_session=False,
            )

    # 显式维度子集 → 在切 processing 前清空旧内容（已 approved 也覆盖）
    dimensions_set: set[str] | None = None
    if body and body.dimensions:
        dimensions_set = set(body.dimensions)
        reset_stats = reset_dimensions_for_regen(db, batch_id, dimensions_set, dry_run=False)
        logger.info(
            "重生预重置 package_id=%s dimensions=%s reset=%s",
            batch_id, sorted(dimensions_set), reset_stats,
        )

    pkg.status = "processing"
    pkg.processed_words = 0  # 重置进度，_run_production_bg 会用绝对值重新计算
    db.commit()
    logger.info(
        "触发生产 package_id=%s user=%s dimensions=%s",
        batch_id, _current_user.email, sorted(dimensions_set) if dimensions_set else None,
    )
    background_tasks.add_task(_run_production_bg_async, batch_id, dimensions_set)
    return ProduceResponse(batch_id=batch_id, status="processing")


@router.post("/{batch_id}/produce/preview", response_model=ProducePreviewResponse)
@limiter.limit("20/minute")
def produce_preview(
    request: Request,
    batch_id: int,
    body: ProduceRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin", "reviewer")),
):
    """dry-run 预览：给定维度集合，返回将受影响的 ContentItem / review_items / words 数量。

    用于前端"维度复选框 → 实时显示将影响 X 条"二次确认 UI，不改任何数据。
    """
    from vocab_qc.core.services.production_service import reset_dimensions_for_regen

    pkg = db.query(Package).filter_by(id=batch_id).first()
    if pkg is None:
        raise HTTPException(status_code=404, detail="批次不存在")
    if not body.dimensions:
        raise HTTPException(status_code=422, detail="dimensions 必填且非空")

    stats = reset_dimensions_for_regen(db, batch_id, set(body.dimensions), dry_run=True)
    return ProducePreviewResponse(**stats)
