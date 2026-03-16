"""import_service 边界条件测试。"""

import json

import pytest
from vocab_qc.core.models import Meaning, Word
from vocab_qc.core.services import import_service


class TestMissingCsvColumns:
    """CSV 缺少必要列时的行为。"""

    def test_csv_missing_word_column(self, db_session):
        """缺少 word 列 — 所有行都无法识别单词，导入 0 条。"""
        csv_content = "name,pos,definition,source\nhello,interj.,你好,课本1"
        result = import_service.import_from_csv(db_session, csv_content, "no_word_col")
        assert result["word_count"] == 0

    def test_csv_missing_pos_column(self, db_session):
        """缺少 pos 列 — 单词可创建但无义项（pos 为空跳过）。"""
        csv_content = "word,definition,source\nhello,你好,课本1"
        result = import_service.import_from_csv(db_session, csv_content, "no_pos_col")
        assert result["word_count"] == 1

        word = db_session.query(Word).filter_by(word="hello").first()
        assert word is not None
        meanings = db_session.query(Meaning).filter_by(word_id=word.id).all()
        assert len(meanings) == 0

    def test_csv_missing_definition_column(self, db_session):
        """缺少 definition 列 — 单词可创建但无义项。"""
        csv_content = "word,pos,source\nhello,interj.,课本1"
        result = import_service.import_from_csv(db_session, csv_content, "no_def_col")
        assert result["word_count"] == 1

        word = db_session.query(Word).filter_by(word="hello").first()
        meanings = db_session.query(Meaning).filter_by(word_id=word.id).all()
        assert len(meanings) == 0

    def test_csv_only_word_column(self, db_session):
        """只有 word 列 — 创建单词但无义项。"""
        csv_content = "word\napple\nbanana"
        result = import_service.import_from_csv(db_session, csv_content, "word_only")
        assert result["word_count"] == 2

        words = db_session.query(Word).filter(
            Word.word.in_(["apple", "banana"])
        ).all()
        assert len(words) == 2


class TestMalformedJson:
    """JSON 解析失败时的行为。"""

    def test_invalid_json_string(self):
        """无效 JSON 字符串 — parse_upload 应抛出异常。"""
        with pytest.raises(json.JSONDecodeError):
            import_service.parse_upload(b"{not valid json", "data.json")

    def test_json_truncated(self):
        """截断的 JSON — 同样触发解析错误。"""
        with pytest.raises(json.JSONDecodeError):
            import_service.parse_upload(b'[{"word": "hello"', "data.json")

    def test_json_wrong_top_level_type(self, db_session):
        """顶层不是列表（字典） — parse_upload 应拒绝并抛出 ValueError。"""
        data_bytes = json.dumps({"word": "hello"}).encode("utf-8")
        with pytest.raises(ValueError, match="期望数组格式"):
            import_service.parse_upload(data_bytes, "data.json")


class TestEmptyFile:
    """空文件或空数据的行为。"""

    def test_empty_json_list(self, db_session):
        """空 JSON 列表 — 导入 0 条。"""
        result = import_service.import_from_json(db_session, [], "empty_json")
        assert result["word_count"] == 0

    def test_empty_csv_content(self, db_session):
        """空 CSV（只有换行或完全为空） — 导入 0 条。"""
        result = import_service.import_from_csv(db_session, "", "empty_csv")
        assert result["word_count"] == 0

    def test_csv_header_only(self, db_session):
        """只有表头没有数据行 — 导入 0 条。"""
        csv_content = "word,pos,definition,source\n"
        result = import_service.import_from_csv(db_session, csv_content, "header_only")
        assert result["word_count"] == 0

    def test_empty_json_file_upload(self):
        """空 JSON 文件上传 — 触发解析错误。"""
        with pytest.raises(json.JSONDecodeError):
            import_service.parse_upload(b"", "empty.json")

    def test_empty_csv_file_upload(self):
        """空 CSV 文件上传 — 返回空列表。"""
        result = import_service.parse_upload(b"", "empty.csv")
        assert result == []


