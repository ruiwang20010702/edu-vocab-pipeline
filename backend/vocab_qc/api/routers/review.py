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
from vocab_qc.core.models.enums import QcStatus, ReviewResolution, ReviewStatus
from vocab_qc.core.models.quality_layer import QcRun
from vocab_qc.core.models.user import User
from vocab_qc.core.security import reject_html_input
from vocab_qc.core.services.audit_service import log_action
from vocab_qc.core.services.review_service import ReviewService, _lookup_package_id


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
@limiter.limit("100/minute")
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
    """后台批量重生成：任务队列 + 回调模式（和生产批次相同路径）。

    Phase 1: 批量预加载（DB 操作）
    Phase 2: 批量入队 → PollingPool 提交 → 回调等待（零轮询）
    Phase 3: 收集 AI 结果 → 逐条写回 + 质检
    """
    import json as _json

    from vocab_qc.core.db import SyncSessionLocal
    from vocab_qc.core.generators.base import _strip_markdown_fences, extract_usage, parse_ai_response
    from vocab_qc.core.models.ai_task_queue import AiTaskStatus
    from vocab_qc.core.polling_pool import PollingPool
    from vocab_qc.core.task_queue import TaskQueueService, TaskSpec

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

    passed = 0
    failed = 0

    try:
        service = ReviewService()
        session = SyncSessionLocal()

        try:
            # ── Phase 1: 批量预加载（在线程中执行，避免阻塞 event loop）──
            def _phase1_preload() -> tuple[dict[int, dict], int]:
                _ctxs: dict[int, dict] = {}
                _failed = 0
                for rid in review_ids:
                    try:
                        ctx = service._regen_preload(session, rid, reviewer, user_id)
                        if ctx.get("early_return"):
                            _failed += 1
                        else:
                            _ctxs[rid] = ctx
                    except Exception:
                        logger.exception("batch regen preload failed review_id=%d", rid)
                        _failed += 1
                session.commit()
                return _ctxs, _failed

            ctxs, p1_failed = await asyncio.to_thread(_phase1_preload)
            failed += p1_failed

            if not ctxs:
                _update_run("completed", passed, failed)
                return

            # ── Phase 2: 批量入队 + 提交 + 等待回调 ──
            batch_key = f"regen:{uuid.uuid4().hex[:8]}"
            specs: list[TaskSpec] = []

            for rid, ctx in ctxs.items():
                submit_body = ctx["generator"].make_submit_body(
                    word=ctx["word_text"],
                    meaning=ctx["meaning_text"],
                    pos=ctx["pos"],
                    _preloaded_config=ctx["ai_config"],
                )
                ci_id = ctx["content_item"].id
                specs.append(TaskSpec(
                    batch_key=batch_key,
                    phase="regeneration",
                    submit_body=submit_body,
                    content_item_id=ci_id,
                    dimension=ctx["content_item"].dimension,
                    ai_model=ctx["ai_config"].model,
                    word_id=ctx["content_item"].word_id,
                ))

            # 入队（独立 session，不破坏主事务）
            eq_session = SyncSessionLocal()
            try:
                TaskQueueService.enqueue_tasks(eq_session, specs)
                eq_session.commit()
            finally:
                eq_session.close()

            # 提交到 Gateway + 等待回调完成
            pool = PollingPool.get_instance()
            await pool.submit_batch(batch_key)
            _update_run("running", passed, failed)
            await pool.wait_for_batch(batch_key, timeout=600)

            # ── Phase 3: 收集结果 + 写回 + 批量质检 ──
            # 拆为三轮：① 写回+L1  ② 批量L2  ③ 更新状态
            # 避免逐条 L2 QC 串行等 gateway 回调（26条×10s→4min），改为1次批量提交
            def _phase3_writeback_and_l1() -> tuple[int, list[tuple[int, dict]]]:
                """第一轮：写回 AI 结果 + 运行 L1 QC，返回 (fail_count, l1_passed_items)."""
                from vocab_qc.core.models.quality_layer import AiUsageLog
                from vocab_qc.core.qc.runner import Layer1Runner
                from vocab_qc.core.models.data_layer import Meaning, Phonetic, Word

                f = 0
                session.expire_all()

                completed_tasks = TaskQueueService.collect_completed(session, batch_key)
                task_map = {t.content_item_id: t for t in completed_tasks}

                # 收集需要 L1 的 items + 预取辅助数据
                l1_items: list[ContentItem] = []
                l1_ctxs: list[tuple[int, dict]] = []  # (rid, ctx)
                word_ids: set[int] = set()
                meaning_ids: set[int] = set()

                for rid, ctx in ctxs.items():
                    ci = ctx["content_item"]
                    ci_id = ci.id
                    task = task_map.get(ci_id)

                    if task is None or task.status == AiTaskStatus.FAILED.value:
                        f += 1
                        continue

                    try:
                        result_data = task.result_data or {}
                        raw = _strip_markdown_fences(parse_ai_response(result_data))
                        gen_result = _json.loads(raw)

                        # 记录 AI 用量
                        usage = extract_usage(result_data)
                        ai_config = ctx["ai_config"]
                        if usage and usage.total_tokens > 0:
                            session.add(AiUsageLog(
                                phase="generation",
                                dimension=ci.dimension,
                                ai_model=ai_config.model,
                                prompt_tokens=usage.prompt_tokens,
                                completion_tokens=usage.completion_tokens,
                                total_tokens=usage.total_tokens,
                                estimated_cost_usd=ctx["estimate_cost"](ai_config.model, usage),
                                word_id=ci.word_id,
                                content_item_id=ci.id,
                                package_id=_lookup_package_id(session, ci.word_id),
                            ))

                        if ci.dimension.startswith("mnemonic_"):
                            gen_result = ctx["generator"]._process_result(gen_result)

                        # 处理 rejected（助记类型不适用）
                        if gen_result.get("valid") is False:
                            ci.content = ""
                            ci.qc_status = QcStatus.REJECTED.value
                            # G 方案：rejected 也填 prompt 版本指纹（与 _regen_writeback_and_qc 行为一致）
                            ci.generated_with_prompt_id = ai_config.prompt_id
                            ci.generated_with_prompt_hash = ai_config.prompt_hash
                            review = ctx["review"]
                            review.status = ReviewStatus.RESOLVED.value
                            review.resolution = ReviewResolution.REGENERATE.value
                            review.reviewer = reviewer
                            review.resolved_at = datetime.now(UTC)
                            session.flush()
                            service._update_batch_progress(session, review.batch_id)
                            # rejected 算通过（不需要再修）
                            l1_ctxs.append((rid, ctx))
                            ctx["_qc_result"] = "rejected"
                            continue

                        # 写入生成结果
                        ci.content = gen_result.get("content", "")
                        if gen_result.get("content_cn"):
                            ci.content_cn = gen_result["content_cn"]

                        ci.qc_status = QcStatus.PENDING.value
                        session.flush()

                        l1_items.append(ci)
                        l1_ctxs.append((rid, ctx))
                        word_ids.add(ci.word_id)
                        if ci.meaning_id:
                            meaning_ids.add(ci.meaning_id)

                    except Exception:
                        logger.exception("batch regen writeback failed ci=%d", ci_id)
                        f += 1

                # 批量预取辅助数据
                word_texts: dict[int, str] = {}
                meaning_texts: dict[int, str] = {}
                extra_kwargs: dict[int, dict] = {}

                if l1_items:
                    for w in session.query(Word).filter(Word.id.in_(word_ids)).all():
                        word_texts[w.id] = w.word
                    meaning_pos: dict[int, str] = {}
                    if meaning_ids:
                        for m in session.query(Meaning).filter(Meaning.id.in_(meaning_ids)).all():
                            meaning_texts[m.id] = m.definition
                            if m.pos:
                                meaning_pos[m.id] = m.pos
                    phonetics = {
                        ph.word_id: ph
                        for ph in session.query(Phonetic).filter(Phonetic.word_id.in_(word_ids)).all()
                    }

                    for ci in l1_items:
                        extra: dict = {"content_cn": ci.content_cn or ""}
                        if ci.meaning_id and ci.meaning_id in meaning_pos:
                            extra["pos"] = meaning_pos[ci.meaning_id]
                        ph = phonetics.get(ci.word_id)
                        if ph:
                            extra["ipa_uk"] = ph.ipa_uk or ""
                            extra["ipa_us"] = ph.ipa_us or ""
                            extra["syllables"] = ph.syllables
                        extra_kwargs[ci.id] = extra

                    # 批量 L1 QC
                    l1_runner = Layer1Runner()
                    l1_runner.run(session, l1_items, word_texts, meaning_texts, extra_kwargs)

                # 区分 L1 通过 / 失败
                l1_passed: list[tuple[int, dict]] = []
                for rid, ctx in l1_ctxs:
                    ci = ctx["content_item"]
                    if ctx.get("_qc_result") == "rejected":
                        l1_passed.append((rid, ctx))
                        continue
                    if ci.qc_status == QcStatus.LAYER1_PASSED.value:
                        l1_passed.append((rid, ctx))
                    else:
                        f += 1
                        # L1 失败的也要记录审计日志和更新进度
                        counter = ctx["counter"]
                        log_action(
                            session,
                            entity_type="review_item",
                            entity_id=ctx["review"].id,
                            action="regenerate",
                            actor=reviewer,
                            new_value={"retry_count": counter.count, "qc_passed": False},
                        )
                        service._update_batch_progress(session, ctx["review"].batch_id)

                session.commit()

                # 保存批量预取数据供 L2 使用
                ctx_store = {
                    "word_texts": word_texts,
                    "meaning_texts": meaning_texts,
                    "extra_kwargs": extra_kwargs,
                }
                return f, l1_passed, ctx_store

            p3_result = await asyncio.to_thread(_phase3_writeback_and_l1)
            p3_f1, l1_passed_items, ctx_store = p3_result
            failed += p3_f1

            # ── Phase 3b: 批量 L2 QC（1 次 gateway 提交 + 1 次等待）──
            l2_need = []  # 需要跑 L2 的 (rid, ctx)
            l2_skip = []  # 不需要 L2 的 (rid, ctx)（rejected 或无 L2 规则的维度）

            if l1_passed_items:
                from vocab_qc.core.qc.layer2.runner import Layer2Runner
                l2_runner = Layer2Runner()

                for rid, ctx in l1_passed_items:
                    ci = ctx["content_item"]
                    if ctx.get("_qc_result") == "rejected":
                        l2_skip.append((rid, ctx))
                    elif ci.dimension in l2_runner._unified_checkers:
                        l2_need.append((rid, ctx))
                    else:
                        l2_skip.append((rid, ctx))

                if l2_need:
                    def _phase3b_l2() -> None:
                        l2_items = [ctx["content_item"] for _, ctx in l2_need]
                        # 取任一 word_id 查 package_id（同批次通常属于同一个 package）
                        pkg_id = _lookup_package_id(session, l2_items[0].word_id)
                        l2_runner.run(
                            session, l2_items,
                            ctx_store["word_texts"],
                            ctx_store["meaning_texts"],
                            extra_kwargs=ctx_store["extra_kwargs"],
                            package_id=pkg_id,
                        )
                        session.commit()

                    await asyncio.to_thread(_phase3b_l2)

            # ── Phase 3c: 根据 QC 结果更新 review 状态 ──
            def _phase3c_update_status() -> tuple[int, int]:
                p, f = 0, 0
                session.expire_all()

                all_items = l2_need + l2_skip
                for rid, ctx in all_items:
                    ci = ctx["content_item"]
                    review = ctx["review"]
                    counter = ctx["counter"]

                    if ctx.get("_qc_result") == "rejected":
                        p += 1
                        continue

                    # 判断最终 QC 是否通过
                    qc_passed = ci.qc_status in (
                        QcStatus.LAYER1_PASSED.value,
                        QcStatus.LAYER2_PASSED.value,
                    )

                    if qc_passed:
                        ci.qc_status = QcStatus.APPROVED.value
                        review.status = ReviewStatus.RESOLVED.value
                        review.resolution = ReviewResolution.REGENERATE.value
                        review.reviewer = reviewer
                        review.resolved_at = datetime.now(UTC)
                        p += 1
                    else:
                        f += 1

                    log_action(
                        session,
                        entity_type="review_item",
                        entity_id=review.id,
                        action="regenerate",
                        actor=reviewer,
                        new_value={"retry_count": counter.count, "qc_passed": qc_passed},
                    )
                    service._update_batch_progress(session, review.batch_id)

                session.commit()
                return p, f

            p3_passed, p3_failed = await asyncio.to_thread(_phase3c_update_status)
            passed += p3_passed
            failed += p3_failed
        finally:
            session.close()

        _update_run("completed", passed, failed)
        logger.info(
            "batch regenerate 完成 run_id=%s total=%d passed=%d failed=%d",
            run_id, len(review_ids), passed, failed,
        )
    except Exception:
        logger.exception("batch regenerate 崩溃 run_id=%s", run_id)
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
