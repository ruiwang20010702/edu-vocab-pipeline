"""钉钉问答机器人入口：建立 Stream 长连接，注册机器人消息回调。

收到 @消息 → 净化输入 → 拼知识库 prompt → 调 51talk AI Gateway → markdown 回复。
失败降级、边界拒答由 system prompt + 异常兜底共同保证。见 docs/钉钉机器人MVP方案.md。

运行：
    pip install -r requirements.txt
    # 配好 .env（见 .env.example）后：
    python stream_client.py
"""

from __future__ import annotations

import logging
import time

import dingtalk_stream
from dingtalk_stream import AckMessage

from ai_client import AiError, ask_ai
from config import BotConfig, load_config
from knowledge_loader import approx_tokens, load_knowledge
from prompt import build_system_prompt, sanitize_input, wrap_user_input
from qa_log import log_qa

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("dingtalk_bot")

_REPLY_TITLE = "S9 质检小助手"
_FALLBACK_NO_AI = "机器人还没配置好 AI，暂时答不了，请联系管理员。"
_FALLBACK_AI_ERROR = "抱歉，我暂时答不上来，请稍后再试，或联系管理员。"
_EMPTY_INPUT = "请把问题用文字发给我，例如「怎么导入词表」。"


class QaChatbotHandler(dingtalk_stream.ChatbotHandler):
    """机器人消息处理器：知识库问答。"""

    def __init__(self, cfg: BotConfig, system_prompt: str, logger_: logging.Logger | None = None) -> None:
        super().__init__()
        self.cfg = cfg
        self.system_prompt = system_prompt
        if logger_ is not None:
            self.logger = logger_

    async def process(self, callback: dingtalk_stream.CallbackMessage):
        incoming = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
        raw = incoming.text.content if incoming.text else ""
        question = sanitize_input(raw)
        logger.info("收到提问 sender=%s text=%r", incoming.sender_nick, question)

        if not question:
            self.reply_markdown(_REPLY_TITLE, _EMPTY_INPUT, incoming)
            return AckMessage.STATUS_OK, "OK"

        if not self.cfg.ai_api_key or not self.cfg.ai_api_base_url:
            self.reply_markdown(_REPLY_TITLE, _FALLBACK_NO_AI, incoming)
            return AckMessage.STATUS_OK, "OK"

        started = time.monotonic()
        ok = True
        try:
            answer = ask_ai(
                base_url=self.cfg.ai_api_base_url,
                api_key=self.cfg.ai_api_key,
                model=self.cfg.ai_model,
                biz_type=self.cfg.ai_gateway_biz_type,
                system_prompt=self.system_prompt,
                user_prompt=wrap_user_input(question),
                provider_fallback=self.cfg.ai_gateway_provider,
            )
        except AiError as exc:
            logger.error("AI 调用失败 sender=%s: %s", incoming.sender_nick, exc)
            answer = _FALLBACK_AI_ERROR
            ok = False

        latency_ms = int((time.monotonic() - started) * 1000)
        self.reply_markdown(_REPLY_TITLE, answer, incoming)
        log_qa(
            self.cfg.bot_log_path,
            sender=incoming.sender_nick or "",
            question=question,
            answer=answer,
            latency_ms=latency_ms,
            ok=ok,
        )
        return AckMessage.STATUS_OK, "OK"


def build_client(cfg: BotConfig) -> dingtalk_stream.DingTalkStreamClient:
    """根据配置构造并注册好回调的 Stream client（启动时加载知识库）。"""
    knowledge = load_knowledge()
    system_prompt = build_system_prompt(knowledge)
    logger.info("知识库加载完成：约 %d tokens", approx_tokens(knowledge))

    credential = dingtalk_stream.Credential(cfg.dingtalk_app_key, cfg.dingtalk_app_secret)
    client = dingtalk_stream.DingTalkStreamClient(credential)
    client.register_callback_handler(
        dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
        QaChatbotHandler(cfg, system_prompt, logger),
    )
    return client


def main() -> None:
    cfg = load_config()
    client = build_client(cfg)
    logger.info("钉钉 Stream client 启动，等待消息…")
    client.start_forever()


if __name__ == "__main__":
    main()
