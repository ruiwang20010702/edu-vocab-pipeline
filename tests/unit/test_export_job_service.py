"""export_job_service 单元测试：建 / 跑 / 查 / 清理 / 并发去重 / 僵尸超时。"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from vocab_qc.core.models import ExportJob, ExportJobStatus
from vocab_qc.core.services import export_job_service as svc
from vocab_qc.core.services.export_service import ExportService


@pytest.fixture
def export_dir(tmp_path, monkeypatch):
    """导出落盘目录指向临时目录，保持测试 hermetic。"""
    d = tmp_path / "exports"
    monkeypatch.setattr(svc, "EXPORT_DIR", d)
    return d


def test_create_job_new(db_session):
    job = svc.create_job(db_session, "a@test.com")
    assert job.id is not None
    assert job.status == ExportJobStatus.PENDING.value
    assert job.created_by == "a@test.com"


def test_create_job_dedupe(db_session):
    """已有未完成任务 → 第二次 create 复用，不重复建。"""
    j1 = svc.create_job(db_session, "a@test.com")
    j2 = svc.create_job(db_session, "b@test.com")
    assert j1.id == j2.id
    assert db_session.query(ExportJob).count() == 1


def test_run_job_completes(db_session, export_dir):
    """空库也应产出文件（仅表头），任务转 completed。"""
    job = svc.create_job(db_session, "a@test.com")
    svc.run_job(db_session, job.id)
    db_session.refresh(job)
    assert job.status == ExportJobStatus.COMPLETED.value
    assert job.file_path and Path(job.file_path).exists()
    assert job.file_size and job.file_size > 0
    assert job.file_name and job.file_name.endswith(".xlsx")


def test_run_job_failure_marks_failed(db_session, export_dir, monkeypatch):
    """导出构建抛异常 → 任务转 failed 且记录 error_message，不卡在 running。"""

    def boom(self, session, output_path=None):
        raise RuntimeError("构建炸了")

    monkeypatch.setattr(ExportService, "export_to_excel", boom)
    job = svc.create_job(db_session, "a@test.com")
    svc.run_job(db_session, job.id)
    db_session.refresh(job)
    assert job.status == ExportJobStatus.FAILED.value
    assert "构建炸了" in (job.error_message or "")


def test_get_job_stale_running_times_out(db_session):
    """running 超 JOB_TIMEOUT 的僵尸任务 → get_job 判 failed。"""
    job = svc.create_job(db_session, "a@test.com")
    job.status = ExportJobStatus.RUNNING.value
    job.started_at = datetime.now(UTC) - timedelta(minutes=21)
    db_session.commit()
    got = svc.get_job(db_session, job.id)
    assert got is not None
    assert got.status == ExportJobStatus.FAILED.value


def test_cleanup_old_removes_file_and_row(db_session, export_dir):
    export_dir.mkdir(parents=True, exist_ok=True)
    f = export_dir / "old.xlsx"
    f.write_text("x")
    job = ExportJob(
        status=ExportJobStatus.COMPLETED.value, created_by="a@test.com", file_path=str(f)
    )
    db_session.add(job)
    db_session.commit()
    job.created_at = datetime.now(UTC) - timedelta(hours=25)  # backdate 到 TTL 之前
    db_session.commit()

    n = svc.cleanup_old(db_session)
    assert n == 1
    assert not f.exists()
    assert db_session.query(ExportJob).count() == 0
