"""GenerationService 单元测试."""

import pytest
from vocab_qc.core.models import AuditLogV2, ContentItem, Meaning, Word
from vocab_qc.core.services.generation_service import GenerationService


@pytest.fixture
def service():
    return GenerationService()


@pytest.fixture
def content_item(db_session):
    """创建一个基础 ContentItem."""
    word = Word(word="happy")
    db_session.add(word)
    db_session.flush()

    meaning = Meaning(word_id=word.id, pos="adj.", definition="快乐的")
    db_session.add(meaning)
    db_session.flush()

    item = ContentItem(
        word_id=word.id,
        meaning_id=meaning.id,
        dimension="chunk",
        content="be happy",
    )
    db_session.add(item)
    db_session.flush()
    return item


class TestRegenerateDimension:
    def test_updates_content(self, db_session, service, content_item):
        """重新生成后 content 更新为新值."""
        updated = service.regenerate_dimension(db_session, content_item, "feel happy")
        assert updated.content == "feel happy"

    def test_returns_same_item(self, db_session, service, content_item):
        """返回的对象是同一个 ContentItem 实例."""
        result = service.regenerate_dimension(db_session, content_item, "new content")
        assert result is content_item

    def test_updates_content_cn_when_provided(self, db_session, service, content_item):
        """传入 new_content_cn 时同步更新中文内容."""
        service.regenerate_dimension(db_session, content_item, "feel happy", new_content_cn="感到快乐")
        assert content_item.content_cn == "感到快乐"

    def test_content_cn_unchanged_when_not_provided(self, db_session, service, content_item):
        """不传 new_content_cn 时中文内容保持不变."""
        content_item.content_cn = "已有中文"
        service.regenerate_dimension(db_session, content_item, "new content")
        assert content_item.content_cn == "已有中文"

    def test_content_cn_none_does_not_override(self, db_session, service, content_item):
        """new_content_cn 默认为 None，不覆盖已有 content_cn."""
        content_item.content_cn = "保留这段"
        service.regenerate_dimension(db_session, content_item, "something", new_content_cn=None)
        assert content_item.content_cn == "保留这段"

    def test_writes_audit_log(self, db_session, service, content_item):
        """调用后写入 AuditLogV2 审计记录."""
        service.regenerate_dimension(db_session, content_item, "audited content")
        log = db_session.query(AuditLogV2).filter_by(entity_type="content_item").first()
        assert log is not None
        assert log.action == "regenerate"

    def test_audit_log_records_old_value(self, db_session, service, content_item):
        """审计日志的 old_value 包含原始内容."""
        original = content_item.content
        service.regenerate_dimension(db_session, content_item, "new value")
        log = db_session.query(AuditLogV2).filter_by(entity_type="content_item").first()
        assert log.old_value == {"content": original}

    def test_audit_log_records_new_value(self, db_session, service, content_item):
        """审计日志的 new_value 包含新内容."""
        service.regenerate_dimension(db_session, content_item, "new value")
        log = db_session.query(AuditLogV2).filter_by(entity_type="content_item").first()
        assert log.new_value == {"content": "new value"}

    def test_audit_log_actor_default_system(self, db_session, service, content_item):
        """默认 actor 为 'system'."""
        service.regenerate_dimension(db_session, content_item, "x")
        log = db_session.query(AuditLogV2).filter_by(entity_type="content_item").first()
        assert log.actor == "system"

    def test_audit_log_actor_custom(self, db_session, service, content_item):
        """可指定自定义 actor."""
        service.regenerate_dimension(db_session, content_item, "x", actor="reviewer_01")
        log = db_session.query(AuditLogV2).filter_by(entity_type="content_item").first()
        assert log.actor == "reviewer_01"

    def test_empty_string_content(self, db_session, service, content_item):
        """可将内容重置为空字符串."""
        updated = service.regenerate_dimension(db_session, content_item, "")
        assert updated.content == ""

    def test_multiple_calls_create_multiple_audit_logs(self, db_session, service, content_item):
        """多次调用写入多条审计日志."""
        service.regenerate_dimension(db_session, content_item, "first")
        service.regenerate_dimension(db_session, content_item, "second")
        logs = db_session.query(AuditLogV2).filter_by(entity_type="content_item").all()
        assert len(logs) == 2
