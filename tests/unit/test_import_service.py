"""import_service 单元测试."""

import json

import pytest

from vocab_qc.core.models import Meaning, Source, Word
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
