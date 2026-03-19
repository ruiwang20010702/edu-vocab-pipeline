"""模型配置与 prompt 加载。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── 路径 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_XLSX = PROJECT_ROOT / "docs" / "design" / "质检黄金案例表2.xlsx"
PROMPT_DIR = PROJECT_ROOT / "docs" / "prompts" / "quality"
RESULTS_DIR = Path(__file__).parent / "results"

# ── 维度 → prompt 文件 映射 ─────────────────────────────
DIMENSION_PROMPT_FILES: dict[str, str] = {
    "sentence": "例句.md",
    "chunk": "语块.md",
    "syllable": "音节.md",
    "mnemonic_root_affix": "助记-词根词缀.md",
    "mnemonic_word_in_word": "助记-词中词.md",
    "mnemonic_sound_meaning": "助记-音义联想.md",
    "mnemonic_exam_app": "助记-考试应用.md",
}

# ── 维度 → xlsx sheet 名 映射 ────────────────────────────
DIMENSION_SHEET_NAMES: dict[str, str] = {
    "sentence": "例句（done)",
    "chunk": "语块done",
    "syllable": "音节done",
    "mnemonic_root_affix": "助记-词根词缀（done）",
    "mnemonic_word_in_word": "助记-词中词（done）",
    "mnemonic_sound_meaning": "助记-音义联想（done）",
    "mnemonic_exam_app": "助记-考试应用（done）",
}


@dataclass(frozen=True)
class ModelConfig:
    name: str       # 显示名 (GPT-5.2 / Gemini / 豆包)
    api_key: str
    base_url: str
    model: str      # API model name
    gateway: bool = False  # True = 51talk AI Gateway 异步模式


def load_models() -> list[ModelConfig]:
    """从环境变量加载可用模型配置，跳过未配置 key 的模型。"""
    candidates = [
        ModelConfig(
            name="GPT-5.2",
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("OPENAI_MODEL", "gpt-5.2"),
        ),
        ModelConfig(
            name="Gemini",
            api_key=os.getenv("GEMINI_API_KEY", ""),
            base_url=os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
            model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
        ),
        ModelConfig(
            name="豆包",
            api_key=os.getenv("DOUBAO_API_KEY", ""),
            base_url=os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
            model=os.getenv("DOUBAO_MODEL", "doubao-seed-1.8-251228"),
        ),
    ]
    models = [m for m in candidates if m.api_key]
    if not models:
        raise RuntimeError("No API keys configured in .env")
    return models


def load_prompt(dimension: str) -> str:
    """加载指定维度的 QC prompt 文件内容。"""
    filename = DIMENSION_PROMPT_FILES[dimension]
    path = PROMPT_DIR / filename
    return path.read_text(encoding="utf-8").strip()
