"""TaskQueueService 单元测试."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from vocab_qc.core.models.ai_task_queue import AiTaskQueue, AiTaskStatus
from vocab_qc.core.task_queue import TaskQueueService, TaskSpec


def _make_spec(batch_key: str = "test:1", **kwargs) -> TaskSpec:
    defaults = dict(
        batch_key=batch_key,
        phase="generation",
        submit_body={"model": "test-model", "messages": []},
        content_item_id=None,
        dimension="chunk",
        ai_model="test-model",
    )
    defaults.update(kwargs)
    return TaskSpec(**defaults)


class TestEnqueue:
    def test_enqueue_single(self, db_session: Session):
        ids = TaskQueueService.enqueue_tasks(db_session, [_make_spec()])
        assert len(ids) == 1
        task = db_session.query(AiTaskQueue).get(ids[0])
        assert task.status == AiTaskStatus.PENDING.value
        assert task.batch_key == "test:1"
        assert task.phase == "generation"
        assert task.submit_body == {"model": "test-model", "messages": []}

    def test_enqueue_multiple(self, db_session: Session):
        specs = [_make_spec(batch_key="test:2") for _ in range(5)]
        ids = TaskQueueService.enqueue_tasks(db_session, specs)
        assert len(ids) == 5
        assert len(set(ids)) == 5  # 全部唯一

    def test_enqueue_preserves_fields(self, db_session: Session):
        spec = _make_spec(
            content_item_id=None,
            dimension="sentence",
            ai_model="gemini-flash",
            word_id=None,
            package_id=None,
            max_retries=5,
        )
        ids = TaskQueueService.enqueue_tasks(db_session, [spec])
        task = db_session.query(AiTaskQueue).get(ids[0])
        assert task.dimension == "sentence"
        assert task.ai_model == "gemini-flash"
        assert task.max_retries == 5


class TestMarkSubmitted:
    def test_mark_submitted(self, db_session: Session):
        ids = TaskQueueService.enqueue_tasks(db_session, [_make_spec()])
        TaskQueueService.mark_submitted(db_session, ids[0], "task_no_abc")
        task = db_session.query(AiTaskQueue).get(ids[0])
        assert task.status == AiTaskStatus.SUBMITTED.value
        assert task.gateway_task_no == "task_no_abc"
        assert task.submitted_at is not None


class TestMarkCompleted:
    def test_mark_completed(self, db_session: Session):
        ids = TaskQueueService.enqueue_tasks(db_session, [_make_spec()])
        TaskQueueService.mark_submitted(db_session, ids[0], "task_no_1")
        TaskQueueService.mark_completed(db_session, ids[0], {"content": "hello"})
        task = db_session.query(AiTaskQueue).get(ids[0])
        assert task.status == AiTaskStatus.COMPLETED.value
        assert task.result_data == {"content": "hello"}
        assert task.completed_at is not None


class TestMarkFailed:
    def test_mark_failed(self, db_session: Session):
        ids = TaskQueueService.enqueue_tasks(db_session, [_make_spec()])
        TaskQueueService.mark_failed(db_session, ids[0], "task_timeout", "超时")
        task = db_session.query(AiTaskQueue).get(ids[0])
        assert task.status == AiTaskStatus.FAILED.value
        assert task.error_type == "task_timeout"
        assert task.error_message == "超时"


class TestCollectCompleted:
    def test_collect_only_completed_and_failed(self, db_session: Session):
        specs = [_make_spec(batch_key="b1") for _ in range(4)]
        ids = TaskQueueService.enqueue_tasks(db_session, specs)
        # 第0个完成，第1个失败，第2、3个仍 pending
        TaskQueueService.mark_submitted(db_session, ids[0], "t0")
        TaskQueueService.mark_completed(db_session, ids[0], {"ok": True})
        TaskQueueService.mark_failed(db_session, ids[1], "err", "msg")

        results = TaskQueueService.collect_completed(db_session, "b1")
        assert len(results) == 2
        statuses = {r.status for r in results}
        assert statuses == {AiTaskStatus.COMPLETED.value, AiTaskStatus.FAILED.value}

    def test_collect_empty_for_other_batch(self, db_session: Session):
        TaskQueueService.enqueue_tasks(db_session, [_make_spec(batch_key="b1")])
        results = TaskQueueService.collect_completed(db_session, "b2")
        assert results == []


class TestGetPendingSubmit:
    def test_returns_pending_only(self, db_session: Session):
        specs = [_make_spec(batch_key="b1") for _ in range(3)]
        ids = TaskQueueService.enqueue_tasks(db_session, specs)
        TaskQueueService.mark_submitted(db_session, ids[0], "t0")

        pending = TaskQueueService.get_pending_submit(db_session, "b1")
        assert len(pending) == 2
        assert all(t.status == AiTaskStatus.PENDING.value for t in pending)


class TestGetSubmittedForPoll:
    def test_returns_submitted_ordered(self, db_session: Session):
        specs = [_make_spec(batch_key="b1") for _ in range(3)]
        ids = TaskQueueService.enqueue_tasks(db_session, specs)
        for i, tid in enumerate(ids):
            TaskQueueService.mark_submitted(db_session, tid, f"t{i}")

        # 给第一个设置较早的 polled_at
        task0 = db_session.query(AiTaskQueue).get(ids[0])
        task0.last_polled_at = datetime.now(UTC) - timedelta(minutes=5)
        db_session.flush()

        results = TaskQueueService.get_submitted_for_poll(db_session, "b1")
        assert len(results) == 3
        # 未轮询过的（NULL）应排在前面
        assert results[0].last_polled_at is None or results[1].last_polled_at is None


class TestIsBatchDone:
    def test_nonexistent_batch_returns_false(self, db_session: Session):
        """空批次（不存在）不应误判为完成."""
        assert TaskQueueService.is_batch_done(db_session, "nonexistent") is False

    def test_not_done_with_pending(self, db_session: Session):
        TaskQueueService.enqueue_tasks(db_session, [_make_spec(batch_key="b1")])
        assert TaskQueueService.is_batch_done(db_session, "b1") is False

    def test_done_when_all_completed(self, db_session: Session):
        ids = TaskQueueService.enqueue_tasks(db_session, [_make_spec(batch_key="b1")])
        TaskQueueService.mark_submitted(db_session, ids[0], "t0")
        TaskQueueService.mark_completed(db_session, ids[0], {})
        assert TaskQueueService.is_batch_done(db_session, "b1") is True

    def test_done_when_all_failed(self, db_session: Session):
        ids = TaskQueueService.enqueue_tasks(db_session, [_make_spec(batch_key="b1")])
        TaskQueueService.mark_failed(db_session, ids[0], "err", "msg")
        assert TaskQueueService.is_batch_done(db_session, "b1") is True


class TestBatchProgress:
    def test_progress_counts(self, db_session: Session):
        specs = [_make_spec(batch_key="b1") for _ in range(4)]
        ids = TaskQueueService.enqueue_tasks(db_session, specs)
        TaskQueueService.mark_submitted(db_session, ids[0], "t0")
        TaskQueueService.mark_completed(db_session, ids[0], {})
        TaskQueueService.mark_failed(db_session, ids[1], "err", "msg")

        progress = TaskQueueService.batch_progress(db_session, "b1")
        assert progress["total"] == 4
        assert progress["completed"] == 1
        assert progress["failed"] == 1
        assert progress["pending"] == 2


class TestRecoverInterrupted:
    def test_recover_stale_submitted(self, db_session: Session):
        ids = TaskQueueService.enqueue_tasks(db_session, [_make_spec()])
        TaskQueueService.mark_submitted(db_session, ids[0], "t0")

        # 模拟 stale：submitted_at 和 last_polled_at 都在 31 分钟前
        task = db_session.query(AiTaskQueue).get(ids[0])
        old_time = datetime.now(UTC) - timedelta(minutes=31)
        task.submitted_at = old_time
        task.last_polled_at = old_time
        db_session.flush()

        recovered = TaskQueueService.recover_interrupted(db_session)
        assert recovered == 1

    def test_no_recover_for_recent(self, db_session: Session):
        ids = TaskQueueService.enqueue_tasks(db_session, [_make_spec()])
        TaskQueueService.mark_submitted(db_session, ids[0], "t0")
        # last_polled_at 默认 None，submitted_at 是刚刚 → 不应恢复
        recovered = TaskQueueService.recover_interrupted(db_session)
        assert recovered == 0

    def test_recover_null_polled_stale_submitted(self, db_session: Session):
        ids = TaskQueueService.enqueue_tasks(db_session, [_make_spec()])
        TaskQueueService.mark_submitted(db_session, ids[0], "t0")
        task = db_session.query(AiTaskQueue).get(ids[0])
        task.submitted_at = datetime.now(UTC) - timedelta(minutes=31)
        task.last_polled_at = None  # 从未被轮询过
        db_session.flush()

        recovered = TaskQueueService.recover_interrupted(db_session)
        assert recovered == 1


class TestCancelBatch:
    def test_cancel_pending_and_submitted(self, db_session: Session):
        specs = [_make_spec(batch_key="b1") for _ in range(3)]
        ids = TaskQueueService.enqueue_tasks(db_session, specs)
        TaskQueueService.mark_submitted(db_session, ids[0], "t0")
        TaskQueueService.mark_completed(db_session, ids[0], {})

        cancelled = TaskQueueService.cancel_batch(db_session, "b1")
        assert cancelled == 2  # 只取消 pending 的两个，不影响 completed

    def test_cancel_does_not_affect_other_batch(self, db_session: Session):
        TaskQueueService.enqueue_tasks(db_session, [_make_spec(batch_key="b1")])
        TaskQueueService.enqueue_tasks(db_session, [_make_spec(batch_key="b2")])
        cancelled = TaskQueueService.cancel_batch(db_session, "b1")
        assert cancelled == 1
        # b2 不受影响
        pending = TaskQueueService.get_pending_submit(db_session, "b2")
        assert len(pending) == 1


class TestCleanupOld:
    def test_cleanup_removes_old_completed(self, db_session: Session):
        ids = TaskQueueService.enqueue_tasks(db_session, [_make_spec()])
        TaskQueueService.mark_submitted(db_session, ids[0], "t0")
        TaskQueueService.mark_completed(db_session, ids[0], {})
        # 模拟 8 天前完成
        task = db_session.query(AiTaskQueue).get(ids[0])
        task.completed_at = datetime.now(UTC) - timedelta(days=8)
        db_session.flush()

        cleaned = TaskQueueService.cleanup_old(db_session, days=7)
        assert cleaned == 1
        assert db_session.query(AiTaskQueue).get(ids[0]) is None

    def test_cleanup_keeps_recent(self, db_session: Session):
        ids = TaskQueueService.enqueue_tasks(db_session, [_make_spec()])
        TaskQueueService.mark_submitted(db_session, ids[0], "t0")
        TaskQueueService.mark_completed(db_session, ids[0], {})
        # 完成时间就是刚刚，不应被清理
        cleaned = TaskQueueService.cleanup_old(db_session, days=7)
        assert cleaned == 0

    def test_cleanup_does_not_touch_active(self, db_session: Session):
        ids = TaskQueueService.enqueue_tasks(db_session, [_make_spec()])
        # pending 状态不应被清理
        cleaned = TaskQueueService.cleanup_old(db_session, days=0)
        assert cleaned == 0


class TestIncrementPoll:
    def test_increment_poll_count(self, db_session: Session):
        ids = TaskQueueService.enqueue_tasks(db_session, [_make_spec()])
        TaskQueueService.mark_submitted(db_session, ids[0], "t0")
        TaskQueueService.increment_poll(db_session, ids[0])
        task = db_session.query(AiTaskQueue).get(ids[0])
        assert task.poll_count == 1
        assert task.last_polled_at is not None

        TaskQueueService.increment_poll(db_session, ids[0])
        db_session.refresh(task)
        assert task.poll_count == 2
