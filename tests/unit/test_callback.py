"""AI Gateway 回调端点测试."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vocab_qc.api.main import app
from vocab_qc.core.config import settings
from vocab_qc.core.models.ai_task_queue import AiTaskQueue, AiTaskStatus
from vocab_qc.core.task_queue import TaskQueueService, TaskSpec


@pytest.fixture
def client(db_session):
    from vocab_qc.api.deps import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    # 测试时不检查 IP 白名单
    original_ips = settings.ai_callback_allowed_ips
    settings.ai_callback_allowed_ips = []
    yield TestClient(app)
    settings.ai_callback_allowed_ips = original_ips
    app.dependency_overrides.clear()


def _enqueue_and_submit(db_session: Session, task_no: str = "test-task-001") -> int:
    """辅助：创建一个 submitted 状态的任务，返回 task_id."""
    ids = TaskQueueService.enqueue_tasks(db_session, [TaskSpec(
        batch_key="test:cb",
        phase="generation",
        submit_body={"model": "test", "provider": "P", "api_key": "k", "biz_type": "t", "biz_id": "b"},
    )])
    TaskQueueService.mark_submitted(db_session, ids[0], task_no)
    db_session.flush()
    return ids[0]


class TestCallbackEndpoint:
    def test_completed_callback(self, client, db_session):
        task_id = _enqueue_and_submit(db_session, "task-ok-001")
        resp = client.post("/api/callback/ai-task", json={
            "task_no": "task-ok-001",
            "biz_id": "1",
            "biz_type": "vocab_qc",
            "result": '{"content": "hello world"}',
            "failed_reason": "",
            "provider": "VERTEX",
            "status": "COMPLETED",
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 10000
        task = db_session.query(AiTaskQueue).filter_by(id=task_id).one()
        assert task.status == AiTaskStatus.COMPLETED.value
        assert task.result_data is not None

    def test_failed_callback(self, client, db_session):
        task_id = _enqueue_and_submit(db_session, "task-fail-001")
        resp = client.post("/api/callback/ai-task", json={
            "task_no": "task-fail-001",
            "biz_id": "1",
            "biz_type": "vocab_qc",
            "result": None,
            "failed_reason": "model timeout",
            "provider": "VERTEX",
            "status": "FAILED",
        })
        assert resp.status_code == 200
        task = db_session.query(AiTaskQueue).filter_by(id=task_id).one()
        assert task.status == AiTaskStatus.FAILED.value
        assert "model timeout" in task.error_message

    def test_idempotent_completed(self, client, db_session):
        """同一 task_no 重复回调不报错."""
        _enqueue_and_submit(db_session, "task-idem-001")
        payload = {
            "task_no": "task-idem-001",
            "biz_id": "1",
            "biz_type": "vocab_qc",
            "result": "ok",
            "status": "COMPLETED",
        }
        resp1 = client.post("/api/callback/ai-task", json=payload)
        resp2 = client.post("/api/callback/ai-task", json=payload)
        assert resp1.status_code == 200
        assert resp2.status_code == 200

    def test_unknown_task_no(self, client, db_session):
        """未知 task_no 幂等返回成功."""
        resp = client.post("/api/callback/ai-task", json={
            "task_no": "nonexistent-999",
            "biz_id": "1",
            "biz_type": "vocab_qc",
            "result": "ok",
            "status": "COMPLETED",
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 10000

    def test_pending_status_ignored(self, client, db_session):
        """PENDING 状态的回调不更新任务状态."""
        task_id = _enqueue_and_submit(db_session, "task-pend-001")
        resp = client.post("/api/callback/ai-task", json={
            "task_no": "task-pend-001",
            "biz_id": "1",
            "biz_type": "vocab_qc",
            "result": None,
            "status": "PENDING",
        })
        assert resp.status_code == 200
        task = db_session.query(AiTaskQueue).filter_by(id=task_id).one()
        assert task.status == AiTaskStatus.SUBMITTED.value  # 未改变

    def test_ip_whitelist_blocks(self, db_session):
        """IP 白名单拦截."""
        from vocab_qc.api.deps import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        settings.ai_callback_allowed_ips = ["10.0.0.1"]
        try:
            c = TestClient(app)
            resp = c.post("/api/callback/ai-task", json={
                "task_no": "x", "biz_id": "1", "biz_type": "t", "result": "", "status": "COMPLETED",
            })
            assert resp.status_code == 403
        finally:
            settings.ai_callback_allowed_ips = []
            app.dependency_overrides.clear()


class TestNormalizeCallbackResult:
    def test_string_result(self):
        from vocab_qc.api.routers.callback import normalize_callback_result
        result = normalize_callback_result('{"content": "hello"}')
        assert result["choices"][0]["message"]["content"] == '{"content": "hello"}'

    def test_json_string_with_choices(self):
        from vocab_qc.api.routers.callback import normalize_callback_result
        full_resp = json.dumps({
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"total_tokens": 10},
        })
        result = normalize_callback_result(full_resp)
        assert result["choices"][0]["message"]["content"] == "hi"
        assert result["usage"]["total_tokens"] == 10

    def test_dict_with_choices(self):
        from vocab_qc.api.routers.callback import normalize_callback_result
        result = normalize_callback_result({
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"total_tokens": 5},
        })
        assert result["choices"][0]["message"]["content"] == "hi"

    def test_plain_dict_without_choices(self):
        from vocab_qc.api.routers.callback import normalize_callback_result
        result = normalize_callback_result({"answer": "42"})
        content = result["choices"][0]["message"]["content"]
        assert "42" in content
        assert result["usage"]["total_tokens"] == 0

    def test_none_result(self):
        from vocab_qc.api.routers.callback import normalize_callback_result
        result = normalize_callback_result(None)
        assert result["choices"][0]["message"]["content"] == "null"
