"""快速测试：用 docs/prompts/quality/ 的完整 prompt 对一个词跑质检。

对比：
- 生产环境的精简 prompt（hardcoded in unified checkers）
- 完整 prompt（docs/prompts/quality/ 文件）

用法:
    python test_full_prompt_qc.py
"""

import asyncio
import json
import time
import uuid

import httpx

# ── 配置 ─────────────────────────────────────────────
GATEWAY_BASE_URL = "https://aigateway.51talk.com/v1"
GATEWAY_API_KEY = "01225b1e-e498-46bf-8038-daeac9d07d90"
MODEL = "gemini-3-flash-preview|efficiency"

# ── 测试数据：一个词的完整助记内容 ───────────────────────
TEST_WORD = "protect"
TEST_POS = "v."
TEST_MEANING = "保护；防护"
# 从黄金案例表提取的正例内容
TEST_CONTENT = """[核心公式] pro(向前) + tect(盖上/掩蔽)
[助记口诀/逻辑] 向前(pro)盖住(tect)，就是保护
[老师话术] 来，XX同学，咱先把这个词念得饱满一点：pro-tect。注意最后那个 /t/ 的爆破音，舌尖抵住上齿龈，然后短促有力地弹开，是不是感觉像给自己扣上了一个坚固的扣子？对，就是要这种"咔哒"一声的安全感，先把这个发音的气场找着，咱们再往下走。
好，盯着屏幕上的公式：pro，向前；tect，盖上、掩蔽。你想想看，当危险来了，你第一反应是干什么？是不是往前一站，把身后的人挡住，就像给他们盖上了一面盾？对，pro-tect，向前盖住，就是保护。
闭上眼，想象一个画面：暴风雨来了，一棵大树向前伸展枝叶，把树下的小动物全盖住了。风吹不着，雨淋不着——这就是protect，用自己的力量向前覆盖，守护住一切。
现在睁开眼，咱来裂变几个同族词：detect，de是去掉，tect还是盖上，去掉遮盖物——就是"发现、侦测"；architect，archi是首要的，tect是建造（源自同一词根），首席建造者——就是"建筑师"。看到没，一个tect词根，串起一家子。
最后送你一句话：真正的保护，不是把别人关起来，而是像那棵大树一样，向前一步，用自己的力量为他人遮风挡雨。protect的力量，就在"向前"两个字里。"""


# ── 生产环境精简 prompt ──────────────────────────────────
PROD_SYSTEM_PROMPT = """你是中小学英语教学专家。请对给定的助记内容执行以下检查:
1. N5_AI: 老师话术是否包含完整步骤框架
2. N6: 助记逻辑是否合理，是否为伪助记

返回 JSON: {"results": [{"rule_id": "N5_AI", "passed": ..., "detail": ...},
{"rule_id": "N6", "passed": ..., "detail": ...}]}"""


# ── 完整 prompt ──────────────────────────────────────
def load_full_prompt() -> str:
    from pathlib import Path
    prompt_path = Path(__file__).parent.parent / "docs" / "prompts" / "quality" / "助记-词根词缀.md"
    return prompt_path.read_text(encoding="utf-8").strip()


# ── Gateway 调用 ─────────────────────────────────────
async def call_gateway(system_prompt: str, user_prompt: str, label: str) -> dict:
    body = {
        "model": MODEL,
        "provider": "VERTEX",
        "api_key": GATEWAY_API_KEY,
        "biz_type": "vocab_qc",
        "biz_id": str(uuid.uuid4()),
        "stream": False,
        "async": True,
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
        ],
        "temperature": 0,
    }
    headers = {"Content-Type": "application/json"}

    t0 = time.monotonic()

    async with httpx.AsyncClient() as client:
        # Submit
        resp = await client.post(
            f"{GATEWAY_BASE_URL}/chat/completions",
            headers=headers, json=body, timeout=30,
        )
        task_no = resp.json().get("res")
        print(f"  [{label}] 提交成功 task_no={task_no}")

        # Poll
        poll_body = {
            "provider": "VERTEX", "model": MODEL, "api_key": GATEWAY_API_KEY,
            "biz_type": "vocab_qc", "biz_id": body["biz_id"], "task_no": task_no,
        }
        for i in range(60):
            await asyncio.sleep(3)
            try:
                pr = await client.post(
                    f"{GATEWAY_BASE_URL}/chat/task/result",
                    headers=headers, json=poll_body, timeout=30,
                )
                res = pr.json().get("res", {})
                status = res.get("status") if isinstance(res, dict) else None
                elapsed = time.monotonic() - t0

                if status == "COMPLETED":
                    content = res["result"]["choices"][0]["message"]["content"]
                    print(f"  [{label}] ✅ 完成 ({elapsed:.1f}s)")
                    return {"content": content, "elapsed": elapsed, "status": "ok"}
                elif status == "FAILED":
                    print(f"  [{label}] ❌ 失败: {res.get('failed_reason')}")
                    return {"content": "", "elapsed": elapsed, "status": "failed"}
                else:
                    if i % 5 == 4:
                        print(f"  [{label}] 轮询 #{i+1} ({elapsed:.0f}s) status={status}")
            except Exception as e:
                print(f"  [{label}] 轮询异常: {e}")

    return {"content": "", "elapsed": time.monotonic() - t0, "status": "timeout"}


async def main():
    user_prompt = (
        f"Word: {TEST_WORD} | POS: {TEST_POS} | "
        f"Meaning: {TEST_MEANING} | Mnemonic: {TEST_CONTENT}"
    )

    full_prompt = load_full_prompt()

    print(f"测试词: {TEST_WORD} ({TEST_POS}) {TEST_MEANING}")
    print(f"助记内容: {len(TEST_CONTENT)} 字符")
    print(f"生产精简 prompt: {len(PROD_SYSTEM_PROMPT)} 字符")
    print(f"完整质检 prompt: {len(full_prompt)} 字符")
    print()

    # 1. 生产精简 prompt
    print("=" * 60)
    print("1. 生产环境精简 prompt（2 条规则）")
    print("=" * 60)
    r1 = await call_gateway(PROD_SYSTEM_PROMPT, user_prompt, "精简")
    if r1["status"] == "ok":
        print(f"\n  输出:\n  {r1['content'][:500]}")

    print()

    # 2. 完整 prompt
    print("=" * 60)
    print("2. 完整质检 prompt（10 条检查规则 + few-shot）")
    print("=" * 60)
    r2 = await call_gateway(full_prompt, user_prompt, "完整")
    if r2["status"] == "ok":
        print(f"\n  输出:\n  {r2['content'][:500]}")

    # 汇总
    print()
    print("=" * 60)
    print("对比结果")
    print("=" * 60)
    print(f"  精简 prompt: {r1['elapsed']:.1f}s | {r1['status']}")
    print(f"  完整 prompt: {r2['elapsed']:.1f}s | {r2['status']}")
    print(f"  耗时比: {r2['elapsed']/r1['elapsed']:.1f}x")


if __name__ == "__main__":
    asyncio.run(main())
