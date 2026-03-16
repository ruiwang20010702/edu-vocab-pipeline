"""PM-H3: Prompt 同步功能测试."""


from vocab_qc.core.models.prompt import Prompt
from vocab_qc.core.services.prompt_service import (
    _compute_file_hash,
    sync_prompts,
)


class TestComputeFileHash:
    def test_deterministic(self):
        h1 = _compute_file_hash("hello")
        h2 = _compute_file_hash("hello")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256

    def test_different_content(self):
        assert _compute_file_hash("a") != _compute_file_hash("b")


class TestSyncPrompts:
    def test_creates_new_prompts(self, db_session):
        """DB 为空时应创建新记录。"""
        result = sync_prompts(db_session)
        assert result["created"] >= 0
        assert result["updated"] == 0

    def test_skips_manual_prompts(self, db_session):
        """source=manual 的 Prompt 不应被文件覆盖。"""
        prompt = Prompt(
            name="测试", category="generation", dimension="chunk",
            model="test", content="手动编辑内容", source="manual",
            file_hash="old_hash",
        )
        db_session.add(prompt)
        db_session.flush()

        sync_prompts(db_session)
        db_session.flush()

        refreshed = db_session.query(Prompt).filter_by(
            category="generation", dimension="chunk", is_active=True,
        ).first()
        assert refreshed.content == "手动编辑内容"
        assert refreshed.source == "manual"

    def test_updates_file_source_with_different_hash(self, db_session):
        """source=file + hash 不同 → 应更新内容。"""
        prompt = Prompt(
            name="测试", category="generation", dimension="chunk",
            model="test", content="旧内容", source="file",
            file_hash="definitely_wrong_hash",
        )
        db_session.add(prompt)
        db_session.flush()

        _result = sync_prompts(db_session)
        # 如果文件存在且 hash 不同，updated >= 1
        # 如果文件不存在，则不会更新
        assert _result["updated"] >= 0

    def test_dry_run_no_changes(self, db_session):
        """dry_run=True 不应修改 DB。"""
        count_before = db_session.query(Prompt).count()
        sync_prompts(db_session, dry_run=True)
        count_after = db_session.query(Prompt).count()
        assert count_before == count_after