class TestDuplicateWordsInBatch:
    """同一批次中出现重复单词。"""

    def test_same_word_appears_twice_in_json(self, db_session):
        """同一批次中同一个单词出现两次 — Word 只创建一条，义项正确合并。"""
        data = [
            {"word": "play", "meanings": [{"pos": "v.", "definition": "玩", "sources": ["来源A"]}]},
            {"word": "play", "meanings": [{"pos": "n.", "definition": "戏剧", "sources": ["来源B"]}]},
        ]
        result = import_service.import_from_json(db_session, data, "dup_in_batch")
        # word_count 计的是遍历次数（每条 entry 计一次），不是去重后的数量
        assert result["word_count"] == 2

        words = db_session.query(Word).filter_by(word="play").all()
        assert len(words) == 1

        meanings = db_session.query(Meaning).filter_by(word_id=words[0].id).all()
        assert len(meanings) == 2

    def test_same_word_same_meaning_in_batch(self, db_session):
        """同批次内同一单词完全相同的义项 — 义项去重，只保留一条。"""
        data = [
            {"word": "go", "meanings": [{"pos": "v.", "definition": "去", "sources": ["来源A"]}]},
            {"word": "go", "meanings": [{"pos": "v.", "definition": "去", "sources": ["来源B"]}]},
        ]
        import_service.import_from_json(db_session, data, "dup_meaning_batch")

        word = db_session.query(Word).filter_by(word="go").first()
        meanings = db_session.query(Meaning).filter_by(word_id=word.id, pos="v.", definition="去").all()
        assert len(meanings) == 1

    def test_duplicate_word_in_csv(self, db_session):
        """CSV 中同一单词多行 — _parse_csv_text 按 word 聚合，义项合并。"""
        csv_content = (
            "word,pos,definition,source\n"
            "book,n.,书,来源A\n"
            "book,v.,预订,来源B\n"
        )
        entries = import_service._parse_csv_text(csv_content)
        assert len(entries) == 1
        assert entries[0]["word"] == "book"
        assert len(entries[0]["meanings"]) == 2


class TestCsvWhitespace:
    """CSV 字段中的多余空白处理。"""

    def test_word_with_leading_trailing_spaces(self, db_session):
        """word 字段前后有空格 — 应被 strip。"""
        csv_content = "word,pos,definition,source\n  happy  ,adj.,快乐的,课本1"
        result = import_service.import_from_csv(db_session, csv_content, "ws_word")
        assert result["word_count"] == 1

        word = db_session.query(Word).filter_by(word="happy").first()
        assert word is not None

    def test_pos_with_spaces(self, db_session):
        """pos 字段有空格 — strip 后正常存储。"""
        csv_content = "word,pos,definition,source\nsad, adj. ,悲伤的,课本1"
        import_service.import_from_csv(db_session, csv_content, "ws_pos")

        word = db_session.query(Word).filter_by(word="sad").first()
        meaning = db_session.query(Meaning).filter_by(word_id=word.id).first()
        assert meaning.pos == "adj."

    def test_definition_with_spaces(self, db_session):
        """definition 字段有空格 — strip 后正常存储。"""
        csv_content = "word,pos,definition,source\ntall,adj., 高的 ,课本1"
        import_service.import_from_csv(db_session, csv_content, "ws_def")

        word = db_session.query(Word).filter_by(word="tall").first()
        meaning = db_session.query(Meaning).filter_by(word_id=word.id).first()
        assert meaning.definition == "高的"

    def test_all_whitespace_word_skipped(self, db_session):
        """word 字段全是空格 — strip 后为空字符串，应跳过。"""
        csv_content = "word,pos,definition,source\n   ,adj.,快乐的,课本1"
        result = import_service.import_from_csv(db_session, csv_content, "ws_empty")
        assert result["word_count"] == 0

    def test_whitespace_only_pos_skips_meaning(self, db_session):
        """pos 字段全是空格 — strip 后为空，义项被跳过。"""
        csv_content = "word,pos,definition,source\ngood,   ,好的,课本1"
        result = import_service.import_from_csv(db_session, csv_content, "ws_pos_empty")
        assert result["word_count"] == 1

        word = db_session.query(Word).filter_by(word="good").first()
        meanings = db_session.query(Meaning).filter_by(word_id=word.id).all()
        assert len(meanings) == 0
