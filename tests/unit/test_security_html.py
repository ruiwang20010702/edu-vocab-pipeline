"""XSS 过滤统一函数 reject_html_input 测试."""

import pytest
from fastapi import HTTPException

from vocab_qc.core.security import reject_html_input


class TestRejectHtmlInput:
    """reject_html_input 应拒绝各类 XSS 载荷。"""

    def test_none_and_empty_pass(self):
        reject_html_input(None)
        reject_html_input("")

    def test_normal_text_pass(self):
        reject_html_input("hello world")
        reject_html_input("apple 苹果 n.")
        reject_html_input("I have 3 < 5 apples")  # 单独 < 不是标签

    def test_simple_tag_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            reject_html_input("<script>alert(1)</script>")
        assert exc_info.value.status_code == 400

    def test_unclosed_tag_rejected(self):
        with pytest.raises(HTTPException):
            reject_html_input("<img src=x onerror=alert(1)")

    def test_multiline_tag_rejected(self):
        """re.DOTALL 覆盖换行绕过。"""
        with pytest.raises(HTTPException):
            reject_html_input("<img\nsrc=x\nonerror=alert(1)>")

    def test_event_handler_rejected(self):
        with pytest.raises(HTTPException):
            reject_html_input('content" onfocus=alert(1) autofocus="')

    def test_html_entity_rejected(self):
        with pytest.raises(HTTPException):
            reject_html_input("&#60;script&#62;")

    def test_named_entity_rejected(self):
        with pytest.raises(HTTPException):
            reject_html_input("&lt;script&gt;")

    def test_javascript_uri_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            reject_html_input("javascript:alert(1)")
        assert "危险 URI" in exc_info.value.detail

    def test_data_uri_rejected(self):
        with pytest.raises(HTTPException):
            reject_html_input("data:text/html,<script>alert(1)</script>")

    def test_field_name_in_error(self):
        with pytest.raises(HTTPException) as exc_info:
            reject_html_input("<b>bold</b>", "content_cn")
        assert "content_cn" in exc_info.value.detail

    def test_svg_tag_rejected(self):
        with pytest.raises(HTTPException):
            reject_html_input("<svg onload=alert(1)>")

    def test_iframe_rejected(self):
        with pytest.raises(HTTPException):
            reject_html_input('<iframe src="evil.com"></iframe>')
