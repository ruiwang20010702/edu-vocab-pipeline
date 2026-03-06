"""质检 API 路由."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_current_user, get_db, get_qc_service, require_role
from vocab_qc.api.schemas import QcRunDetail, QcRunRequest, QcRunResponse, QcSummaryItem, RuleResultResponse
from vocab_qc.core.models import QcRuleResult, QcRun
from vocab_qc.core.models.user import User
from vocab_qc.core.services.qc_service import QcService

router = APIRouter(prefix="/api/qc", tags=["质检"])


@router.post("/run", response_model=QcRunResponse)
def run_qc(
    request: QcRunRequest,
    db: Session = Depends(get_db),
    qc_service: QcService = Depends(get_qc_service),
    _current_user: User = Depends(require_role("admin")),
):
    """触发质检运行."""
    result = qc_service.run_layer1(db, scope=request.scope, dimension=request.dimension)
    return QcRunResponse(**result)


@router.get("/runs/{run_id}", response_model=QcRunDetail)
def get_run_detail(
    run_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """查看运行详情."""
    qc_run = db.query(QcRun).filter_by(id=run_id).first()
    if not qc_run:
        raise HTTPException(status_code=404, detail="Run not found")
    return QcRunDetail.model_validate(qc_run)


@router.get("/runs/{run_id}/results", response_model=list[RuleResultResponse])
def get_run_results(
    run_id: str,
    passed: Optional[bool] = Query(default=None),
    rule_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """查看运行的规则结果."""
    query = db.query(QcRuleResult).filter_by(run_id=run_id)
    if passed is not None:
        query = query.filter_by(passed=passed)
    if rule_id:
        query = query.filter_by(rule_id=rule_id)
    return [RuleResultResponse.model_validate(r) for r in query.all()]


@router.get("/summary", response_model=list[QcSummaryItem])
def get_summary(
    run_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """按规则维度统计通过率."""
    from sqlalchemy import func

    query = db.query(
        QcRuleResult.rule_id,
        QcRuleResult.dimension,
        func.count().label("total"),
        func.sum(func.cast(QcRuleResult.passed, db.bind.dialect.name != "sqlite" and "INTEGER" or "INTEGER")).label("passed_count"),
    ).group_by(QcRuleResult.rule_id, QcRuleResult.dimension)

    if run_id:
        query = query.filter(QcRuleResult.run_id == run_id)

    results = []
    for row in query.all():
        total = row.total
        passed = int(row.passed_count or 0)
        results.append(
            QcSummaryItem(
                rule_id=row.rule_id,
                dimension=row.dimension,
                total=total,
                passed=passed,
                failed=total - passed,
                pass_rate=round(passed / total * 100, 1) if total > 0 else 0,
            )
        )
    return results
