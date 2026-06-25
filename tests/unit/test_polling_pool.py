"""PollingPool 和任务队列生产流程单元测试."""

from unittest.mock import patch

import pytest
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


class TestL2CheckerBuildPrompts:
    """测试 L2 UnifiedChecker 的 build_prompts 和 parse_ai_response."""

    def test_chunk_build_prompts(self):
        from vocab_qc.core.qc.layer2.unified.chunk_unified import UnifiedChunkChecker
        checker = UnifiedChunkChecker()
        sys_p, usr_p, use_json = checker.build_prompts("take a walk", "walk", "散步", pos="n.")
        assert len(sys_p) > 0
        assert "walk" in usr_p
        assert isinstance(use_json, bool)

    def test_chunk_parse_json_response(self):
        from vocab_qc.core.qc.layer2.unified.chunk_unified import UnifiedChunkChecker
        checker = UnifiedChunkChecker()
        response = {"results": [{"rule_id": "C3", "passed": True, "detail": "ok"}]}
        results = checker.parse_ai_response(response, use_json_format=True)
        assert len(results) == 1
        assert results[0].passed is True

    def test_chunk_parse_text_response(self):
        from vocab_qc.core.qc.layer2.unified.chunk_unified import UnifiedChunkChecker
        checker = UnifiedChunkChecker()
        response = {"raw_text": "Collocation Check: PASS\nOVERALL: PASS"}
        results = checker.parse_ai_response(response, use_json_format=False)
        assert len(results) == 1
        assert results[0].passed is True

    def test_sentence_build_prompts(self):
        from vocab_qc.core.qc.layer2.unified.sentence_unified import UnifiedSentenceChecker
        checker = UnifiedSentenceChecker()
        sys_p, usr_p, use_json = checker.build_prompts(
            "He is kind.", "kind", "友好的", pos="adj.", content_cn="他很友好。",
        )
        assert "kind" in usr_p
        assert isinstance(use_json, bool)

    def test_syllable_build_prompts(self):
        from vocab_qc.core.qc.layer2.unified.syllable_unified import UnifiedSyllableChecker
        checker = UnifiedSyllableChecker()
        sys_p, usr_p, use_json = checker.build_prompts("hap·py", "happy")
        assert "happy" in usr_p

    def test_mnemonic_build_prompts(self):
        from vocab_qc.core.qc.layer2.unified.mnemonic_unified import UnifiedMnemonicChecker
        checker = UnifiedMnemonicChecker()
        sys_p, usr_p, use_json = checker.build_prompts(
            "kind = k + ind", "kind", "友好的",
            item_dimension="mnemonic_word_in_word",
        )
        assert "kind" in usr_p

    def test_mnemonic_parse_json_response(self):
        from vocab_qc.core.qc.layer2.unified.mnemonic_unified import UnifiedMnemonicChecker
        checker = UnifiedMnemonicChecker()
        response = {"results": [
            {"rule_id": "N5_AI", "passed": True, "detail": "ok"},
            {"rule_id": "N6", "passed": False, "detail": "伪助记"},
        ]}
        results = checker.parse_ai_response(response, use_json_format=True)
        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False

    def test_ai_client_make_submit_body(self):
        from vocab_qc.core.qc.layer2.ai_base import AiClient
        client = AiClient(api_key="test", base_url="http://test", model="test-model")
        body = client.make_submit_body("system", "user")
        assert "messages" in body
        assert body.get("temperature") == 0  # 质检用 temperature=0
