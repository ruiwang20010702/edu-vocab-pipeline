"""PollingPool 和任务队列生产流程单元测试."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vocab_qc.core.models.ai_task_queue import AiTaskQueue, AiTaskStatus
from vocab_qc.core.polling_pool import PollingPool, _poll_interval_for_count
from vocab_qc.core.task_queue import TaskQueueService, TaskSpec


class TestPollIntervalForCount:
    def test_low_count(self):
        assert _poll_interval_for_count(0) == 3.0
        assert _poll_interval_for_count(4) == 3.0

    def test_medium_count(self):
        assert _poll_interval_for_count(5) == 5.0
        assert _poll_interval_for_count(19) == 5.0

    def test_high_count(self):
        assert _poll_interval_for_count(20) == 10.0
        assert _poll_interval_for_count(49) == 10.0

    def test_very_high_count(self):
        assert _poll_interval_for_count(50) == 20.0
        assert _poll_interval_for_count(100) == 20.0


class TestPollingPoolSingleton:
    def test_get_instance(self):
        PollingPool.reset_instance()
        p1 = PollingPool.get_instance()
        p2 = PollingPool.get_instance()
        assert p1 is p2
        PollingPool.reset_instance()

    def test_reset_instance(self):
        PollingPool.reset_instance()
        p1 = PollingPool.get_instance()
        PollingPool.reset_instance()
        p2 = PollingPool.get_instance()
        assert p1 is not p2
        PollingPool.reset_instance()


class TestPollingPoolWaitForBatch:
    @pytest.mark.asyncio
    async def test_wait_returns_true_when_already_done(self, db_session):
        """批次已全部完成时立即返回 True."""
        PollingPool.reset_instance()
        pool = PollingPool.get_instance()

        specs = [TaskSpec(
            batch_key="test:done",
            phase="generation",
            submit_body={"model": "m", "provider": "P", "api_key": "k", "biz_type": "t", "biz_id": "b"},
        )]
        ids = TaskQueueService.enqueue_tasks(db_session, specs)
        TaskQueueService.mark_submitted(db_session, ids[0], "t0")
        TaskQueueService.mark_completed(db_session, ids[0], {"result": "ok"})
        db_session.commit()

        with patch("vocab_qc.core.polling_pool.SyncSessionLocal", return_value=db_session):
            result = await pool.wait_for_batch("test:done", timeout=5.0)
        assert result is True
        PollingPool.reset_instance()

    @pytest.mark.asyncio
    async def test_wait_returns_false_on_timeout(self, db_session):
        """超时返回 False."""
        PollingPool.reset_instance()
        pool = PollingPool.get_instance()

        specs = [TaskSpec(
            batch_key="test:timeout",
            phase="generation",
            submit_body={"model": "m", "provider": "P", "api_key": "k", "biz_type": "t", "biz_id": "b"},
        )]
        TaskQueueService.enqueue_tasks(db_session, specs)
        db_session.commit()

        with patch("vocab_qc.core.polling_pool.SyncSessionLocal", return_value=db_session):
            result = await pool.wait_for_batch("test:timeout", timeout=0.1)
        assert result is False
        PollingPool.reset_instance()


class TestMakeSubmitBody:
    """测试生成器的 make_submit_body 方法."""

    def test_chunk_generator(self):
        from vocab_qc.core.generators.chunk import ChunkGenerator
        gen = ChunkGenerator()
        body = gen.make_submit_body(word="hello", meaning="你好", pos="interj.")
        assert "messages" in body
        assert body.get("async") is True

    def test_syllable_generator(self):
        from vocab_qc.core.generators.syllable import SyllableGenerator
        gen = SyllableGenerator()
        body = gen.make_submit_body(word="hello")
        assert "messages" in body

    def test_sentence_generator(self):
        from vocab_qc.core.generators.sentence import SentenceGenerator
        gen = SentenceGenerator()
        body = gen.make_submit_body(word="hello", meaning="你好", pos="interj.")
        assert "messages" in body
