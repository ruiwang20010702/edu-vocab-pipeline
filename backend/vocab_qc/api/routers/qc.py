"""质检 API 路由."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_current_user, get_db, get_qc_service, require_role
from vocab_qc.api.schemas import QcRunDetail, QcRunRequest, QcSummaryItem, RuleResultResponse
from vocab_qc.core.models.user import User
from vocab_qc.core.services.qc_service import QcService

router = APIRouter(prefix="/api/qc", tags=["质检"])


@router.post("/run")
def run_qc(
    request: QcRunRequest,
    db: Session = Depends(get_db),
    qc_service: QcService = Depends(get_qc_service),
    _current_user: User = Depends(require_role("admin", "reviewer")),
):
    """触发质检运行."""
    results: dict = {}
    if 1 in request.layers:
        results["layer1"] = qc_service.run_layer1(db, scope=request.scope, dimension=request.dimension)
    if 2 in request.layers:
        results["layer2"] = qc_service.run_layer2(db, scope=request.scope, dimension=request.dimension)
    db.commit()
    return results


@router.get("/runs/{run_id}", response_model=QcRunDetail)
def get_run_detail(
    run_id: str,
    db: Session = Depends(get_db),
    qc_service: QcService = Depends(get_qc_service),
    _current_user: User = Depends(get_current_user),
):
    """查看运行详情."""
    qc_run = qc_service.get_run(db, run_id)
    if not qc_run:
        raise HTTPException(status_code=404, detail="质检运行记录不存在")
    return QcRunDetail.model_validate(qc_run)


@router.get("/runs/{run_id}/results", response_model=list[RuleResultResponse])
def get_run_results(
    run_id: str,
    passed: Optional[bool] = Query(default=None),
    rule_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    qc_service: QcService = Depends(get_qc_service),
    _current_user: User = Depends(get_current_user),
):
    """查看运行的规则结果."""
    results = qc_service.get_run_results(db, run_id, passed=passed, rule_id=rule_id)
    return [RuleResultResponse.model_validate(r) for r in results]


@router.get("/summary", response_model=list[QcSummaryItem])
def get_summary(
    run_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    qc_service: QcService = Depends(get_qc_service),
    _current_user: User = Depends(get_current_user),
):
    """按规则维度统计通过率."""
    rows = qc_service.get_summary(db, run_id=run_id)
    return [QcSummaryItem(**row) for row in rows]


@router.get("/runs/{run_id}/status")
def get_run_status(
    run_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """查询质检/批量修复任务的进度。"""
    from vocab_qc.core.models.quality_layer import QcRun

    qc_run = db.query(QcRun).filter_by(id=run_id).first()
    if not qc_run:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "done": qc_run.status in ("completed", "failed"),
        "status": qc_run.status,
        "total": qc_run.total_items or 0,
        "completed": (qc_run.passed_items or 0) + (qc_run.failed_items or 0),
        "passed": qc_run.passed_items or 0,
        "failed": qc_run.failed_items or 0,
    }
