"""助记生成器: 4 种类型，每种可返回 valid: false 表示不适用."""

import json
from typing import Any, Optional

from vocab_qc.core.generators.base import ContentGenerator

# 助记结果的统一 key: valid, formula, chant, script
# valid=false 时表示该类型不适用于此单词


class _MnemonicBase(ContentGenerator):
    """助记生成器基类，统一处理 valid/false 逻辑."""

    def _build_user_prompt(self, word: str, pos: Optional[str], meaning: Optional[str]) -> str:
        return f"Word: {word} | POS: {pos or '未知'} | Meaning: {meaning or '未知'}"

    @staticmethod
    def _process_result(result: dict) -> dict:
        if not result:
            return {"valid": False, "content": None, "content_cn": None}
        if result.get("valid") is False:
            return {"valid": False, "content": None, "content_cn": None}

        formula = result.get("formula", "")
        chant = result.get("chant", "")
        script = result.get("script", "")
        content = json.dumps(
            {"formula": formula, "chant": chant, "script": script},
            ensure_ascii=False,
        )
        return {
            "valid": True,
            "content": content,
            "content_cn": None,
            "formula": formula,
            "chant": chant,
            "script": script,
        }

    def generate(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs: Any) -> dict:
        ai_config = self.resolve_ai_config(**kwargs)
        user_prompt = self._build_user_prompt(word, pos, meaning)
        result = self._call_ai(
            ai_config.system_prompt, user_prompt,
            model=ai_config.model, api_key=ai_config.api_key, base_url=ai_config.base_url,
        )
        return self._process_result(result)

    async def generate_async(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs: Any) -> dict:
        ai_config = self.resolve_ai_config(**kwargs)
        user_prompt = self._build_user_prompt(word, pos, meaning)
        result = await self._call_ai_async(
            ai_config.system_prompt, user_prompt,
            model=ai_config.model, api_key=ai_config.api_key, base_url=ai_config.base_url,
        )
        return self._process_result(result)

    def _fallback_prompt(self) -> str:
        return (
            "你是英语教学专家，为中小学生生成单词助记法。\n"
            '如果该词不适用此助记类型，返回: {"valid": false}\n'
            '否则返回: {"valid": true, "formula": "核心公式", "chant": "助记口诀", "script": "老师话术"}'
        )


class RootAffixMnemonicGenerator(_MnemonicBase):
    """词根词缀助记."""

    dimension = "mnemonic_root_affix"
    prompt_filename = "助记-词根词缀.md"


class WordInWordMnemonicGenerator(_MnemonicBase):
    """词中词助记."""

    dimension = "mnemonic_word_in_word"
    prompt_filename = "助记-词中词.md"


class SoundMeaningMnemonicGenerator(_MnemonicBase):
    """音义联想助记."""

    dimension = "mnemonic_sound_meaning"
    prompt_filename = "助记-音义联想.md"


class ExamAppMnemonicGenerator(_MnemonicBase):
    """考试应用助记."""

    dimension = "mnemonic_exam_app"
    prompt_filename = "助记-考试应用.md"
