"""主评估脚本：异步并行调用 3 模型，大幅提速。

用法:
    python run_eval.py                      # 全量跑（3模型并行 × 每模型10并发）
    python run_eval.py --dim sentence       # 只跑例句维度
    python run_eval.py --model GPT-5.2      # 只跑 GPT-5.2
    python run_eval.py --concurrency 5      # 每模型并发数（默认10）
    python run_eval.py --dry-run            # 只提取案例，不调 API
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path

import httpx

from checkpoints import DIMENSION_CHECKPOINTS, build_json_output_instruction
from config import RESULTS_DIR, ModelConfig, load_models, load_prompt
from extract_cases import TestCase, extract_all_cases, save_cases_json


# ── 结果文件 ─────────────────────────────────────────
def _result_path(dimension: str, model_name: str) -> Path:
    safe_name = model_name.replace(" ", "_").replace("/", "_")
    return RESULTS_DIR / f"eval_{dimension}_{safe_name}.json"


def _load_existing_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {r["key"] for r in data.get("results", [])}


def _load_existing_results(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("results", [])


def _save_results(path: Path, dimension: str, model_name: str, results: list[dict]) -> None:
    path.parent.mkdir(exist_ok=True)
    data = {
        "dimension": dimension,
        "model": model_name,
        "total": len(results),
        "correct": sum(1 for r in results if r.get("is_correct")),
        "results": results,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── API 调用 ─────────────────────────────────────────

# Gateway provider 自动推断
_MODEL_PROVIDER_MAP = {"gemini": "VERTEX", "gpt": "AZURE"}


def _resolve_provider(model: str) -> str:
    model_lower = model.lower().split("|")[0]
    for prefix, provider in _MODEL_PROVIDER_MAP.items():
        if model_lower.startswith(prefix):
            return provider
    return "OPENAI"


async def call_model_async(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    *,
    gateway: bool = False,
) -> tuple[str, float]:
    """调用模型。gateway=True 时走 51talk AI Gateway 异步提交+轮询模式。"""
    if gateway:
        return await _call_gateway_async(client, base_url, api_key, model, system_prompt, user_prompt)

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    t0 = time.monotonic()
    resp = await client.post(url, headers=headers, json=body, timeout=180)
    elapsed = time.monotonic() - t0
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    return content, elapsed


async def _call_gateway_async(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, float]:
    """51talk AI Gateway: 异步提交 → 轮询结果。"""
    import uuid

    submit_url = f"{base_url.rstrip('/')}/chat/completions"
    body = {
        "model": model,
        "provider": _resolve_provider(model),
        "api_key": api_key,
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

    # 1. 提交任务
    resp = await client.post(submit_url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    submit_data = resp.json()
    code = submit_data.get("code")
    task_no = submit_data.get("res")
    if code != 10000 or not isinstance(task_no, str):
        raise RuntimeError(f"Gateway submit failed: code={code}, res={task_no}")

    # 2. 轮询结果
    poll_url = f"{base_url.rstrip('/')}/chat/task/result"
    poll_body = {
        "provider": body["provider"],
        "model": body["model"],
        "api_key": body["api_key"],
        "biz_type": body["biz_type"],
        "biz_id": body["biz_id"],
        "task_no": task_no,
    }

    max_wait = 300  # 5 分钟
    poll_interval = 3.0
    deadline = time.monotonic() + max_wait

    while time.monotonic() < deadline:
        await asyncio.sleep(poll_interval)
        try:
            # 每次轮询用新 client 避免连接池断开
            async with httpx.AsyncClient() as poll_client:
                poll_resp = await poll_client.post(poll_url, headers=headers, json=poll_body, timeout=30)
        except (httpx.ConnectError, httpx.TimeoutException):
            # 连接失败，等待后重试
            await asyncio.sleep(poll_interval * 2)
            continue

        if poll_resp.status_code == 429:
            await asyncio.sleep(poll_interval * 2)
            continue
        poll_resp.raise_for_status()

        poll_data = poll_resp.json()
        res = poll_data.get("res", {})
        status = res.get("status") if isinstance(res, dict) else None

        if status == "COMPLETED" and res.get("result"):
            elapsed = time.monotonic() - t0
            result_data = res["result"]
            choices = result_data.get("choices", [])
            if choices:
                content = choices[0]["message"]["content"]
                return content, elapsed
            raise RuntimeError(f"Gateway result missing choices: {result_data}")
        elif status == "FAILED":
            raise RuntimeError(f"Gateway task failed: {res.get('failed_reason', 'unknown')}")
        # PENDING/PROCESSING → 继续轮询

    raise RuntimeError(f"Gateway poll timeout ({max_wait}s), task_no={task_no}")


def parse_structured_output(raw_output: str, dimension: str) -> dict:
    text = raw_output.strip()
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            checkpoints = parsed.get("checkpoints", {})
            overall = parsed.get("overall", "").upper()
            reason = parsed.get("reason", "")
            if overall not in ("PASS", "FAIL"):
                has_no = any(str(v).upper() == "NO" for v in checkpoints.values())
                overall = "FAIL" if has_no else "PASS"
            return {"checkpoints": checkpoints, "overall": overall, "reason": reason}
        except json.JSONDecodeError:
            pass
    # fallback
    upper = text.upper()
    has_fail = "不通过" in text or "FAIL" in upper
    overall = "FAIL" if has_fail else "PASS"
    checkpoints = {cp.id: "N/A" for cp in DIMENSION_CHECKPOINTS.get(dimension, [])}
    return {"checkpoints": checkpoints, "overall": overall, "reason": text[:200]}


# ── 单模型单维度并行评估 ─────────────────────────────────
async def eval_model_dimension(
    model_cfg: ModelConfig,
    dimension: str,
    cases: list[TestCase],
    system_prompt: str,
    concurrency: int,
    progress_prefix: str,
) -> list[dict]:
    """并行评估一个模型在一个维度上的所有案例。"""
    result_path = _result_path(dimension, model_cfg.name)
    existing_keys = _load_existing_keys(result_path)
    existing_results = _load_existing_results(result_path)

    # 过滤出需要跑的案例
    pending = [c for c in cases if f"{c.case_id}_{c.sample_type}" not in existing_keys]
    skipped = len(cases) - len(pending)

    if skipped:
        print(f"  {progress_prefix} 跳过 {skipped} 已完成，剩余 {len(pending)} 待跑")

    if not pending:
        print(f"  {progress_prefix} 全部已完成 ✅")
        return existing_results

    results = list(existing_results)
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    counters = {"done": 0, "correct": 0, "error": 0, "total": len(pending)}

    async def process_one(case: TestCase) -> None:
        key = f"{case.case_id}_{case.sample_type}"
        async with sem:
            try:
                async with httpx.AsyncClient() as client:
                    raw_output, elapsed = await call_model_async(
                        client, model_cfg.base_url, model_cfg.api_key,
                        model_cfg.model, system_prompt, case.user_prompt_input,
                        gateway=model_cfg.gateway,
                    )
                parsed = parse_structured_output(raw_output, dimension)
                judgment = parsed["overall"]
                is_correct = (judgment == case.expected)

                result = {
                    "key": key, "case_id": case.case_id, "word": case.word,
                    "category": case.category, "sample_type": case.sample_type,
                    "issue_desc": case.issue_desc, "expected": case.expected,
                    "model_judgment": judgment, "is_correct": is_correct,
                    "checkpoints": parsed["checkpoints"],
                    "reason": parsed["reason"], "raw_output": raw_output,
                    "elapsed_s": round(elapsed, 2), "error": None,
                }
                icon = "✅" if is_correct else "❌"

                async with lock:
                    counters["done"] += 1
                    if is_correct:
                        counters["correct"] += 1
                    results.append(result)
                    # 每 5 个保存一次
                    if counters["done"] % 5 == 0 or counters["done"] == counters["total"]:
                        _save_results(result_path, dimension, model_cfg.name, results)
                    print(
                        f"    {progress_prefix} [{counters['done']}/{counters['total']}] "
                        f"{case.word[:15]:<15} {case.sample_type} "
                        f"期望={case.expected} 模型={judgment} {icon} ({elapsed:.1f}s)"
                    )

            except Exception as e:
                async with lock:
                    counters["done"] += 1
                    counters["error"] += 1
                    results.append({
                        "key": key, "case_id": case.case_id, "word": case.word,
                        "category": case.category, "sample_type": case.sample_type,
                        "issue_desc": case.issue_desc, "expected": case.expected,
                        "model_judgment": "ERROR", "is_correct": False,
                        "checkpoints": {}, "reason": "", "raw_output": "",
                        "elapsed_s": 0, "error": str(e),
                    })
                    print(f"    {progress_prefix} [{counters['done']}/{counters['total']}] "
                          f"{case.word[:15]:<15} ERROR: {e}")

    # 并行执行
    await asyncio.gather(*[process_one(c) for c in pending])

    # 最终保存
    _save_results(result_path, dimension, model_cfg.name, results)

    total_done = len(results)
    total_correct = sum(1 for r in results if r.get("is_correct"))
    print(
        f"  {progress_prefix} → 完成: {total_correct}/{total_done} 正确 "
        f"({total_correct/total_done*100:.1f}%), 错误 {counters['error']}"
    )
    return results


# ── 主流程 ──────────────────────────────────────────
async def run_eval_async(
    dimensions: list[str] | None = None,
    model_filter: str | None = None,
    dry_run: bool = False,
    concurrency: int = 10,
) -> None:
    print("=== 提取测试案例 ===")
    all_cases = extract_all_cases()
    save_cases_json(all_cases)

    for dim, cases in all_cases.items():
        pos = sum(1 for c in cases if c.sample_type == "正例")
        neg = sum(1 for c in cases if c.sample_type == "反例")
        print(f"  {dim}: {len(cases)} ({pos}正例 + {neg}反例)")

    if dry_run:
        print("\n--dry-run: 仅提取案例，不调用 API")
        return

    models = load_models()
    if model_filter:
        models = [m for m in models if model_filter.lower() in m.name.lower()]
    print(f"\n=== 模型: {[m.name for m in models]}, 每模型并发: {concurrency} ===")

    if dimensions:
        all_cases = {d: c for d, c in all_cases.items() if d in dimensions}

    # 逐维度，3 模型并行
    for dimension, cases in all_cases.items():
        base_prompt = load_prompt(dimension)
        json_instruction = build_json_output_instruction(dimension)
        system_prompt = base_prompt + json_instruction

        print(f"\n{'='*60}")
        print(f"维度: {dimension} ({len(cases)} 案例 × {len(models)} 模型)")
        print(f"{'='*60}")

        # 3 个模型并行跑同一维度
        tasks = [
            eval_model_dimension(
                model_cfg=m,
                dimension=dimension,
                cases=cases,
                system_prompt=system_prompt,
                concurrency=concurrency,
                progress_prefix=f"[{m.name}]",
            )
            for m in models
        ]
        await asyncio.gather(*tasks)

    print(f"\n{'='*60}")
    print("全部评估完成！运行 python report.py 生成汇总报告。")


def main() -> None:
    parser = argparse.ArgumentParser(description="QC 模型评估（异步并行）")
    parser.add_argument("--dim", type=str, help="只跑指定维度")
    parser.add_argument("--model", type=str, help="只跑指定模型")
    parser.add_argument("--dry-run", action="store_true", help="仅提取案例")
    parser.add_argument("--concurrency", type=int, default=10, help="每模型并发数 (default: 10)")
    args = parser.parse_args()

    dims = [args.dim] if args.dim else None
    asyncio.run(run_eval_async(
        dimensions=dims,
        model_filter=args.model,
        dry_run=args.dry_run,
        concurrency=args.concurrency,
    ))


if __name__ == "__main__":
    main()
