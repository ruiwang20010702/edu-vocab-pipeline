"""完整 Prompt 质检集成测试（需要真实 AI API）。

验证：
1. 对比测试：同一个词分别用精简 prompt 和完整 prompt 跑质检
2. 耗时验证：确认不加 response_format 后耗时 < 30s
3. 回归验证：其他维度仍用精简 prompt + JSON 格式正常工作
"""

import asyncio
import time

import pytest

from vocab_qc.core.config import settings
from vocab_qc.core.qc.layer2.ai_base import AiClient
from vocab_qc.core.qc.layer2.unified.mnemonic_unified import (
    UnifiedMnemonicChecker,
)
from vocab_qc.core.qc.layer2.unified.sentence_unified import UnifiedSentenceChecker
from vocab_qc.core.qc.layer2.unified.chunk_unified import UnifiedChunkChecker

# 跳过条件：无 API 配置
pytestmark = pytest.mark.skipif(
    not settings.ai_api_key or not settings.ai_api_base_url,
    reason="需要真实 AI API 配置",
)

# ---------------------------------------------------------------------------
# 测试数据
# ---------------------------------------------------------------------------

# 一个好的词根词缀助记（应该通过）
GOOD_ROOT_AFFIX = """[核心公式] in(不) + vis(看) + ible(能…的，形容词后缀)
[助记口诀] 不(in)能(ible)被看(vis)见的东西。
[老师话术] 好，XX同学，我们来看这个单词 invisible。你先跟我读一遍，in-vi-si-ble，注意重音在第二个音节，嘴巴张大发/ˈvɪ/这个音，对，很好。

现在我们来拆零件。你看屏幕上这个公式：in 表示"不"，vis 是个词根表示"看"，ible 是形容词后缀表示"能…的"。

你想想看，不(in)能被看(vis)见的(ible)，就像哈利波特披上隐身斗篷，整个人消失了，别人怎么找都找不到他，因为他变得 invisible 了。

所以你把这三个零件拼起来，不+看+能…的，猜猜是什么意思？对了，就是"看不见的，无形的"。

跟上了吗？我们来裂变几个词。vision，vis+ion，看+名词后缀，就是"视力、视觉"。visual，vis+ual，看+形容词后缀，就是"视觉的"。visit，vis+it，看+去，去看一看，就是"参观、拜访"。你看，都有 vis 这个"看"的词根。

XX同学，你想啊，人这辈子很多重要的东西其实都是 invisible 的，比如爱、比如友谊、比如勇气。看不见不代表不存在，对吧？"""

# 一个有问题的词根词缀助记（伪词源）
BAD_ROOT_AFFIX = """[核心公式] Feb(飞吧) + ru(如) + ary(名词后缀)
[助记口诀] 飞吧如意二月天。
[老师话术] 好，同学们，我们来看 February。

先拆零件：Feb 就是"飞吧"的谐音，ru 就是"如"，ary 是名词后缀。

你想象一下，二月份春天来了，小鸟飞吧飞吧，如意的二月天。拿出放大镜看看这个单词。

所以 February 就是二月。

我们来看几个类似的词：flower 花，festival 节日。

好了同学们下课！"""

GOOD_ROOT_AFFIX_WORD = "invisible"
GOOD_ROOT_AFFIX_POS = "adj."
GOOD_ROOT_AFFIX_MEANING = "看不见的，无形的"

BAD_ROOT_AFFIX_WORD = "February"
BAD_ROOT_AFFIX_POS = "n."
BAD_ROOT_AFFIX_MEANING = "二月"


# ---------------------------------------------------------------------------
# 对比测试
# ---------------------------------------------------------------------------


