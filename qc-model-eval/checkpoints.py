"""每个维度的检查点定义，与黄金案例表/评估表的列一一对齐。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Checkpoint:
    id: str           # 短 ID (用于 JSON key)
    name_cn: str      # 中文列头（与 xlsx 对齐）


# ── 例句 ──────────────────────────────────────────────
SENTENCE_CHECKPOINTS = [
    Checkpoint("simple_sentence", "是否为绝对简单句（一个主语一个谓语，无任何从句）"),
    Checkpoint("vocab_ceiling", "除目标词外，所有词汇均为A1基础高频词"),
    Checkpoint("scenario", "场景贴近12-15岁青少年日常（校园、家庭、天气等）"),
    Checkpoint("exam_collocation", "若目标词有必考固定搭配，例句中已使用"),
    Checkpoint("meaning_pos", "例句中目标词用法对应给定的具体义项和词性"),
    Checkpoint("translation", "中文翻译与英文语义准确对应，无增减或扭曲"),
    Checkpoint("naturalness", "表达自然地道，无中式英语"),
    Checkpoint("safety", "内容阳光积极，适合K-12学生"),
]

# ── 语块 ──────────────────────────────────────────────
CHUNK_CHECKPOINTS = [
    Checkpoint("collocation", "是否为高频固定搭配（动宾/形名/动介等），非随意组合"),
    Checkpoint("meaning_pos", "目标词在语块中的用法对应给定义项和词性"),
    Checkpoint("translation", "中文翻译自然准确，2-6个汉字"),
    Checkpoint("naturalness", "表达自然地道，无中式英语逻辑"),
    Checkpoint("non_sentence", "是短语/词组，非完整句子"),
    Checkpoint("safety", "内容阳光积极，适合K-12学生"),
]

# ── 音节 ──────────────────────────────────────────────
SYLLABLE_CHECKPOINTS = [
    Checkpoint("monosyllable", "单音节词未切分 / 多音节词已正确切分"),
    Checkpoint("vowel_anchor", "每个切分块恰好包含一个发音元音（-le例外）"),
    Checkpoint("atomic_unit", "原子单位未被拆分（sh/ch/th/ea/ee/ar/or等）"),
    Checkpoint("silent_letter", "静音字母（词尾silent-e、silent gh）未独立成音节"),
    Checkpoint("consonant_split", "辅音切分位置正确（VCV单辅音归后，VCCV从中切，双写切开）"),
    Checkpoint("prefix_intact", "常见前缀保持完整（re-/un-/dis-/pre-/con-/ab-等）"),
    Checkpoint("separator", "仅使用中圆点·(U+00B7)作为分隔符"),
]

# ── 助记-词根词缀 ────────────────────────────────────────
MNEMONIC_ROOT_AFFIX_CHECKPOINTS = [
    Checkpoint("etymology", "词根词缀拆解有据可查（非谐音/民间词源）"),
    Checkpoint("formula", "公式格式正确：component(中文含义) + component(中文含义)"),
    Checkpoint("suffix_pos", "后缀标注的词性与给定词性一致"),
    Checkpoint("chant_coherence", "口诀逻辑对应公式内容，无额外引入"),
    Checkpoint("six_steps", "老师话术包含完整6步（纠音/拆解/画面/合成/裂变/升华）"),
    Checkpoint("scene_logic", "画面还原由词根词缀含义逻辑推出，非强行联想"),
    Checkpoint("word_family", "批量裂变词与目标词共享同一词根"),
    Checkpoint("no_props", "话术未提及任何实体教学道具（卡片/黑板/教鞭等）"),
    Checkpoint("tone", "语气口语自然，像直播互动，非AI朗读感"),
    Checkpoint("no_dismiss", "话术中没有'下课'等相关表述"),
]

# ── 助记-词中词 ──────────────────────────────────────────
MNEMONIC_WORD_IN_WORD_CHECKPOINTS = [
    Checkpoint("internal_words", "内部熟词均为连续字母序列且为高频常见词"),
    Checkpoint("full_coverage", "所有内部词拼合后完全覆盖原词（无缺漏无多余）"),
    Checkpoint("formula", "公式格式正确：[熟词](中文) + [熟词](中文)"),
    Checkpoint("chant_coherence", "口诀逻辑对应公式内容，无额外引入"),
    Checkpoint("six_steps", "老师话术包含完整6步（纠音/搜索/画面/合成/关联/升华）"),
    Checkpoint("scene_logic", "画面还原基于内部熟词构建，与目标词义有逻辑桥梁"),
    Checkpoint("meaning_align", "整体助记逻辑指向给定义项和词性"),
    Checkpoint("no_props", "话术未提及任何实体教学道具"),
    Checkpoint("tone", "语气口语自然，像直播互动"),
    Checkpoint("no_dismiss", "话术中没有'下课'等相关表述"),
]

# ── 助记-音义联想 ────────────────────────────────────────
MNEMONIC_SOUND_MEANING_CHECKPOINTS = [
    Checkpoint("phonetic_similarity", "谐音与英文发音高度相似（≥60%音似度）"),
    Checkpoint("phonetic_appropriate", "谐音为常见中文词/象声词，无消极/低俗含义"),
    Checkpoint("formula", "公式格式正确：/IPA发音/ ≈ 中文谐音"),
    Checkpoint("chant_coherence", "口诀逻辑对应公式内容，无额外引入"),
    Checkpoint("six_steps", "老师话术包含完整6步（纠音/谐音/画面/合成/发音保护/升华）"),
    Checkpoint("scene_logic", "画面还原基于中文谐音构建，与词义有情感桥梁"),
    Checkpoint("pronunciation_firewall", "第5步明确提醒学生谐音仅为记忆辅助，不可替代正确发音"),
    Checkpoint("meaning_align", "整体助记逻辑指向给定义项和词性"),
    Checkpoint("no_props", "话术未提及任何实体教学道具"),
    Checkpoint("tone", "语气口语自然，像直播互动"),
    Checkpoint("no_dismiss", "话术中没有'下课'等相关表述"),
]

# ── 助记-考试应用 ────────────────────────────────────────
MNEMONIC_EXAM_APP_CHECKPOINTS = [
    Checkpoint("exam_point", "考点为真实高频中高考搭配（非泛泛而谈）"),
    Checkpoint("formula", "公式格式正确：目标词(词性) + 核心搭配 = 中文含义(高频考点)"),
    Checkpoint("logic", "考点逻辑精准具体，指出了搭配的核心语法规则"),
    Checkpoint("three_steps", "老师话术包含完整3步（锁定考点/实战例句/避坑警示）"),
    Checkpoint("example_sentence", "实战例句语法正确且清晰示范了该考试搭配"),
    Checkpoint("example_translation", "实战例句的中文翻译准确自然"),
    Checkpoint("trap_accuracy", "避坑警示指出了具体的错误选项（考场陷阱）"),
    Checkpoint("no_props", "话术未提及任何实体教学道具"),
    Checkpoint("tone", "语气犀利有提分感，像考前冲刺讲师"),
    Checkpoint("no_dismiss", "话术中没有'下课'等相关表述"),
]

# ── 维度 → 检查点列表 映射 ────────────────────────────────
DIMENSION_CHECKPOINTS: dict[str, list[Checkpoint]] = {
    "sentence": SENTENCE_CHECKPOINTS,
    "chunk": CHUNK_CHECKPOINTS,
    "syllable": SYLLABLE_CHECKPOINTS,
    "mnemonic_root_affix": MNEMONIC_ROOT_AFFIX_CHECKPOINTS,
    "mnemonic_word_in_word": MNEMONIC_WORD_IN_WORD_CHECKPOINTS,
    "mnemonic_sound_meaning": MNEMONIC_SOUND_MEANING_CHECKPOINTS,
    "mnemonic_exam_app": MNEMONIC_EXAM_APP_CHECKPOINTS,
}


def build_json_output_instruction(dimension: str) -> str:
    """生成 JSON 输出格式指令，附加到 system prompt 末尾。"""
    checkpoints = DIMENSION_CHECKPOINTS[dimension]
    fields = ",\n".join(
        f'    "{cp.id}": "Yes/No/NA"' for cp in checkpoints
    )
    return f"""

IMPORTANT: You MUST respond in the following JSON format ONLY. Do not include any text before or after the JSON.

{{
    "checkpoints": {{
{fields}
    }},
    "overall": "PASS/FAIL",
    "reason": "Brief explanation in Chinese (1-2 sentences)"
}}

Rules:
- "Yes" = this check passes, "No" = this check fails, "NA" = not applicable
- "overall": "FAIL" if ANY checkpoint is "No"; "PASS" only if all are "Yes" or "NA"
- "reason": Summarize which checks failed and why, or say "全部通过" if all pass
"""
