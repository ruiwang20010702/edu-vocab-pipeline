"""钉钉问答机器人配置：从环境变量加载，启动即校验。

只读配置，独立于主项目（不 import vocab_qc）。本地开发可放 .env，
生产通过环境变量注入。AppSecret / AI key 仅存在于 env，绝不进代码或日志。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:  # 本地开发便利：有 .env 则自动加载，无则忽略
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # 生产环境直接用注入的环境变量
    pass


@dataclass(frozen=True)
class BotConfig:
    """机器人运行所需的全部配置（不可变）。"""

    dingtalk_app_key: str
    dingtalk_app_secret: str
    ai_api_key: str
    ai_api_base_url: str
    ai_model: str
    ai_gateway_biz_type: str
    ai_gateway_provider: str
    bot_log_path: str


def _require(name: str) -> str:
    """读取必需环境变量，缺失则 fail fast。"""
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少必需环境变量: {name}")
    return value


def load_config() -> BotConfig:
    """加载配置。

    任务1骨架阶段只强校验钉钉连接凭证；AI 相关凭证在接入 AI（任务4）时再校验，
    缺失时留空，以便仅凭钉钉凭证就能先把 Stream 连接跑通。
    """
    return BotConfig(
        dingtalk_app_key=_require("DINGTALK_APP_KEY"),
        dingtalk_app_secret=_require("DINGTALK_APP_SECRET"),
        ai_api_key=os.environ.get("AI_API_KEY", "").strip(),
        ai_api_base_url=os.environ.get("AI_API_BASE_URL", "").strip(),
        ai_model=os.environ.get("AI_MODEL", "gemini-3-flash-preview|efficiency").strip(),
        ai_gateway_biz_type=os.environ.get("AI_GATEWAY_BIZ_TYPE", "vocab_qc_bot").strip(),
        ai_gateway_provider=os.environ.get("AI_GATEWAY_PROVIDER", "VERTEX").strip(),
        bot_log_path=os.environ.get("BOT_LOG_PATH", "./bot_qa.log").strip(),
    )
