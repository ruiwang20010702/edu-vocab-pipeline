"""handler 集成测试：mock 掉 ask_ai 与 reply_markdown，验证回复分支 + 问答日志。"""

import asyncio
import json

import dingtalk_stream

import ai_client
import config
import stream_client


def make_cfg(tmp_path, with_ai=True):
    return config.BotConfig(
        dingtalk_app_key="k",
        dingtalk_app_secret="s",
        ai_api_key="ak" if with_ai else "",
        ai_api_base_url="http://x" if with_ai else "",
        ai_model="gemini-3-flash-preview|efficiency",
        ai_gateway_biz_type="vocab_qc_bot",
        ai_gateway_provider="VERTEX",
        bot_log_path=str(tmp_path / "qa.log"),
    )


def make_callback(text):
    fake = {
        "msgtype": "text",
        "text": {"content": text},
        "senderNick": "测试",
        "conversationId": "c",
        "sessionWebhook": "https://x/y",
        "senderStaffId": "s",
        "robotCode": "r",
        "msgId": "m",
    }
    raw = {
        "headers": {"topic": dingtalk_stream.chatbot.ChatbotMessage.TOPIC, "messageId": "1"},
        "data": json.dumps(fake),
    }
    return dingtalk_stream.CallbackMessage.from_dict(raw)


def run_process(handler, cb):
    return asyncio.new_event_loop().run_until_complete(handler.process(cb))


def build_handler(tmp_path, with_ai=True):
    handler = stream_client.QaChatbotHandler(make_cfg(tmp_path, with_ai), "SYS_PROMPT")
    captured = {}
    handler.reply_markdown = lambda title, text, incoming: captured.update(title=title, text=text)
    return handler, captured


def test_normal_question_calls_ai_and_replies(tmp_path, monkeypatch):
    monkeypatch.setattr(stream_client, "ask_ai", lambda **kw: "这是答案")
    handler, captured = build_handler(tmp_path)
    status, _ = run_process(handler, make_callback("怎么导入词表"))
    assert status == dingtalk_stream.AckMessage.STATUS_OK
    assert captured["text"] == "这是答案"
    # 问答日志已落盘
    lines = (tmp_path / "qa.log").read_text(encoding="utf-8").strip().splitlines()
    rec = json.loads(lines[-1])
    assert rec["question"] == "怎么导入词表" and rec["ok"] is True


def test_empty_input_does_not_call_ai(tmp_path, monkeypatch):
    called = {"n": 0}

    def fake_ask(**kw):
        called["n"] += 1
        return "x"

    monkeypatch.setattr(stream_client, "ask_ai", fake_ask)
    handler, captured = build_handler(tmp_path)
    run_process(handler, make_callback("   "))
    assert called["n"] == 0
    assert captured["text"] == stream_client._EMPTY_INPUT


def test_missing_ai_config_fallback(tmp_path):
    handler, captured = build_handler(tmp_path, with_ai=False)
    run_process(handler, make_callback("怎么导入"))
    assert captured["text"] == stream_client._FALLBACK_NO_AI


def test_ai_error_fallback_and_logged(tmp_path, monkeypatch):
    def boom(**kw):
        raise ai_client.AiError("boom")

    monkeypatch.setattr(stream_client, "ask_ai", boom)
    handler, captured = build_handler(tmp_path)
    run_process(handler, make_callback("怎么导入"))
    assert captured["text"] == stream_client._FALLBACK_AI_ERROR
    rec = json.loads((tmp_path / "qa.log").read_text(encoding="utf-8").strip().splitlines()[-1])
    assert rec["ok"] is False
