"""导出层 POS 规范化函数 _normalize_pos_for_export 单元测试。"""

import pytest
from vocab_qc.core.services.export_service import _normalize_pos_for_export


class TestNormalizePosForExport:
    # 旧带点格式去点
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("n.", "n"),
            ("v.", "v"),
            ("adj.", "adj"),
            ("adv.", "adv"),
            ("prep.", "prep"),
            ("conj.", "conj"),
            ("pron.", "pron"),
            ("num.", "num"),
            ("int.", "int"),
        ],
    )
    def test_strip_trailing_dot(self, raw, expected):
        assert _normalize_pos_for_export(raw) == expected

    # art. / art 忠于原值（不再映射到 det）。
    # 2026-05-26 权威清单 art. 与 det. 并存，删除历史 art→det 映射。
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("art.", "art"), ("art", "art"), ("det.", "det"), ("det", "det")],
    )
    def test_art_and_det_both_preserved(self, raw, expected):
        assert _normalize_pos_for_export(raw) == expected

    # 已规范化的新格式保持不变
    @pytest.mark.parametrize(
        "pos",
        [
            "n", "v", "adj", "adv", "prep", "pron", "num",
            "mod", "aux", "conj", "int", "abbr", "det",
            "phr", "n phr", "a phr",
        ],
    )
    def test_already_normalized_passthrough(self, pos):
        assert _normalize_pos_for_export(pos) == pos

    # 防御：空/None
    @pytest.mark.parametrize("raw", ["", None])
    def test_empty_returns_empty_string(self, raw):
        assert _normalize_pos_for_export(raw) == ""

    # 多余的尾部点会被全部剥掉（rstrip 行为）
    def test_multiple_trailing_dots_stripped(self):
        assert _normalize_pos_for_export("n..") == "n"
