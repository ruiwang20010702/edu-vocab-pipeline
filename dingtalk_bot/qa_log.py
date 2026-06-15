"""问答日志：每条问答追加一行 JSONL，供沉淀 FAQ / 发现知识盲区。

故意与运行日志分开（结构化、可后续分析）。写入失败只告警不影响回复。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

logger = logging.getLogger("dingtalk_bot")

_MAX_ANSWER_LEN = 500


def log_qa(path: str, *, sender: str, question: str, answer: str, latency_ms: int, ok: bool) -> None:
    """追加一条问答记录（JSONL）。answer 截断到 500 字。"""
    record = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sender": sender,
        "question": question,
        "answer": answer[:_MAX_ANSWER_LEN],
        "latency_ms": latency_ms,
        "ok": ok,
    }
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:  # 日志写不进去不能影响给用户回复
        logger.warning("问答日志写入失败 path=%s: %s", path, exc)
