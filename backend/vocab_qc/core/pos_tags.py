"""词性标签权威口径与历史兼容集合。"""

# 学科于 2026-05-26 确认的对外/新入库权威格式：23 类，全部带点。
AUTHORITATIVE_POS_TAGS = frozenset({
    "n.", "v.", "adj.", "adv.", "prep.", "pron.", "num.", "int.",
    "abbr.", "phr.", "n phr.", "det.", "aux.", "conj.", "art.",
    "mod.", "excl.", "quant.", "phr v.", "col.", "v phr.",
    "a phr.", "p phr.",
})

AUTHORITATIVE_POS_BARE_TAGS = frozenset(tag[:-1] for tag in AUTHORITATIVE_POS_TAGS)

# 仅为历史数据兼容保留；新导入文件不应继续生产这些标签。
LEGACY_COMPAT_POS_BARE_TAGS = frozenset({"vi", "vt", "interj", "modal v"})
LEGACY_COMPAT_POS_TAGS = frozenset(
    {f"{tag}." for tag in LEGACY_COMPAT_POS_BARE_TAGS}
    | set(LEGACY_COMPAT_POS_BARE_TAGS)
)

# M3 兼容历史不带点数据，但权威的新产出始终使用 AUTHORITATIVE_POS_TAGS。
VALID_POS_TAGS = frozenset(
    set(AUTHORITATIVE_POS_TAGS)
    | set(AUTHORITATIVE_POS_BARE_TAGS)
    | set(LEGACY_COMPAT_POS_TAGS)
)
