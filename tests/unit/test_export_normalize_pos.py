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

    # art. / art 都映射为 det
    @pytest.mark.parametrize("raw", ["art.", "art"])
    def test_art_maps_to_det(self, raw):
        assert _normalize_pos_for_export(raw) == "det"

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
