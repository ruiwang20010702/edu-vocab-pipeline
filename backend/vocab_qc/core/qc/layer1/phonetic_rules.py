"""Phonetic 维度 Layer 1 规则: P1, P2."""

from typing import Optional

from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.registry import RuleRegistry, _RuleCheckerBase

# IPA 音标合法字符集（美式 GA）
IPA_CHARS = set("aɑæbdðeəɛfɡhiɪɨjklɫmmnŋoɔɒøpɹrstθuʊʌvwxyzʒʃʔːˈˌ·()/ ")


@RuleRegistry.register_layer1
class P1IpaFormat(_RuleCheckerBase):
    """P1: 统一采用 IPA 国际音标，美式发音（GA）."""

    rule_id = "P1"
    dimension = "phonetic"
    description = "IPA 格式校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        ipa = kwargs.get("ipa", content)
        if not ipa:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少音标")

        # 检查是否用斜杠包裹
        stripped = ipa.strip()
        if not (stripped.startswith("/") and stripped.endswith("/")):
            return RuleResult(rule_id=self.rule_id, passed=False, detail=f"音标未用斜杠包裹: {ipa!r}")

        # 检查内部字符是否合法
        inner = stripped[1:-1]
        invalid_chars = set(inner) - IPA_CHARS
        if invalid_chars:
            return RuleResult(
                rule_id=self.rule_id,
                passed=False,
                detail=f"音标包含非法字符: {invalid_chars}",
            )

        return RuleResult(rule_id=self.rule_id, passed=True)


@RuleRegistry.register_layer1
class P2IpaSyllableAlignment(_RuleCheckerBase):
    """P2: 音标-音节对齐，分隔数一致."""

    rule_id = "P2"
    dimension = "phonetic"
    description = "音标-音节对齐校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        ipa = kwargs.get("ipa", "")
        syllables = kwargs.get("syllables", "")

        if not ipa or not syllables:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少音标或音节数据")

        # 计算音节数（按 · 分隔）
        syllable_count = len(syllables.split("·"))

        # 计算音标中的音节数（按 · 分隔，去掉斜杠）
        ipa_inner = ipa.strip("/")
        ipa_syllable_count = len(ipa_inner.split("·"))

        if syllable_count != ipa_syllable_count:
            return RuleResult(
                rule_id=self.rule_id,
                passed=False,
                detail=f"音节数不一致: 音节={syllable_count}, 音标={ipa_syllable_count}",
            )

        return RuleResult(rule_id=self.rule_id, passed=True)