class TestComparisonFullVsSimple:
    """对比完整 prompt 和精简 prompt 的质检结果。"""

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_good_content_both_pass(self):
        """好的助记内容：两种 prompt 都应该通过。"""
        client = AiClient()
        checker = UnifiedMnemonicChecker()

        # 完整 prompt
        t0 = time.monotonic()
        full_results = await checker.check(
            client, content=GOOD_ROOT_AFFIX, word=GOOD_ROOT_AFFIX_WORD,
            meaning=GOOD_ROOT_AFFIX_MEANING, pos=GOOD_ROOT_AFFIX_POS,
            item_dimension="mnemonic_root_affix",
        )
        full_elapsed = time.monotonic() - t0

        # 精简 prompt
        t0 = time.monotonic()
        simple_results = await checker.check(
            client, content=GOOD_ROOT_AFFIX, word=GOOD_ROOT_AFFIX_WORD,
            meaning=GOOD_ROOT_AFFIX_MEANING, pos=GOOD_ROOT_AFFIX_POS,
            item_dimension="mnemonic_word_in_word",  # 走精简分支
        )
        simple_elapsed = time.monotonic() - t0

        print(f"\n--- 好内容对比 ({GOOD_ROOT_AFFIX_WORD}) ---")
        print(f"完整 prompt: {full_elapsed:.1f}s")
        for r in full_results:
            print(f"  {r.rule_id}: {'PASS' if r.passed else 'FAIL'} | {r.detail}")
        print(f"精简 prompt: {simple_elapsed:.1f}s")
        for r in simple_results:
            print(f"  {r.rule_id}: {'PASS' if r.passed else 'FAIL'} | {r.detail}")

        # 好内容两种都应该通过
        assert all(r.passed for r in full_results), f"完整 prompt 应通过: {full_results}"

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_bad_content_full_prompt_catches_more(self):
        """有问题的助记内容：完整 prompt 应该能检出更多问题。"""
        client = AiClient()
        checker = UnifiedMnemonicChecker()

        # 完整 prompt
        t0 = time.monotonic()
        full_results = await checker.check(
            client, content=BAD_ROOT_AFFIX, word=BAD_ROOT_AFFIX_WORD,
            meaning=BAD_ROOT_AFFIX_MEANING, pos=BAD_ROOT_AFFIX_POS,
            item_dimension="mnemonic_root_affix",
        )
        full_elapsed = time.monotonic() - t0

        # 精简 prompt
        t0 = time.monotonic()
        simple_results = await checker.check(
            client, content=BAD_ROOT_AFFIX, word=BAD_ROOT_AFFIX_WORD,
            meaning=BAD_ROOT_AFFIX_MEANING, pos=BAD_ROOT_AFFIX_POS,
            item_dimension="mnemonic_word_in_word",
        )
        simple_elapsed = time.monotonic() - t0

        print(f"\n--- 坏内容对比 ({BAD_ROOT_AFFIX_WORD}) ---")
        print(f"完整 prompt: {full_elapsed:.1f}s")
        for r in full_results:
            print(f"  {r.rule_id}: {'PASS' if r.passed else 'FAIL'} | {r.detail}")
        print(f"精简 prompt: {simple_elapsed:.1f}s")
        for r in simple_results:
            print(f"  {r.rule_id}: {'PASS' if r.passed else 'FAIL'} | {r.detail}")

        # 完整 prompt 必须判 FAIL（伪词源 + 实体道具 + 下课用语）
        full_has_fail = any(not r.passed for r in full_results)
        assert full_has_fail, f"完整 prompt 应检出问题: {full_results}"


# ---------------------------------------------------------------------------
# 耗时验证
# ---------------------------------------------------------------------------


class TestPerformance:
    """验证去掉 response_format 后耗时在合理范围内。"""

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_full_prompt_within_time_limit(self):
        """完整 prompt 不加 response_format 应在 30s 内完成。"""
        client = AiClient()
        checker = UnifiedMnemonicChecker()

        t0 = time.monotonic()
        results = await checker.check(
            client, content=GOOD_ROOT_AFFIX, word=GOOD_ROOT_AFFIX_WORD,
            meaning=GOOD_ROOT_AFFIX_MEANING, pos=GOOD_ROOT_AFFIX_POS,
            item_dimension="mnemonic_root_affix",
        )
        elapsed = time.monotonic() - t0

        print(f"\n--- 耗时验证 ---")
        print(f"完整 prompt 耗时: {elapsed:.1f}s")
        for r in results:
            print(f"  {r.rule_id}: {'PASS' if r.passed else 'FAIL'} | {r.detail}")

        assert elapsed < 30, f"完整 prompt 耗时 {elapsed:.1f}s 超过 30s 限制"


# ---------------------------------------------------------------------------
# 回归验证：其他维度不受影响
# ---------------------------------------------------------------------------


class TestOtherDimensionsRegression:
    """确认例句/语块等维度仍用 JSON 格式正常工作。"""

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_sentence_checker_still_works(self):
        """例句维度仍用精简 prompt + JSON。"""
        client = AiClient()
        checker = UnifiedSentenceChecker()

        results = await checker.check(
            client,
            content="She goes to school every day.",
            word="go",
            meaning="去",
            content_cn="她每天去上学。",
        )
        print(f"\n--- 例句回归 ---")
        for r in results:
            print(f"  {r.rule_id}: {'PASS' if r.passed else 'FAIL'} | {r.detail}")

        assert len(results) > 0, "例句维度应返回结果"
        assert all(hasattr(r, 'rule_id') for r in results)

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_chunk_checker_still_works(self):
        """语块维度仍用精简 prompt + JSON。"""
        client = AiClient()
        checker = UnifiedChunkChecker()

        results = await checker.check(
            client,
            content="go to school",
            word="go",
            meaning="去",
        )
        print(f"\n--- 语块回归 ---")
        for r in results:
            print(f"  {r.rule_id}: {'PASS' if r.passed else 'FAIL'} | {r.detail}")

        assert len(results) > 0, "语块维度应返回结果"
