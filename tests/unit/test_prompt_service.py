"""Prompt 服务单元测试."""

from vocab_qc.core.models.prompt import Prompt
from vocab_qc.core.services import prompt_service


class TestPromptService:
    def test_seed_defaults(self, db_session):
        """种子数据应成功插入."""
        count = prompt_service.seed_defaults(db_session)
        assert count == 8
        prompts = prompt_service.list_prompts(db_session)
        assert len(prompts) == 8

    def test_seed_idempotent(self, db_session):
        """重复调用 seed 不应创建重复数据."""
        prompt_service.seed_defaults(db_session)
        count = prompt_service.seed_defaults(db_session)
        assert count == 0

    def test_create_prompt(self, db_session):
        prompt = prompt_service.create_prompt(db_session, {
            "name": "测试 Prompt",
            "category": "generation",
            "dimension": "chunk",
            "content": "这是测试内容",
        })
        assert prompt.id is not None
        assert prompt.name == "测试 Prompt"
        assert prompt.dimension == "chunk"

    def test_update_prompt(self, db_session):
        prompt = prompt_service.create_prompt(db_session, {
            "name": "原始名",
            "category": "qa",
            "dimension": "sentence",
        })
        updated = prompt_service.update_prompt(db_session, prompt.id, {"name": "新名称"})
        assert updated is not None
        assert updated.name == "新名称"

    def test_delete_prompt(self, db_session):
        prompt = prompt_service.create_prompt(db_session, {
            "name": "待删除",
            "category": "generation",
            "dimension": "mnemonic",
        })
        assert prompt_service.delete_prompt(db_session, prompt.id) is True
        assert prompt_service.get_prompt(db_session, prompt.id) is None

    def test_list_by_category(self, db_session):
        prompt_service.create_prompt(db_session, {"name": "A", "category": "generation", "dimension": "chunk"})
        prompt_service.create_prompt(db_session, {"name": "B", "category": "qa", "dimension": "sentence"})
        gen_prompts = prompt_service.list_prompts(db_session, category="generation")
        assert len(gen_prompts) == 1
        assert gen_prompts[0].name == "A"

    def test_get_active_prompt(self, db_session):
        prompt_service.create_prompt(db_session, {
            "name": "活跃 Prompt",
            "category": "generation",
            "dimension": "chunk",
            "content": "active content",
        })
        active = prompt_service.get_active_prompt(db_session, "generation", "chunk")
        assert active is not None
        assert active.content == "active content"

    def test_update_nonexistent(self, db_session):
        result = prompt_service.update_prompt(db_session, 99999, {"name": "x"})
        assert result is None

    def test_delete_nonexistent(self, db_session):
        assert prompt_service.delete_prompt(db_session, 99999) is False
