"""完整 Prompt 质检公共模块。

从 docs/prompts/quality/ 加载完整 prompt 文件，
提供文本输出格式指令和解析器，供所有维度 checker 共用。
"""

import logging
import re
from pathlib import Path
from typing import Optional

from vocab_qc.core.qc.base import RuleResult

logger = logging.getLogger(__name__)

# 维度 → 文件名映射
DIMENSION_FILE_MAP = {
    "mnemonic_root_affix": "助记-词根词缀.md",
    "mnemonic_word_in_word": "助记-词中词.md",
    "mnemonic_sound_meaning": "助记-音义联想.md",
    "mnemonic_exam_app": "助记-考试应用.md",
    "sentence": "例句.md",
    "chunk": "语块.md",
    "syllable": "音节.md",
}

# 追加在完整 prompt 末尾的输出格式指令
TEXT_OUTPUT_INSTRUCTION = """

请按以下格式输出，每个检查项一行：
检查项名称: PASS 或 FAIL — 原因（一句话）
最后一行输出: OVERALL: PASS 或 FAIL
"""

# 缓存已加载的 prompt 文件内容
_full_prompt_cache: dict[str, str] = {}


def load_full_prompt(dimension: str) -> Optional[str]:
    """从 docs/prompts/quality/ 加载完整 prompt 文件。

    Returns:
        prompt 文本，找不到文件时返回 None。
    """
    if dimension in _full_prompt_cache:
        return _full_prompt_cache[dimension]

    filename = DIMENSION_FILE_MAP.get(dimension)
    if not filename:
        return None

    # 向上查找项目根目录（pyproject.toml 所在位置）
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "pyproject.toml").exists():
            break
        current = current.parent
    else:
        return None

    path = current / "docs" / "prompts" / "quality" / filename
    if not path.exists():
        logger.warning("完整 prompt 文件不存在: %s", path)
        return None

    content = path.read_text(encoding="utf-8")
    _full_prompt_cache[dimension] = content
    return content


def parse_text_result(text: str, rule_ids: list[str]) -> list[RuleResult]:
    """解析简洁文本格式的质检输出。

    期望格式：
    Etymology Validity: PASS
    Script 6-Step Framework: FAIL — 话术缺少第4步逻辑合成
    ...
    OVERALL: PASS 或 FAIL
    """
    lines = text.strip().splitlines()
    has_fail = False
    fail_details: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 跳过 OVERALL 行（最终汇总行）
        if line.upper().startswith("OVERALL"):
            overall_match = re.search(r"(FAIL|不通过)", line, re.IGNORECASE)
            if overall_match:
                has_fail = True
            continue

        # 解析 "检查项: PASS/FAIL — 原因"
        match = re.match(
            r"^(.+?):\s*(PASS|FAIL|通过|不通过)\s*(?:—\s*(.*))?$",
            line,
            re.IGNORECASE,
        )
        if match:
            check_name = match.group(1).strip()
            status = match.group(2).upper()
            reason = match.group(3).strip() if match.group(3) else ""

            is_fail = status in ("FAIL", "不通过")
            if is_fail:
                has_fail = True
                detail = f"{check_name}: {reason}" if reason else check_name
                fail_details.append(detail)

    # 映射到 rule_id
    if not has_fail:
        return [
            RuleResult(rule_id=rid, passed=True, detail="完整 prompt 校验通过")
            for rid in rule_ids
        ]

    detail_text = "; ".join(fail_details) if fail_details else "AI 质检未通过"
    return [
        RuleResult(rule_id=rule_ids[0], passed=False, detail=detail_text),
        *(RuleResult(rule_id=rid, passed=True, detail=None) for rid in rule_ids[1:]),
    ]
