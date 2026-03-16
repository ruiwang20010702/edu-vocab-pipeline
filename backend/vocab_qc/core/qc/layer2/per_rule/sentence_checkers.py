"""Sentence 维度 AI 校验: E1-E5, E8(语义), E9, E10, E11."""

from typing import Optional

from vocab_qc.core.qc.layer2.ai_base import AiRuleChecker
from vocab_qc.core.qc.registry import RuleRegistry

_SENTENCE_SYSTEM = (
    "你是中小学英语教学质检专家。请严格按要求判断例句质量。"
    "返回 JSON: {\"passed\": true/false, \"detail\": \"原因\"}"
)


@RuleRegistry.register_layer2
class E1GrammarLevel(AiRuleChecker):
    rule_id = "E1"
    dimension = "sentence"
    description = "语法难度"
    system_prompt = _SENTENCE_SYSTEM

    def build_user_prompt(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> str:
        return f"例句: {content}\n\n请判断此例句的语法是否在初中英语教学大纲范围内。"


@RuleRegistry.register_layer2
class E2MainStructure(AiRuleChecker):
    rule_id = "E2"
    dimension = "sentence"
    description = "主干结构"
    system_prompt = _SENTENCE_SYSTEM

    def build_user_prompt(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> str:
        return f"例句: {content}\n\n请判断此例句是否以简单陈述句结构（主谓宾或主系表）为主。"


@RuleRegistry.register_layer2
class E3ConjunctionLimit(AiRuleChecker):
    rule_id = "E3"
    dimension = "sentence"
    description = "连接词限制"
    system_prompt = _SENTENCE_SYSTEM

    def build_user_prompt(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> str:
        return f"例句: {content}\n\n请判断此例句的连接词是否仅使用 and/but/so/because。如果例句是简单句则直接通过。"


@RuleRegistry.register_layer2
class E4ClauseLimit(AiRuleChecker):
    rule_id = "E4"
    dimension = "sentence"
    description = "从句限制"
    system_prompt = _SENTENCE_SYSTEM

    def build_user_prompt(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> str:
        return (
            f"例句: {content}\n\n"
            "请判断：如果例句包含定语从句，是否仅由 that/which/who 引导，且从句长度 ≤ 5 词？"
            "注：because/so 等引导的状语从句不受此限制。无从句的简单句直接通过。"
        )


@RuleRegistry.register_layer2
class E5ForbiddenStructure(AiRuleChecker):
    rule_id = "E5"
    dimension = "sentence"
    description = "禁区检测"
    system_prompt = _SENTENCE_SYSTEM

    def build_user_prompt(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> str:
        return (
            f"例句: {content}\n\n"
            "请判断此例句是否包含以下禁区结构：非谓语动词短语作状语、虚拟语气、倒装句、独立主格。"
        )


@RuleRegistry.register_layer2
class E8SemanticMatch(AiRuleChecker):
    rule_id = "E8_AI"
    dimension = "sentence"
    description = "中文翻译语义对应"
    system_prompt = _SENTENCE_SYSTEM

    def build_user_prompt(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> str:
        content_cn = kwargs.get("content_cn", "")
        return f"英文例句: {content}\n中文翻译: {content_cn}\n\n请判断中文翻译是否与英文例句语义对应。"


@RuleRegistry.register_layer2
class E9MeaningMatch(AiRuleChecker):
    rule_id = "E9"
    dimension = "sentence"
    description = "义项匹配"
    system_prompt = _SENTENCE_SYSTEM

    def build_user_prompt(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> str:
        return (
            f"单词: {word}\n标注义项: {meaning or '无'}\n例句: {content}\n\n"
            "请判断例句中目标词的用法是否对应标注的义项，有无张冠李戴。"
        )


@RuleRegistry.register_layer2
class E10Naturalness(AiRuleChecker):
    rule_id = "E10"
    dimension = "sentence"
    description = "语言地道性"
    system_prompt = _SENTENCE_SYSTEM

    def build_user_prompt(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> str:
        return f"例句: {content}\n\n请判断此例句是否自然地道，是否存在「中式英语」表达。"


@RuleRegistry.register_layer2
class E11ContentSafety(AiRuleChecker):
    rule_id = "E11"
    dimension = "sentence"
    description = "内容安全性"
    system_prompt = _SENTENCE_SYSTEM

    def build_user_prompt(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> str:
        return f"例句: {content}\n\n请判断此例句内容是否阳光中性，是否涉及暴力、低俗、性别种族歧视或宗教政治倾向。"
