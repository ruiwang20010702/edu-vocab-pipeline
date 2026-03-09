"""import_service 单元测试."""

import json

import pytest

from vocab_qc.core.models import ContentItem, Meaning, Source, Word
from vocab_qc.core.models.package_layer import Package, PackageMeaning
from vocab_qc.core.services import import_service


class TestImportFromJson:
    def test_basic_import(self, db_session):
        data = [
            {
                "word": "hello",
                "meanings": [
                    {"pos": "interj.", "definition": "你好", "sources": ["人教七上U1"]}
                ],
            }
        ]
        result = import_service.import_from_json(db_session, data, "测试批次")
        assert result["word_count"] == 1
        assert result["batch_id"]

        word = db_session.query(Word).filter_by(word="hello").first()
        assert word is not None

        meanings = db_session.query(Meaning).filter_by(word_id=word.id).all()
        assert len(meanings) == 1
        assert meanings[0].pos == "interj."

    def test_duplicate_word_reuses(self, db_session):
        data = [{"word": "apple", "meanings": [{"pos": "n.", "definition": "苹果", "sources": []}]}]
        import_service.import_from_json(db_session, data, "batch1")
        import_service.import_from_json(db_session, data, "batch2")

        words = db_session.query(Word).filter_by(word="apple").all()
        assert len(words) == 1

    def test_meaning_merge(self, db_session):
        data = [
            {
                "word": "run",
                "meanings": [
                    {"pos": "v.", "definition": "跑", "sources": ["来源A"]},
                    {"pos": "v.", "definition": "跑", "sources": ["来源B"]},
                ],
            }
        ]
        result = import_service.import_from_json(db_session, data, "merge_test")
        assert result["word_count"] == 1

        word = db_session.query(Word).filter_by(word="run").first()
        meanings = db_session.query(Meaning).filter_by(word_id=word.id, pos="v.", definition="跑").all()
        assert len(meanings) == 1

        sources = db_session.query(Source).filter_by(meaning_id=meanings[0].id).all()
        assert len(sources) == 2

    def test_package_created(self, db_session):
        data = [{"word": "test", "meanings": [{"pos": "n.", "definition": "测试", "sources": []}]}]
        result = import_service.import_from_json(db_session, data, "我的批次")

        pkg = db_session.query(Package).filter_by(name="我的批次").first()
        assert pkg is not None
        assert str(pkg.id) == result["batch_id"]

    def test_skip_empty_word(self, db_session):
        data = [{"word": "", "meanings": []}]
        result = import_service.import_from_json(db_session, data, "empty")
        assert result["word_count"] == 0

    def test_multi_word_import(self, db_session):
        data = [
            {"word": "cat", "meanings": [{"pos": "n.", "definition": "猫", "sources": []}]},
            {"word": "dog", "meanings": [{"pos": "n.", "definition": "狗", "sources": []}]},
            {"word": "fish", "meanings": [{"pos": "n.", "definition": "鱼", "sources": []}]},
        ]
        result = import_service.import_from_json(db_session, data, "animals")
        assert result["word_count"] == 3

    def test_package_status_set_after_import(self, db_session):
        """导入后 Package 的 status/total_words/processed_words 正确设置。"""
        data = [
            {"word": "sun", "meanings": [{"pos": "n.", "definition": "太阳", "sources": []}]},
            {"word": "moon", "meanings": [{"pos": "n.", "definition": "月亮", "sources": []}]},
        ]
        import_service.import_from_json(db_session, data, "pkg_status_test")

        pkg = db_session.query(Package).filter_by(name="pkg_status_test").first()
        assert pkg.status == "pending"
        assert pkg.total_words == 2
        assert pkg.processed_words == 0

    def test_content_placeholders_created_per_meaning(self, db_session):
        """每个义项应有 chunk + sentence 占位 ContentItem。"""
        data = [
            {
                "word": "light",
                "meanings": [
                    {"pos": "n.", "definition": "光", "sources": []},
                    {"pos": "adj.", "definition": "轻的", "sources": []},
                ],
            }
        ]
        import_service.import_from_json(db_session, data, "placeholder_test")

        word = db_session.query(Word).filter_by(word="light").first()
        chunks = db_session.query(ContentItem).filter_by(word_id=word.id, dimension="chunk").all()
        sentences = db_session.query(ContentItem).filter_by(word_id=word.id, dimension="sentence").all()
        assert len(chunks) == 2  # 两个义项各一条
        assert len(sentences) == 2

    def test_mnemonic_placeholder_created_per_word(self, db_session):
        """每个单词应有 1 条 mnemonic 占位 ContentItem（与义项无关）。"""
        data = [
            {
                "word": "bright",
                "meanings": [
                    {"pos": "adj.", "definition": "明亮的", "sources": []},
                    {"pos": "adj.", "definition": "聪明的", "sources": []},
                ],
            }
        ]
        import_service.import_from_json(db_session, data, "mnemonic_test")

        word = db_session.query(Word).filter_by(word="bright").first()
        mnemonics = db_session.query(ContentItem).filter_by(word_id=word.id, dimension="mnemonic").all()
        assert len(mnemonics) == 1
        assert mnemonics[0].meaning_id is None

    def test_content_placeholders_not_duplicated(self, db_session):
        """重复导入相同数据不会重复创建 ContentItem。"""
        data = [{"word": "star", "meanings": [{"pos": "n.", "definition": "星星", "sources": []}]}]
        import_service.import_from_json(db_session, data, "dup_batch1")
        import_service.import_from_json(db_session, data, "dup_batch2")

        word = db_session.query(Word).filter_by(word="star").first()
        chunks = db_session.query(ContentItem).filter_by(word_id=word.id, dimension="chunk").all()
        mnemonics = db_session.query(ContentItem).filter_by(word_id=word.id, dimension="mnemonic").all()
        assert len(chunks) == 1
        assert len(mnemonics) == 1


class TestImportFromCsv:
    def test_basic_csv(self, db_session):
        csv_content = "word,pos,definition,source\nhello,interj.,你好,课本1\nworld,n.,世界,课本2"
        result = import_service.import_from_csv(db_session, csv_content, "csv_test")
        assert result["word_count"] == 2


class TestParseUpload:
    def test_json_file(self):
        data = [{"word": "a", "meanings": []}]
        content = json.dumps(data).encode("utf-8")
        result = import_service.parse_upload(content, "test.json")
        assert len(result) == 1

    def test_csv_file(self):
        csv = "word,pos,definition,source\nhello,interj.,你好,src"
        result = import_service.parse_upload(csv.encode("utf-8"), "test.csv")
        assert len(result) == 1

    def test_unsupported_format(self):
        with pytest.raises(ValueError, match="不支持"):
            import_service.parse_upload(b"data", "test.xlsx")
