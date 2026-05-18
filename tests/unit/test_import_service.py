"""import_service 单元测试."""

import json

import pytest
from vocab_qc.core.models import ContentItem, Meaning, Source, Word
from vocab_qc.core.models.package_layer import Package
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

    def test_mnemonic_placeholder_created_per_meaning(self, db_session):
        """每个义项应有 4 条 mnemonic 占位 ContentItem。"""
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
        from vocab_qc.core.models.enums import MNEMONIC_DIMENSIONS

        mnemonics = db_session.query(ContentItem).filter(
            ContentItem.word_id == word.id,
            ContentItem.dimension.in_(MNEMONIC_DIMENSIONS),
        ).all()
        # bright 有 2 个义项 × 4 种助记类型 = 8 条
        assert len(mnemonics) == 8
        assert all(m.meaning_id is not None for m in mnemonics)

    def test_content_placeholders_not_duplicated(self, db_session):
        """重复导入相同数据不会重复创建 ContentItem。"""
        from vocab_qc.core.models.enums import MNEMONIC_DIMENSIONS

        data = [{"word": "star", "meanings": [{"pos": "n.", "definition": "星星", "sources": []}]}]
        import_service.import_from_json(db_session, data, "dup_batch1")
        import_service.import_from_json(db_session, data, "dup_batch2")

        word = db_session.query(Word).filter_by(word="star").first()
        chunks = db_session.query(ContentItem).filter_by(word_id=word.id, dimension="chunk").all()
        mnemonics = db_session.query(ContentItem).filter(
            ContentItem.word_id == word.id,
            ContentItem.dimension.in_(MNEMONIC_DIMENSIONS),
        ).all()
        assert len(chunks) == 1
        assert len(mnemonics) == 4


class TestImportFromCsv:
    def test_basic_csv(self, db_session):
        csv_content = "word,pos,definition,source\nhello,interj.,你好,课本1\nworld,n.,世界,课本2"
        result = import_service.import_from_csv(db_session, csv_content, "csv_test")
        assert result["word_count"] == 2


class TestParseUpload:
    def test_json_file(self):
        data = [{"word": "a", "meanings": []}]
        content = json.dumps(data).encode("utf-8")
        result, _ = import_service.parse_upload(content, "test.json")
        assert len(result) == 1

    def test_csv_file(self):
        csv = "word,pos,definition,source\nhello,interj.,你好,src"
        result, _ = import_service.parse_upload(csv.encode("utf-8"), "test.csv")
        assert len(result) == 1

    def test_unsupported_format(self):
        with pytest.raises(ValueError, match="不支持"):
            import_service.parse_upload(b"data", "test.txt")


class TestNormalizePos:
    """词性规范化：内部统一为带点裸标签格式。"""

    @pytest.mark.parametrize("inp,expected", [
        ("n", "n."),
        ("N", "n."),
        ("n.", "n."),
        ("n..", "n."),
        ("adj", "adj."),
        ("ADJ", "adj."),
        ("adj.", "adj."),
        ("phr", "phr."),
        ("modal v.", "modal v."),
        ("n., vi.", "n., vi."),
        # 复合词性无点输入也要归一到带点形式，否则与 DB 已有的 'n., vi.' 不会去重
        ("n, vi", "n., vi."),
        ("N,VI", "n., vi."),
        ("vi, vt", "vi., vt."),
        (" v ", "v."),
        ("", ""),
    ])
    def test_normalize_pos(self, inp, expected):
        assert import_service._normalize_pos(inp) == expected


class TestNormalizeDefinition:
    """释义规范化：半角中文标点转全角，折叠空白。"""

    @pytest.mark.parametrize("inp,expected", [
        ("焰火;烟花", "焰火；烟花"),
        ("焰火；烟花", "焰火；烟花"),
        ("开心的,满意的", "开心的，满意的"),
        ("优美，优雅", "优美，优雅"),
        ("(数字)零", "（数字）零"),
        ("好!坏?", "好！坏？"),
        ("  前后空白 ", "前后空白"),
        ("多\n\t空白", "多 空白"),
        ("", ""),
    ])
    def test_normalize_definition(self, inp, expected):
        assert import_service._normalize_definition(inp) == expected


class TestDedupAcrossStyles:
    """跨风格去重：模拟历史/新版两种格式同义项的合并行为。"""

    def test_old_style_then_new_style_creates_one_meaning(self, db_session):
        """先导入老风格 (n. + 全角分号)，再导入新风格 (n + 半角分号)，应只产生 1 条 Meaning。"""
        old_style = [{"word": "firework", "meanings": [
            {"pos": "n.", "definition": "焰火；烟花", "sources": ["旧批次"]},
        ]}]
        new_style = [{"word": "firework", "meanings": [
            {"pos": "n", "definition": "焰火;烟花", "sources": ["新批次"]},
        ]}]

        import_service.import_from_json(db_session, old_style, "batch_old")
        import_service.import_from_json(db_session, new_style, "batch_new")

        word = db_session.query(Word).filter_by(word="firework").first()
        meanings = db_session.query(Meaning).filter_by(word_id=word.id).all()
        assert len(meanings) == 1
        assert meanings[0].pos == "n."
        assert meanings[0].definition == "焰火；烟花"

        # 两个批次的 source 都应挂在同一 meaning 上
        sources = db_session.query(Source).filter_by(meaning_id=meanings[0].id).all()
        source_names = sorted(s.source_name for s in sources)
        assert source_names == ["新批次", "旧批次"]

    def test_reverse_order_also_dedupes(self, db_session):
        """反向顺序：先新风格再老风格，结果同样应只有 1 条 Meaning。"""
        new_style = [{"word": "tent", "meanings": [
            {"pos": "n", "definition": "帐篷", "sources": ["a"]},
        ]}]
        old_style = [{"word": "tent", "meanings": [
            {"pos": "n.", "definition": "帐篷", "sources": ["b"]},
        ]}]

        import_service.import_from_json(db_session, new_style, "b1")
        import_service.import_from_json(db_session, old_style, "b2")

        word = db_session.query(Word).filter_by(word="tent").first()
        meanings = db_session.query(Meaning).filter_by(word_id=word.id).all()
        assert len(meanings) == 1
        assert meanings[0].pos == "n."  # 规范化为带点格式

    def test_csv_normalization_applied(self, db_session):
        """CSV 路径同样应触发规范化。"""
        csv_content = "word,pos,definition,source\ncarnival,n,狂欢节;嘉年华会,csv_src"
        import_service.import_from_csv(db_session, csv_content, "csv_norm")

        word = db_session.query(Word).filter_by(word="carnival").first()
        meanings = db_session.query(Meaning).filter_by(word_id=word.id).all()
        assert len(meanings) == 1
        assert meanings[0].pos == "n."
        assert meanings[0].definition == "狂欢节；嘉年华会"
