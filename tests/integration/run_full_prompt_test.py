"""完整 Prompt 质检集成测试（异步并行，直接运行，绕过 conftest 清空 API key）。

用法: PYTHONPATH=backend .venv/bin/python tests/integration/run_full_prompt_test.py

验证全部 7 个维度的完整 prompt 质检，所有维度并行调用 AI 服务。
"""

import asyncio
import time

from vocab_qc.core.config import settings
from vocab_qc.core.qc.layer2.ai_base import AiClient
from vocab_qc.core.qc.layer2.unified.mnemonic_unified import UnifiedMnemonicChecker
from vocab_qc.core.qc.layer2.unified.sentence_unified import UnifiedSentenceChecker
from vocab_qc.core.qc.layer2.unified.chunk_unified import UnifiedChunkChecker
from vocab_qc.core.qc.layer2.unified.syllable_unified import UnifiedSyllableChecker

# ---------------------------------------------------------------------------
# 测试数据
# ---------------------------------------------------------------------------

GOOD_ROOT_AFFIX = """[核心公式] in(不) + vis(看) + ible(能…的，形容词后缀)
[助记口诀] 不(in)能(ible)被看(vis)见的东西。
[老师话术] 好，XX同学，我们来看这个单词 invisible。你先跟我读一遍，in-vi-si-ble，注意重音在第二个音节，嘴巴张大发/ˈvɪ/这个音，对，很好。

现在我们来拆零件。你看屏幕上这个公式：in 表示"不"，vis 是个词根表示"看"，ible 是形容词后缀表示"能…的"。

你想想看，不(in)能被看(vis)见的(ible)，就像哈利波特披上隐身斗篷，整个人消失了，别人怎么找都找不到他，因为他变得 invisible 了。

所以你把这三个零件拼起来，不+看+能…的，猜猜是什么意思？对了，就是"看不见的，无形的"。

跟上了吗？我们来裂变几个词。vision，vis+ion，看+名词后缀，就是"视力、视觉"。visual，vis+ual，看+形容词后缀，就是"视觉的"。visit，vis+it，看+去，去看一看，就是"参观、拜访"。你看，都有 vis 这个"看"的词根。

XX同学，你想啊，人这辈子很多重要的东西其实都是 invisible 的，比如爱、比如友谊、比如勇气。看不见不代表不存在，对吧？"""

BAD_ROOT_AFFIX = """[核心公式] Feb(飞吧) + ru(如) + ary(名词后缀)
[助记口诀] 飞吧如意二月天。
[老师话术] 好，同学们，我们来看 February。

先拆零件：Feb 就是"飞吧"的谐音，ru 就是"如"，ary 是名词后缀。

你想象一下，二月份春天来了，小鸟飞吧飞吧，如意的二月天。拿出放大镜看看这个单词。

所以 February 就是二月。

我们来看几个类似的词：flower 花，festival 节日。

好了同学们下课！"""


def _format_results(label: str, results, elapsed: float) -> str:
    lines = [f"\n{label} ({elapsed:.1f}s):"]
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"  {r.rule_id}: {status} | {r.detail}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 每个维度的测试协程
# ---------------------------------------------------------------------------


async def check_one(label: str, checker, client: AiClient, **kwargs) -> tuple[str, list, float]:
    """调用单个 checker 并计时，返回 (label, results, elapsed)。"""
    t0 = time.monotonic()
    results = await checker.check(client, **kwargs)
    elapsed = time.monotonic() - t0
    return label, results, elapsed


