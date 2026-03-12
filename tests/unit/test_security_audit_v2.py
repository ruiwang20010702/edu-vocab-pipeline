"""第二轮安全审计修复的单元测试."""

import json

import pytest

from vocab_qc.core.services.import_service import _validate_magic_bytes, parse_upload


class TestMagicBytesValidation:
    """S-H2: 文件上传 magic bytes 校验。"""

    def test_valid_xlsx_magic_bytes(self):
        """合法 xlsx 文件（PK 开头）应通过。"""
        content = b"PK\x03\x04" + b"\x00" * 100
        _validate_magic_bytes(content, "test.xlsx")

    def test_invalid_xlsx_magic_bytes(self):
        """非法 xlsx 内容应被拒绝。"""
        content = b"not a zip file at all"
        with pytest.raises(ValueError, match="格式不匹配"):
            _validate_magic_bytes(content, "test.xlsx")

    def test_valid_xls_magic_bytes(self):
        """合法 xls 文件（OLE2 开头）应通过。"""
        content = b"\xd0\xcf\x11\xe0" + b"\x00" * 100
        _validate_magic_bytes(content, "data.xls")

    def test_invalid_xls_magic_bytes(self):
        """非法 xls 内容应被拒绝。"""
        content = b"PK\x03\x04" + b"\x00" * 100  # ZIP 而非 OLE2
        with pytest.raises(ValueError, match="格式不匹配"):
            _validate_magic_bytes(content, "data.xls")

    def test_json_no_magic_check(self):
        """JSON 文件不检查 magic bytes。"""
        content = b'[{"word": "hello"}]'
        _validate_magic_bytes(content, "words.json")

    def test_csv_no_magic_check(self):
        """CSV 文件不检查 magic bytes。"""
        content = b"word,pos\nhello,n."
        _validate_magic_bytes(content, "words.csv")

    def test_unsupported_format(self):
        """不支持的格式应被拒绝。"""
        with pytest.raises(ValueError, match="不支持"):
            _validate_magic_bytes(b"content", "test.pdf")

    def test_parse_upload_validates_magic_bytes(self):
        """parse_upload 应在解析前校验 magic bytes。"""
        # 伪造 xlsx 扩展名但非 ZIP 内容
        with pytest.raises(ValueError, match="格式不匹配"):
            parse_upload(b"not a zip", "evil.xlsx")

    def test_parse_upload_json_still_works(self):
        """parse_upload JSON 仍然正常工作。"""
        data = [{"word": "test", "meanings": [{"pos": "n.", "definition": "测试"}]}]
        result = parse_upload(json.dumps(data).encode(), "test.json")
        assert len(result) == 1
        assert result[0]["word"] == "test"
