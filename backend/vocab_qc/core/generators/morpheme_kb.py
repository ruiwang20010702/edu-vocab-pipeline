"""词根词缀知识库：加载 CSV、解析词素、格式化为 prompt 文本."""

import csv
import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from vocab_qc.core.generators import _find_project_root

logger = logging.getLogger(__name__)

_PROJECT_ROOT = _find_project_root()
_DATA_DIR = _PROJECT_ROOT / "docs" / "data"


@dataclass(frozen=True)
class MorphemeEntry:
    """一条词素记录（不可变）."""

    category: str  # "root" | "prefix" | "suffix"
    forms: tuple[str, ...]  # 所有变体形式（小写）
    display: str  # 原始显示名
    description: str  # 来源说明


def _parse_root_forms(raw: str) -> tuple[str, ...]:
    """解析词根: 'DUC, DUCT[DU]' → ('duc', 'duct', 'du')——主形式在前，变体在后."""
    forms: list[str] = []
    # 先提取方括号变体（暂存）
    bracket_variants: list[str] = []
    bracket_matches = re.findall(r"\[([^\]]+)\]", raw)
    for bm in bracket_matches:
        for part in bm.split(","):
            part = part.strip().lower()
            if part:
                bracket_variants.append(part)
    # 去掉方括号部分，主形式先加入
    cleaned = re.sub(r"\[[^\]]*\]", "", raw)
    for part in cleaned.split(","):
        part = part.strip().lower()
        if part:
            forms.append(part)
    # 变体追加在后
    forms.extend(bracket_variants)
    return tuple(dict.fromkeys(forms))


def _parse_prefix_forms(raw: str) -> tuple[str, ...]:
    """解析前缀: 'AB (ABS, A)' → ('ab', 'abs', 'a')."""
    forms: list[str] = []
    # 提取圆括号内的变体
    paren_match = re.search(r"\(([^)]+)\)", raw)
    if paren_match:
        for part in paren_match.group(1).split(","):
            part = part.strip().lower()
            if part:
                forms.append(part)
    # 主形式：圆括号之前的部分
    main = re.sub(r"\([^)]*\)", "", raw).strip()
    for part in main.split(","):
        part = part.strip().lower()
        if part:
            forms.insert(0, part)
    return tuple(dict.fromkeys(forms))


def _parse_suffix_forms(raw: str) -> tuple[str, ...]:
    """解析后缀: '-AGE, -ITY, -TION' 或 'AGE, ITY, TION' → ('age', 'ity', 'tion')."""
    forms: list[str] = []
    for part in raw.split(","):
        part = part.strip().lstrip("-").strip().lower()
        if part:
            forms.append(part)
    return tuple(dict.fromkeys(forms))


def _load_csv(filename: str, category: str, parser) -> list[MorphemeEntry]:
    """从 CSV 文件加载词素条目."""
    path = _DATA_DIR / filename
    if not path.exists():
        logger.warning("词素知识库文件不存在: %s", path)
        return []
    entries: list[MorphemeEntry] = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # 获取列名（第二列 = 词根/前缀/后缀，第三列 = 来源）
        fieldnames = reader.fieldnames or []
        if len(fieldnames) < 3:
            logger.warning("CSV 列数不足: %s", path)
            return []
        form_col = fieldnames[1]
        desc_col = fieldnames[2]
        for row in reader:
            raw_form = row.get(form_col, "").strip()
            description = row.get(desc_col, "").strip()
            if not raw_form:
                continue
            forms = parser(raw_form)
            if forms:
                entries.append(MorphemeEntry(
                    category=category,
                    forms=forms,
                    display=raw_form,
                    description=description,
                ))
    return entries


_kb_cache: tuple[MorphemeEntry, ...] | None = None
_kb_lock = threading.Lock()


def get_morpheme_kb() -> tuple[MorphemeEntry, ...]:
    """延迟加载 + 双检锁单例，返回不可变 tuple."""
    global _kb_cache
    if _kb_cache is not None:
        return _kb_cache
    with _kb_lock:
        if _kb_cache is not None:
            return _kb_cache
        entries: list[MorphemeEntry] = []
        entries.extend(_load_csv("morpheme_roots.csv", "root", _parse_root_forms))
        entries.extend(_load_csv("morpheme_prefixes.csv", "prefix", _parse_prefix_forms))
        entries.extend(_load_csv("morpheme_suffixes.csv", "suffix", _parse_suffix_forms))
        logger.info("词素知识库加载完成: %d 条", len(entries))
        _kb_cache = tuple(entries)
        return _kb_cache


_fmt_cache: str | None = None
_fmt_lock = threading.Lock()

_INJECTION_PATTERNS = re.compile(
    r"(?i)(ignore|forget|disregard)\s+(\w+\s+)?(previous|above|prior)\s+(instructions?|rules?|prompts?)",
)


def _sanitize_kb_entry(text: str) -> str:
    """清洗知识库条目，移除疑似 prompt injection 模式."""
    return _INJECTION_PATTERNS.sub("[FILTERED]", text)


def format_kb_for_prompt() -> str:
    """将知识库格式化为可注入 system prompt 的文本（模块级缓存）."""
    global _fmt_cache
    if _fmt_cache is not None:
        return _fmt_cache
    with _fmt_lock:
        if _fmt_cache is not None:
            return _fmt_cache
        kb = get_morpheme_kb()
        sections: dict[str, list[str]] = {"prefix": [], "root": [], "suffix": []}
        for entry in kb:
            sections[entry.category].append(
                f"  - {_sanitize_kb_entry(entry.display)}: {_sanitize_kb_entry(entry.description)}"
            )
        parts: list[str] = []
        for cat, label in [("prefix", "前缀"), ("root", "词根"), ("suffix", "后缀")]:
            if sections[cat]:
                parts.append(f"## {label}\n" + "\n".join(sections[cat]))
        _fmt_cache = "\n\n".join(parts)
        return _fmt_cache
