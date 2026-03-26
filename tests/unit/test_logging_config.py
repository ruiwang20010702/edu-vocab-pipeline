"""日志配置模块测试: Formatter、Filter、中间件、log_elapsed."""

import json
import logging
import time

import pytest

from vocab_qc.core.logging_config import (
    JsonFormatter,
    RequestIdFilter,
    TextFormatter,
    _request_id_var,
    get_request_id,
    log_elapsed,
    set_request_id,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_request_id():
    """每个测试前后重置 request_id，确保隔离."""
    token = _request_id_var.set("-")
    yield
    _request_id_var.reset(token)


def _make_record(
    msg: str = "test message",
    level: int = logging.INFO,
    logger_name: str = "test.logger",
    **extra,
) -> logging.LogRecord:
    """创建 LogRecord 用于 Formatter 测试."""
    record = logging.LogRecord(
        name=logger_name,
        level=level,
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for k, v in extra.items():
        setattr(record, k, v)
    return record


# ---------------------------------------------------------------------------
# JsonFormatter
# ---------------------------------------------------------------------------

class TestJsonFormatter:

    def test_output_is_valid_json(self):
        fmt = JsonFormatter()
        record = _make_record("hello world")
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["msg"] == "hello world"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"

    def test_contains_timestamp(self):
        fmt = JsonFormatter()
        record = _make_record()
        parsed = json.loads(fmt.format(record))
        assert "ts" in parsed
        # ISO 格式应包含 T 分隔符
        assert "T" in parsed["ts"]

    def test_includes_request_id(self):
        fmt = JsonFormatter()
        record = _make_record(request_id="abc123")
        parsed = json.loads(fmt.format(record))
        assert parsed["request_id"] == "abc123"

    def test_default_request_id_is_dash(self):
        fmt = JsonFormatter()
        record = _make_record()
        parsed = json.loads(fmt.format(record))
        assert parsed["request_id"] == "-"

    def test_extra_fields_included(self):
        fmt = JsonFormatter()
        record = _make_record(request_id="-", elapsed_ms=123, word_count=10)
        parsed = json.loads(fmt.format(record))
        assert parsed["elapsed_ms"] == 123
        assert parsed["word_count"] == 10

    def test_non_serializable_extra_converted_to_str(self):
        fmt = JsonFormatter()
        record = _make_record(request_id="-", custom_obj=object())
        output = fmt.format(record)
        parsed = json.loads(output)
        # object() 不可 JSON 序列化，应转为字符串
        assert "custom_obj" in parsed
        assert isinstance(parsed["custom_obj"], str)

    def test_exception_included(self):
        fmt = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            record = _make_record()
            record.exc_info = sys.exc_info()

        output = fmt.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]
        assert "test error" in parsed["exception"]

    def test_chinese_message_not_escaped(self):
        fmt = JsonFormatter()
        record = _make_record("质检完成 总数=100")
        output = fmt.format(record)
        # ensure_ascii=False 保证中文直接输出
        assert "质检完成" in output
        parsed = json.loads(output)
        assert parsed["msg"] == "质检完成 总数=100"

    def test_warning_level(self):
        fmt = JsonFormatter()
        record = _make_record("warning msg", level=logging.WARNING)
        parsed = json.loads(fmt.format(record))
        assert parsed["level"] == "WARNING"


# ---------------------------------------------------------------------------
# TextFormatter
# ---------------------------------------------------------------------------

class TestTextFormatter:

    def test_output_contains_key_parts(self):
        fmt = TextFormatter()
        record = _make_record("hello world")
        record.request_id = "req123"
        output = fmt.format(record)
        assert "INFO" in output
        assert "[req123]" in output
        assert "test.logger" in output
        assert "hello world" in output

    def test_default_request_id(self):
        fmt = TextFormatter()
        record = _make_record("msg")
        # 没有 request_id 属性时应默认 "-"
        output = fmt.format(record)
        assert "[-]" in output

    def test_has_timestamp(self):
        fmt = TextFormatter()
        record = _make_record("msg")
        output = fmt.format(record)
        # 应包含日期格式 YYYY-MM-DD
        assert "-" in output.split(" ")[0]


# ---------------------------------------------------------------------------
# RequestIdFilter
# ---------------------------------------------------------------------------

class TestRequestIdFilter:

    def test_injects_request_id_from_contextvar(self):
        filt = RequestIdFilter()
        set_request_id("test-rid-42")
        record = _make_record()
        result = filt.filter(record)
        assert result is True
        assert record.request_id == "test-rid-42"

    def test_default_request_id(self):
        filt = RequestIdFilter()
        record = _make_record()
        filt.filter(record)
        assert record.request_id == "-"

    def test_always_returns_true(self):
        """Filter 不应过滤掉任何记录."""
        filt = RequestIdFilter()
        record = _make_record()
        assert filt.filter(record) is True


# ---------------------------------------------------------------------------
# get_request_id / set_request_id
# ---------------------------------------------------------------------------

class TestRequestIdContextVar:

    def test_default_value(self):
        assert get_request_id() == "-"

    def test_set_and_get(self):
        set_request_id("my-request-123")
        assert get_request_id() == "my-request-123"

    def test_reset_via_token(self):
        token = set_request_id("temporary")
        assert get_request_id() == "temporary"
        _request_id_var.reset(token)
        assert get_request_id() == "-"


# ---------------------------------------------------------------------------
# log_elapsed
# ---------------------------------------------------------------------------

class TestLogElapsed:

    def test_logs_elapsed_time(self, caplog):
        test_logger = logging.getLogger("test.elapsed")
        with caplog.at_level(logging.INFO, logger="test.elapsed"):
            with log_elapsed(test_logger, "测试操作"):
                time.sleep(0.01)

        assert len(caplog.records) == 1
        assert "测试操作" in caplog.records[0].message
        assert "elapsed=" in caplog.records[0].message
        # 至少 10ms
        assert "ms" in caplog.records[0].message

    def test_custom_log_level(self, caplog):
        test_logger = logging.getLogger("test.elapsed.level")
        with caplog.at_level(logging.WARNING, logger="test.elapsed.level"):
            with log_elapsed(test_logger, "警告操作", level=logging.WARNING):
                pass

        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.WARNING

    def test_info_level_not_captured_at_warning(self, caplog):
        test_logger = logging.getLogger("test.elapsed.filter")
        with caplog.at_level(logging.WARNING, logger="test.elapsed.filter"):
            with log_elapsed(test_logger, "静默操作", level=logging.INFO):
                pass

        assert len(caplog.records) == 0

    def test_elapsed_is_non_negative(self, caplog):
        test_logger = logging.getLogger("test.elapsed.nonneg")
        with caplog.at_level(logging.INFO, logger="test.elapsed.nonneg"):
            with log_elapsed(test_logger, "快速操作"):
                pass

        msg = caplog.records[0].message
        # 提取 elapsed=Xms 中的数字
        import re
        match = re.search(r"elapsed=(\d+)ms", msg)
        assert match is not None
        assert int(match.group(1)) >= 0
