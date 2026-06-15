"""纯函数单测：prompt 净化、知识库加载、ai_client 解析与 provider 推断。"""

import pytest

import ai_client
import knowledge_loader
import prompt


# ---------- prompt.sanitize_input ----------
def test_sanitize_strips_and_collapses():
    assert prompt.sanitize_input("  你好  ") == "你好"


def test_sanitize_removes_control_chars():
    assert prompt.sanitize_input("a\x00b\x07c") == "abc"


def test_sanitize_truncates_long_input():
    assert len(prompt.sanitize_input("字" * 5000)) == 1000


def test_sanitize_none_safe():
    assert prompt.sanitize_input(None) == ""


def test_wrap_user_input_has_tags():
    wrapped = prompt.wrap_user_input("怎么导入")
    assert wrapped.startswith("<user_input>") and wrapped.endswith("</user_input>")
    assert "怎么导入" in wrapped


def test_build_system_prompt_embeds_knowledge():
    sp = prompt.build_system_prompt("【KB内容XYZ】")
    assert "【KB内容XYZ】" in sp
    assert "S9 单词内容生产质检小助手" in sp


# ---------- knowledge_loader ----------
def test_load_knowledge_reads_md(tmp_path):
    (tmp_path / "a.md").write_text("AAA", encoding="utf-8")
    (tmp_path / "b.md").write_text("BBB", encoding="utf-8")
    kb = knowledge_loader.load_knowledge(tmp_path)
    assert "AAA" in kb and "BBB" in kb
    assert "a.md" in kb  # 文件名作为分块标题


def test_load_knowledge_empty_dir_raises(tmp_path):
    with pytest.raises(RuntimeError):
        knowledge_loader.load_knowledge(tmp_path)


def test_approx_tokens_positive():
    assert knowledge_loader.approx_tokens("abcdef") > 0


# ---------- ai_client.resolve_provider ----------
@pytest.mark.parametrize(
    "model,expected",
    [
        ("gemini-3-flash-preview|efficiency", "VERTEX"),
        ("gpt-5.2|efficiency", "AZURE"),
        ("some-other-model", "FALLBACK"),
    ],
)
def test_resolve_provider(model, expected):
    assert ai_client.resolve_provider(model, "FALLBACK") == expected


# ---------- ai_client.parse_response ----------
def test_parse_response_plain_choices():
    data = {"choices": [{"message": {"content": "答案"}}]}
    assert ai_client.parse_response(data) == "答案"


def test_parse_response_res_wrapped():
    data = {"res": {"choices": [{"message": {"content": "包裹答案"}}]}}
    assert ai_client.parse_response(data) == "包裹答案"


def test_parse_response_res_null_raises():
    with pytest.raises(ai_client.AiError):
        ai_client.parse_response({"res": None, "code": "ERR"})


def test_parse_response_no_choices_raises():
    with pytest.raises(ai_client.AiError):
        ai_client.parse_response({"foo": "bar"})