async def main():
    if not settings.ai_api_key or not settings.ai_api_base_url:
        print("AI API 未配置，跳过集成测试")
        return

    print(f"AI 配置: model={settings.ai_model}, gateway={settings.ai_gateway_mode}")
    print()

    client = AiClient()
    mnemonic = UnifiedMnemonicChecker()
    sentence = UnifiedSentenceChecker()
    chunk = UnifiedChunkChecker()
    syllable = UnifiedSyllableChecker()

    # -----------------------------------------------------------------------
    # 并行发起全部 7 个维度 + 2 个对照（共 9 个 AI 调用）
    # -----------------------------------------------------------------------
    tasks = [
        # 4 个助记维度
        check_one(
            "1. mnemonic_root_affix (好内容)", mnemonic, client,
            content=GOOD_ROOT_AFFIX, word="invisible",
            meaning="看不见的，无形的", pos="adj.",
            item_dimension="mnemonic_root_affix",
        ),
        check_one(
            "2. mnemonic_root_affix (坏内容/伪词源)", mnemonic, client,
            content=BAD_ROOT_AFFIX, word="February",
            meaning="二月", pos="n.",
            item_dimension="mnemonic_root_affix",
        ),
        check_one(
            "3. mnemonic_word_in_word", mnemonic, client,
            content=(
                "[核心公式] to+get+her\n"
                "[助记口诀] 去(to)拿到(get)她(her)，就是在一起\n"
                "[老师话术] 好，同学们来看 together。你仔细看这个词里面藏了三个小词……"
            ),
            word="together", meaning="一起", pos="adv.",
            item_dimension="mnemonic_word_in_word",
        ),
        check_one(
            "4. mnemonic_sound_meaning", mnemonic, client,
            content=(
                '[核心公式] pest 谐音"拍死它"\n'
                "[助记口诀] 拍死它！害虫！\n"
                '[老师话术] 好，同学们来看 pest。你读一读，pest，是不是听起来像"拍死它"……'
            ),
            word="pest", meaning="害虫", pos="n.",
            item_dimension="mnemonic_sound_meaning",
        ),
        check_one(
            "5. mnemonic_exam_app", mnemonic, client,
            content=(
                "[核心公式] important 考试高频词\n"
                "[助记口诀] 重要的事情要 import（进口）到大脑\n"
                "[老师话术] 好，同学们来看 important。这个词在考试中出现频率非常高……"
            ),
            word="important", meaning="重要的", pos="adj.",
            item_dimension="mnemonic_exam_app",
        ),
        # 例句
        check_one(
            "6. sentence", sentence, client,
            content="She goes to school every day.",
            word="go", meaning="去",
            content_cn="她每天去上学。",
        ),
        # 语块
        check_one(
            "7. chunk", chunk, client,
            content="go to school",
            word="go", meaning="去",
        ),
        # 音节（2 个）
        check_one(
            "8. syllable (apple)", syllable, client,
            content="ap·ple", word="apple",
        ),
        check_one(
            "9. syllable (invisible)", syllable, client,
            content="in·vi·si·ble", word="invisible",
        ),
    ]

    print(f"并行发起 {len(tasks)} 个 AI 调用...")
    print("=" * 60)

    t_all = time.monotonic()
    results_list = await asyncio.gather(*tasks, return_exceptions=True)
    total_elapsed = time.monotonic() - t_all

    # -----------------------------------------------------------------------
    # 打印结果
    # -----------------------------------------------------------------------
    pass_count = 0
    fail_count = 0
    error_count = 0

    for item in results_list:
        if isinstance(item, Exception):
            error_count += 1
            print(f"\nERROR: {item}")
            continue

        label, results, elapsed = item
        print(_format_results(label, results, elapsed))

        for r in results:
            if r.passed:
                pass_count += 1
            else:
                fail_count += 1

    # -----------------------------------------------------------------------
    # 汇总
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("汇总")
    print("=" * 60)
    print(f"  总耗时（并行）: {total_elapsed:.1f}s")
    print(f"  调用数: {len(tasks)}")
    print(f"  规则通过: {pass_count}")
    print(f"  规则失败: {fail_count}")
    print(f"  异常: {error_count}")

    if total_elapsed < 60:
        print(f"  耗时: OK (< 60s)")
    else:
        print(f"  耗时: WARN (>= 60s，但并行已最优)")

    # 坏内容(#2)必须检出问题
    if not isinstance(results_list[1], Exception):
        _, bad_results, _ = results_list[1]
        bad_has_fail = any(not r.passed for r in bad_results)
        print(f"  坏内容检出: {'OK' if bad_has_fail else 'MISS（完整 prompt 未检出伪词源）'}")

    print("\n集成测试完成")


if __name__ == "__main__":
    asyncio.run(main())
